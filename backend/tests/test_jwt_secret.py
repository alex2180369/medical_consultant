"""Tests for JWT_SECRET fail-fast protection in production."""

from __future__ import annotations

import pytest

from app.config import load_settings


def test_production_requires_strong_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production should refuse the default development secret."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AITUNNEL_API_KEY", raising=False)
    monkeypatch.delenv("PROXYAPI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load_settings()


def test_production_requires_long_enough_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production should reject a short explicit JWT_SECRET."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "short-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load_settings()


def test_production_rejects_placeholder_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production should reject the .env.example placeholder value."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "change-me-generate-a-long-random-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load_settings()


def test_production_accepts_strong_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production should boot with a long explicit JWT_SECRET."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = load_settings()
    assert settings.jwt_secret == "x" * 64


def test_development_allows_default_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-production environments keep the development default."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = load_settings()
    assert settings.jwt_secret == "dev-insecure-change-me"


def test_test_env_ignores_production_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test environment should not raise for a short secret."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = load_settings()
    assert settings.jwt_secret == "test-secret"