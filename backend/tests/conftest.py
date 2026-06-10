"""Shared pytest fixtures."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://medical:medical@localhost:5432/medical_consultant_test",
    ),
)
os.environ.setdefault("APPWRITE_PROJECT_ID", "test-project")

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
