"""Shared test settings factory."""

from app.config import Settings


def make_test_settings(**overrides: object) -> Settings:
    """Build settings for unit tests."""
    defaults = {
        "app_env": "test",
        "app_name": "test",
        "database_url": "postgresql://medical:medical@localhost/test",
        "uploads_dir": "/tmp/medical-uploads",
        "aitunnel_api_key": None,
        "proxyapi_api_key": None,
        "symptoms_model": "symptoms-model",
        "medications_model": "medications-model",
        "complex_symptoms_model": "complex-model",
        "review_model": "review-model",
        "imaging_model": "imaging-model",
        "aitunnel_base_url": "https://api.aitunnel.ru/v1",
        "proxyapi_base_url": "https://api.proxyapi.ru/v1",
        "jwt_secret": "test-secret",
        "jwt_algorithm": "HS256",
        "jwt_expire_minutes": 60,
        "frontend_url": "https://example.test",
        "smtp_host": None,
        "smtp_port": 587,
        "smtp_username": None,
        "smtp_password": None,
        "smtp_from_email": None,
        "smtp_use_tls": True,
        "admin_email": "admin@example.com",
        "ops_notify_url": None,
        "ops_token": None,
        "admin_enrichment_model": "gpt-4o-mini",
        "payment_gateway_enabled": False,
        "yookassa_shop_id": None,
        "yookassa_secret_key": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)
