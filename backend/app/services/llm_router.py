"""Model routing rules for future AI requests."""

from dataclasses import dataclass
from enum import StrEnum

from app.config import Settings


class LlmTask(StrEnum):
    """Supported categories of AI tasks."""

    SYMPTOMS = "symptoms"
    MEDICATIONS = "medications"
    COMPLEX_SYMPTOMS = "complex_symptoms"
    REVIEW = "review"
    IMAGING = "imaging"
    NUTRITION = "nutrition"
    ADMIN_ENRICHMENT = "admin_enrichment"


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """Resolved model provider and model name."""

    provider: str
    model: str


def resolve_model_route(task: LlmTask, settings: Settings) -> ModelRoute:
    """Return the configured provider and model for a medical AI task."""
    routes = {
        LlmTask.SYMPTOMS: ModelRoute(
            provider="aitunnel.ru",
            model=settings.symptoms_model,
        ),
        LlmTask.MEDICATIONS: ModelRoute(
            provider="aitunnel.ru",
            model=settings.medications_model,
        ),
        LlmTask.COMPLEX_SYMPTOMS: ModelRoute(
            provider="aitunnel.ru",
            model=settings.complex_symptoms_model,
        ),
        LlmTask.REVIEW: ModelRoute(
            provider="aitunnel.ru",
            model=settings.review_model,
        ),
        LlmTask.IMAGING: ModelRoute(
            provider="proxyapi.ru",
            model=settings.imaging_model,
        ),
        LlmTask.NUTRITION: ModelRoute(
            provider="aitunnel.ru",
            model=settings.nutrition_model,
        ),
        LlmTask.ADMIN_ENRICHMENT: ModelRoute(
            provider="proxyapi.ru",
            model=settings.admin_enrichment_model,
        ),
    }

    return routes[task]
