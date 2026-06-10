"""Account deletion helpers."""

from __future__ import annotations

from pathlib import Path

import httpx

from app.config import load_settings
from app.database import get_connection


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


def delete_appwrite_user(user_id: str) -> None:
    """Delete the Appwrite account using the server API key."""
    settings = load_settings()
    if not settings.appwrite_api_key:
        raise RuntimeError("APPWRITE_API_KEY is not configured.")

    response = httpx.delete(
        f"{settings.appwrite_endpoint.rstrip('/')}/users/{user_id}",
        headers={
            "X-Appwrite-Project": settings.appwrite_project_id,
            "X-Appwrite-Key": settings.appwrite_api_key,
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if response.status_code not in {200, 204, 404}:
        response.raise_for_status()
