"""Account deletion helpers."""

from __future__ import annotations

from pathlib import Path

from app.config import load_settings
from app.database import get_connection
from app.services.user_service import delete_user


def delete_user_files(user_id: str) -> None:
    """Remove uploaded files for a user from disk."""
    settings = load_settings()
    uploads_dir = settings.uploads_dir

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT path FROM documents WHERE user_id = %s",
            (user_id,),
        ).fetchall()

    for row in rows:
        file_path = Path(str(row["path"]))
        if file_path.exists() and uploads_dir in file_path.parents:
            file_path.unlink(missing_ok=True)


def hard_delete_user_data(user_id: str) -> None:
    """Physically remove all user records from PostgreSQL."""
    delete_user_files(user_id)

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM profiles WHERE user_id = %s",
            (user_id,),
        )

    delete_user(user_id)
