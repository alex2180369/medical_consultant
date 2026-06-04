"""SQLite database helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection, Row, connect

from app.config import load_settings
from app.security import ADMIN_PASSWORD, ADMIN_USERNAME, hash_password


def get_database_path() -> Path:
    """Return the configured SQLite database path."""
    return load_settings().database_path


@contextmanager
def get_connection() -> Iterator[Connection]:
    """Open a SQLite connection with row access by column name."""
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect(database_path)
    connection.row_factory = Row

    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    """Create required tables if they do not exist."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'member',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL DEFAULT '',
                age INTEGER,
                birth_date TEXT,
                sex TEXT NOT NULL DEFAULT '',
                blood_type TEXT NOT NULL DEFAULT '',
                height_cm REAL,
                weight_kg REAL,
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
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                marker_name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                reference_range TEXT NOT NULL DEFAULT '',
                measured_at TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                extracted_text TEXT NOT NULL DEFAULT '',
                analysis_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                symptoms TEXT NOT NULL DEFAULT '',
                doctor_feedback TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL,
                ai_analysis TEXT NOT NULL DEFAULT '',
                ai_diagnosis TEXT NOT NULL DEFAULT '',
                ai_treatment TEXT NOT NULL DEFAULT '',
                ai_doctor_questions TEXT NOT NULL DEFAULT '',
                ai_urgency TEXT NOT NULL DEFAULT '',
                ai_status TEXT NOT NULL DEFAULT 'pending',
                ai_opinion_comparison TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS consultations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                occurred_at TEXT NOT NULL,
                doctor_feedback TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                complaint_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS consultation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                consultation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (consultation_id) REFERENCES consultations(id)
            );
            """
        )
        _migrate_legacy_profile_table(connection)
        _migrate_profiles_table(connection)
        _migrate_user_scope_columns(connection)
        _migrate_complaints_table(connection)
        _migrate_documents_table(connection)
        _seed_default_users(connection)


def _table_columns(connection: Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _migrate_legacy_profile_table(connection: Connection) -> None:
    """Move single-row profiles to per-user profiles."""
    columns = _table_columns(connection, "profiles")
    if "user_id" in columns or "id" not in columns:
        return

    connection.executescript(
        """
        CREATE TABLE profiles_new (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL DEFAULT '',
            age INTEGER,
            birth_date TEXT,
            sex TEXT NOT NULL DEFAULT '',
            blood_type TEXT NOT NULL DEFAULT '',
            height_cm REAL,
            weight_kg REAL,
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
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    default_user_id = _ensure_default_member_user(connection)
    connection.execute(
        """
        INSERT INTO profiles_new (
            user_id,
            full_name,
            age,
            birth_date,
            sex,
            blood_type,
            height_cm,
            weight_kg,
            diabetes_status,
            cardiovascular_status,
            chronic_conditions,
            allergies,
            medications,
            family_history,
            lifestyle,
            activity_level,
            smoking_status,
            sleep_hours,
            stress_level,
            family_members,
            notes,
            updated_at
        )
        SELECT
            ?,
            full_name,
            age,
            NULL,
            sex,
            '',
            height_cm,
            weight_kg,
            '',
            '',
            chronic_conditions,
            allergies,
            medications,
            family_history,
            lifestyle,
            '',
            '',
            NULL,
            '',
            NULL,
            notes,
            updated_at
        FROM profiles
        WHERE id = 1
        """,
        (default_user_id,),
    )
    connection.execute("DROP TABLE profiles")
    connection.execute("ALTER TABLE profiles_new RENAME TO profiles")


def _migrate_profiles_table(connection: Connection) -> None:
    """Add extended questionnaire columns to older profile tables."""
    columns = _table_columns(connection, "profiles")
    migrations = {
        "birth_date": "TEXT",
        "blood_type": "TEXT NOT NULL DEFAULT ''",
        "diabetes_status": "TEXT NOT NULL DEFAULT ''",
        "cardiovascular_status": "TEXT NOT NULL DEFAULT ''",
        "activity_level": "TEXT NOT NULL DEFAULT ''",
        "smoking_status": "TEXT NOT NULL DEFAULT ''",
        "sleep_hours": "INTEGER",
        "stress_level": "TEXT NOT NULL DEFAULT ''",
        "family_members": "INTEGER",
    }

    for column_name, definition in migrations.items():
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE profiles ADD COLUMN {column_name} {definition}"
            )


def _ensure_default_member_user(connection: Connection) -> int:
    """Ensure there is a default family member for legacy data."""
    row = connection.execute(
        "SELECT id FROM users WHERE username = ?",
        ("family",),
    ).fetchone()
    if row is not None:
        return int(row["id"])

    cursor = connection.execute(
        """
        INSERT INTO users (username, password_hash, display_name, role, is_active)
        VALUES (?, ?, ?, 'member', 1)
        """,
        ("family", hash_password("family"), "Семья"),
    )
    return int(cursor.lastrowid)


def _migrate_user_scope_columns(connection: Connection) -> None:
    """Add user_id to legacy tables and backfill existing rows."""
    default_user_id = _ensure_default_member_user(connection)
    scoped_tables = (
        "lab_results",
        "documents",
        "complaints",
        "consultations",
    )

    for table_name in scoped_tables:
        columns = _table_columns(connection, table_name)
        if "user_id" in columns:
            continue

        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1"
        )
        connection.execute(
            f"UPDATE {table_name} SET user_id = ? WHERE user_id = 1",
            (default_user_id,),
        )


def _seed_default_users(connection: Connection) -> None:
    """Create the default administrator account."""
    row = connection.execute(
        "SELECT id FROM users WHERE username = ?",
        (ADMIN_USERNAME,),
    ).fetchone()
    if row is not None:
        return

    cursor = connection.execute(
        """
        INSERT INTO users (username, password_hash, display_name, role, is_active)
        VALUES (?, ?, ?, 'admin', 1)
        """,
        (ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), "Администратор"),
    )
    admin_id = int(cursor.lastrowid)
    connection.execute(
        """
        INSERT INTO profiles (user_id, full_name)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO NOTHING
        """,
        (admin_id, "Администратор"),
    )


def _migrate_documents_table(connection: Connection) -> None:
    """Add extraction columns to older databases."""
    columns = _table_columns(connection, "documents")
    migrations = {
        "extracted_text": "TEXT NOT NULL DEFAULT ''",
        "analysis_status": "TEXT NOT NULL DEFAULT 'pending'",
    }

    for column_name, definition in migrations.items():
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE documents ADD COLUMN {column_name} {definition}"
            )


def _migrate_complaints_table(connection: Connection) -> None:
    """Add AI analysis columns to older databases."""
    columns = _table_columns(connection, "complaints")
    migrations = {
        "ai_analysis": "TEXT NOT NULL DEFAULT ''",
        "ai_diagnosis": "TEXT NOT NULL DEFAULT ''",
        "ai_treatment": "TEXT NOT NULL DEFAULT ''",
        "ai_doctor_questions": "TEXT NOT NULL DEFAULT ''",
        "ai_urgency": "TEXT NOT NULL DEFAULT ''",
        "ai_status": "TEXT NOT NULL DEFAULT 'pending'",
        "ai_opinion_comparison": "TEXT NOT NULL DEFAULT ''",
    }

    for column_name, definition in migrations.items():
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE complaints ADD COLUMN {column_name} {definition}"
            )
