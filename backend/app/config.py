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
    admin_email: str | None
    ops_notify_url: str | None
    ops_token: str | None
    admin_enrichment_model: str
    payment_gateway_enabled: bool = False
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    nutrition_model: str = "claude-sonnet-4.6"
    yandex_ocr_api_key: str | None = None
    yandex_ocr_folder_id: str | None = None
    yandex_ocr_base_url: str = "https://ocr.api.cloud.yandex.net/ocr/v1"
    yandex_ocr_credits_per_page: int = 2
    auto_approve_after_minutes: int = 0
    yookassa_webhook_enabled: bool = False
    max_upload_bytes: int = 30 * 1024 * 1024


def load_settings() -> Settings:
    """Load settings from `.env` and process environment."""
    load_dotenv()

    app_env = environ.get("APP_ENV", "development")
    jwt_secret = environ.get("JWT_SECRET", "dev-insecure-change-me")

    if app_env.strip().lower() == "production":
        if (
            not jwt_secret.strip()
            or "change-me" in jwt_secret.lower()
            or "dev-insecure" in jwt_secret.lower()
            or len(jwt_secret.strip()) < 32
        ):
            raise RuntimeError(
                "JWT_SECRET must be set to a strong secret in production. "
                "Generate one with: python -c \"import secrets; "
                "print(secrets.token_hex(32))\""
            )

    return Settings(
        app_env=app_env,
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
        jwt_secret=jwt_secret,
        jwt_algorithm=environ.get("JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=int(environ.get("JWT_EXPIRE_MINUTES", "10080")),
        frontend_url=environ.get(
            "FRONTEND_URL", "https://ii-doktor.ru"
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
        admin_email=environ.get("ADMIN_EMAIL"),
        ops_notify_url=environ.get("OPS_NOTIFY_URL"),
        ops_token=environ.get("OPS_TOKEN"),
        admin_enrichment_model=environ.get(
            "ADMIN_ENRICHMENT_MODEL", "gpt-4o-mini"
        ),
        payment_gateway_enabled=environ.get(
            "PAYMENT_GATEWAY_ENABLED", "false"
        ).lower()
        in {"1", "true", "yes"},
        yookassa_shop_id=environ.get("YOOKASSA_SHOP_ID"),
        yookassa_secret_key=environ.get("YOOKASSA_SECRET_KEY"),
        yandex_ocr_api_key=environ.get("YANDEX_OCR_API_KEY"),
        yandex_ocr_folder_id=environ.get("YANDEX_OCR_FOLDER_ID"),
        yandex_ocr_base_url=environ.get(
            "YANDEX_OCR_BASE_URL",
            "https://ocr.api.cloud.yandex.net/ocr/v1",
        ),
        yandex_ocr_credits_per_page=int(
            environ.get("YANDEX_OCR_CREDITS_PER_PAGE", "2")
        ),
        auto_approve_after_minutes=int(
            environ.get("AUTO_APPROVE_AFTER_MINUTES", "0")
        ),
        yookassa_webhook_enabled=environ.get(
            "YOOKASSA_WEBHOOK_ENABLED", "false"
        ).lower()
        in {"1", "true", "yes"},
        max_upload_bytes=int(environ.get("MAX_UPLOAD_BYTES", "31457280")),
    )
