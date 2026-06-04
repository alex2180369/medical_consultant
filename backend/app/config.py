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
    database_path: Path
    aitunnel_api_key: str | None
    proxyapi_api_key: str | None
    symptoms_model: str
    medications_model: str
    complex_symptoms_model: str
    review_model: str
    imaging_model: str
    aitunnel_base_url: str
    proxyapi_base_url: str
    nutrition_model: str = "claude-sonnet-4.6"


def load_settings() -> Settings:
    """Load settings from `.env` and process environment."""
    load_dotenv()

    return Settings(
        app_env=environ.get("APP_ENV", "development"),
        app_name=environ.get("APP_NAME", "Локальный медицинский ИИ-навигатор"),
        database_path=Path(
            environ.get("DATABASE_PATH", "./data/medical_consultant.sqlite3")
        ),
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
    )
