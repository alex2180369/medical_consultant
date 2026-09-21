"""PostgreSQL database helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from os import environ

import psycopg
from psycopg.rows import dict_row

from app.config import load_settings


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Open a PostgreSQL connection with row access by column name."""
    settings = load_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    connection = psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
    )

    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    """Create required tables if they do not exist."""
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                consent_accepted_at TIMESTAMPTZ,
                password_reset_token TEXT,
                password_reset_expires_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS password_reset_rate_limits (
                email TEXT PRIMARY KEY,
                last_requested_at TIMESTAMPTZ NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL DEFAULT '',
                age INTEGER,
                birth_date DATE,
                sex TEXT NOT NULL DEFAULT '',
                blood_type TEXT NOT NULL DEFAULT '',
                height_cm DOUBLE PRECISION,
                weight_kg DOUBLE PRECISION,
                diabetes_status TEXT NOT NULL DEFAULT '',
                cardiovascular_status TEXT NOT NULL DEFAULT '',
                chronic_conditions TEXT NOT NULL DEFAULT '',
                allergies TEXT NOT NULL DEFAULT '',
                medications TEXT NOT NULL DEFAULT '',
                family_history TEXT NOT NULL DEFAULT '',
                lifestyle TEXT NOT NULL DEFAULT '',
                activity_level TEXT NOT NULL DEFAULT '',
                smoking_status TEXT NOT NULL DEFAULT '',
                sleep_hours INTEGER,
                stress_level TEXT NOT NULL DEFAULT '',
                family_members INTEGER,
                notes TEXT NOT NULL DEFAULT '',
                consent_accepted_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS lab_results (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
                marker_name TEXT NOT NULL,
                value DOUBLE PRECISION NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                reference_range TEXT NOT NULL DEFAULT '',
                measured_at DATE NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                extracted_text TEXT NOT NULL DEFAULT '',
                analysis_status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS complaints (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
                symptoms TEXT NOT NULL DEFAULT '',
                doctor_feedback TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                occurred_at DATE NOT NULL,
                ai_analysis TEXT NOT NULL DEFAULT '',
                ai_diagnosis TEXT NOT NULL DEFAULT '',
                ai_treatment TEXT NOT NULL DEFAULT '',
                ai_doctor_questions TEXT NOT NULL DEFAULT '',
                ai_urgency TEXT NOT NULL DEFAULT '',
                ai_status TEXT NOT NULL DEFAULT 'pending',
                ai_opinion_comparison TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS consultations (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
                occurred_at DATE NOT NULL,
                doctor_feedback TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                complaint_id INTEGER REFERENCES complaints(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS consultation_messages (
                id SERIAL PRIMARY KEY,
                consultation_id INTEGER NOT NULL
                    REFERENCES consultations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_users_email
                ON users(lower(email));
            CREATE INDEX IF NOT EXISTS idx_lab_results_user_id
                ON lab_results(user_id);
            CREATE INDEX IF NOT EXISTS idx_documents_user_id
                ON documents(user_id);
            CREATE INDEX IF NOT EXISTS idx_complaints_user_id
                ON complaints(user_id);
            CREATE INDEX IF NOT EXISTS idx_consultations_user_id
                ON consultations(user_id);

            CREATE TABLE IF NOT EXISTS blocked_emails (
                email TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                blocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                blocked_by TEXT NOT NULL DEFAULT ''
            );
            """
        )
        _run_migrations(connection)

    from app.services.wallet_service import backfill_wallets_for_approved_users

    backfill_wallets_for_approved_users()


def _run_migrations(connection: psycopg.Connection) -> None:
    """Apply incremental schema changes for user moderation."""
    connection.execute(
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_suggested_name TEXT NOT NULL DEFAULT '';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_email_analysis TEXT NOT NULL DEFAULT '';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_confidence TEXT NOT NULL DEFAULT '';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_analyzed_at TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_by TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS rejected_by TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS rejection_reason TEXT NOT NULL DEFAULT '';
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_usage_events (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT,
            consultation_id INTEGER
                REFERENCES consultations(id) ON DELETE SET NULL,
            complaint_id INTEGER
                REFERENCES complaints(id) ON DELETE SET NULL,
            document_id INTEGER
                REFERENCES documents(id) ON DELETE SET NULL,
            operation_type TEXT NOT NULL,
            llm_task TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            provider_cost_rub NUMERIC(12, 6) NOT NULL DEFAULT 0,
            estimated_credits INTEGER NOT NULL DEFAULT 0,
            cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
            is_charged BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_llm_usage_events_user_id
            ON llm_usage_events(user_id);
        CREATE INDEX IF NOT EXISTS idx_llm_usage_events_consultation_id
            ON llm_usage_events(consultation_id);
        CREATE INDEX IF NOT EXISTS idx_llm_usage_events_created_at
            ON llm_usage_events(created_at DESC);

        CREATE TABLE IF NOT EXISTS user_wallets (
            user_id TEXT PRIMARY KEY REFERENCES profiles(user_id) ON DELETE CASCADE,
            credits_balance INTEGER NOT NULL DEFAULT 0,
            free_turns_remaining INTEGER NOT NULL DEFAULT 2,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
            delta_credits INTEGER NOT NULL,
            reason TEXT NOT NULL,
            reference_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id
            ON wallet_transactions(user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS payment_orders (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
            package_id TEXT NOT NULL,
            amount_rub NUMERIC(10, 2) NOT NULL,
            credits INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            provider TEXT NOT NULL DEFAULT 'yookassa',
            provider_payment_id TEXT,
            confirmation_url TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            paid_at TIMESTAMPTZ
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_provider_payment_id
            ON payment_orders(provider_payment_id)
            WHERE provider_payment_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_payment_orders_user_id
            ON payment_orders(user_id, created_at DESC);
        """
        )

    connection.execute(
        """
        ALTER TABLE llm_usage_events
            ADD COLUMN IF NOT EXISTS charged_credits INTEGER NOT NULL DEFAULT 0;
        """
    )

    settings = load_settings()
    if settings.auto_approve_after_minutes > 0:
        connection.execute(
            """
            UPDATE users
            SET status = 'approved',
                approved_at = COALESCE(approved_at, NOW()),
                approved_by = COALESCE(approved_by, 'auto')
            WHERE status = 'pending'
              AND approved_at IS NULL
              AND rejected_at IS NULL
              AND created_at < NOW() - make_interval(mins => %s)
            """,
            (settings.auto_approve_after_minutes,),
        )

    admin_email = environ.get("ADMIN_EMAIL", "").strip().lower()
    if admin_email:
        connection.execute(
            """
            UPDATE users
            SET role = 'admin', status = 'approved'
            WHERE lower(email) = %s
            """,
            (admin_email,),
        )


def ensure_user_profile(
    user_id: str,
    *,
    email: str = "",
    display_name: str = "",
    consent_accepted_at=None,
) -> None:
    """Create or update a profile row for a registered user."""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO profiles (
                user_id,
                email,
                display_name,
                full_name,
                consent_accepted_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = CASE
                    WHEN profiles.display_name = '' THEN EXCLUDED.display_name
                    ELSE profiles.display_name
                END,
                consent_accepted_at = COALESCE(
                    profiles.consent_accepted_at,
                    EXCLUDED.consent_accepted_at
                ),
                updated_at = NOW()
            """,
            (user_id, email, display_name, display_name, consent_accepted_at),
        )
