"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

PRODUCTION_DATABASE_NAME = "medical_consultant"


def _default_test_database_url() -> str:
    """Build the default URL for the isolated test database."""
    in_docker = Path("/.dockerenv").exists()
    host = "postgres" if in_docker else "localhost"
    password = os.environ.get("POSTGRES_PASSWORD", "medical")
    return (
        f"postgresql://medical:{password}@{host}:5432/"
        f"{PRODUCTION_DATABASE_NAME}_test"
    )


def _resolve_test_database_url() -> str:
    """Return a safe test database URL and reject production targets."""
    database_url = os.environ.get("TEST_DATABASE_URL") or _default_test_database_url()
    database_name = urlparse(database_url).path.lstrip("/")

    if database_name == PRODUCTION_DATABASE_NAME:
        raise RuntimeError(
            "Refusing to run tests against the production database "
            f"'{PRODUCTION_DATABASE_NAME}'. "
            f"Use TEST_DATABASE_URL with '{PRODUCTION_DATABASE_NAME}_test'."
        )

    if not database_name.endswith("_test"):
        raise RuntimeError(
            "Refusing to run tests against a non-test database "
            f"'{database_name}'. Database name must end with '_test'."
        )

    return database_url


os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = _resolve_test_database_url()
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.database import initialize_database
from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Return a test client with initialized database."""
    initialize_database()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """Return an authenticated test client."""
    client.headers.update({"Authorization": "Bearer test-user"})
    return client
