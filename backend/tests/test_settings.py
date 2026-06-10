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
        "appwrite_endpoint": "https://cloud.appwrite.io/v1",
        "appwrite_project_id": "test-project",
        "appwrite_api_key": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)
