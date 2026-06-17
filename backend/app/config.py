"""Application settings loaded from environment variables."""

from dataclasses import dataclass
from os import environ
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration for the backend."""

    app_env: str
    app_name: str
    database_url: str
    uploads_dir: Path
    aitunnel_api_key: str | None
    proxyapi_api_key: str | None
    symptoms_model: str
    medications_model: str
    complex_symptoms_model: str
    review_model: str
    imaging_model: str
    aitunnel_base_url: str
    proxyapi_base_url: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    frontend_url: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_use_tls: bool
    nutrition_model: str = "claude-sonnet-4.6"


def load_settings() -> Settings:
    """Load settings from `.env` and process environment."""
    load_dotenv()

    return Settings(
        app_env=environ.get("APP_ENV", "development"),
        app_name=environ.get("APP_NAME", "Локальный медицинский ИИ-навигатор"),
        database_url=environ.get(
            "DATABASE_URL",
            "postgresql://medical:medical@postgres:5432/medical_consultant",
        ),
        uploads_dir=Path(environ.get("UPLOADS_DIR", "./data/uploads")),
        aitunnel_api_key=environ.get("AITUNNEL_API_KEY"),
        proxyapi_api_key=environ.get("PROXYAPI_API_KEY"),
        symptoms_model=environ.get("SYMPTOMS_MODEL", "qwen3.5-plus-02-15"),
        medications_model=environ.get(
            "MEDICATIONS_MODEL", "claude-sonnet-4.6"
        ),
        complex_symptoms_model=environ.get(
            "COMPLEX_SYMPTOMS_MODEL", "deepseek-r1-0528"
        ),
        review_model=environ.get("REVIEW_MODEL", "claude-opus-4-7"),
        imaging_model=environ.get("IMAGING_MODEL", "gpt-4o-mini"),
        nutrition_model=environ.get("NUTRITION_MODEL", "claude-sonnet-4.6"),
        aitunnel_base_url=environ.get(
            "AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1"
        ),
        proxyapi_base_url=environ.get(
            "PROXYAPI_BASE_URL", "https://api.proxyapi.ru/openai/v1"
        ),
        jwt_secret=environ.get("JWT_SECRET", "dev-insecure-change-me"),
        jwt_algorithm=environ.get("JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=int(environ.get("JWT_EXPIRE_MINUTES", "10080")),
        frontend_url=environ.get(
            "FRONTEND_URL", "https://помощники-консультанты.рф"
        ),
        smtp_host=environ.get("SMTP_HOST"),
        smtp_port=int(environ.get("SMTP_PORT", "587")),
        smtp_username=environ.get("SMTP_USERNAME"),
        smtp_password=environ.get("SMTP_PASSWORD"),
        smtp_from_email=environ.get("SMTP_FROM_EMAIL"),
        smtp_use_tls=environ.get("SMTP_USE_TLS", "true").lower() in {
            "1",
            "true",
            "yes",
        },
    )
