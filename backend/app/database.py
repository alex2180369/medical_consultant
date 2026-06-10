"""PostgreSQL database helpers."""

from collections.abc import Iterator
from contextlib import contextmanager

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

            CREATE INDEX IF NOT EXISTS idx_lab_results_user_id
                ON lab_results(user_id);
            CREATE INDEX IF NOT EXISTS idx_documents_user_id
                ON documents(user_id);
            CREATE INDEX IF NOT EXISTS idx_complaints_user_id
                ON complaints(user_id);
            CREATE INDEX IF NOT EXISTS idx_consultations_user_id
                ON consultations(user_id);
            """
        )


def ensure_user_profile(
    user_id: str,
    *,
    email: str = "",
    display_name: str = "",
) -> None:
    """Create an empty profile row for a new Appwrite user."""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO profiles (user_id, email, display_name, full_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = CASE
                    WHEN profiles.display_name = '' THEN EXCLUDED.display_name
                    ELSE profiles.display_name
                END,
                updated_at = NOW()
            """,
            (user_id, email, display_name, display_name),
        )
