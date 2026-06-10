"""Tests for model route selection."""

from datetime import date

from app.schemas import ComplaintCreate, MedicalProfile
from app.services.llm_router import LlmTask, resolve_model_route
from app.services.symptom_analyzer import resolve_symptom_task
from tests.test_settings import make_test_settings


def test_resolve_imaging_route_uses_proxyapi() -> None:
    """Imaging tasks should use the configured proxyapi.ru model."""
    route = resolve_model_route(LlmTask.IMAGING, make_test_settings())

    assert route.provider == "proxyapi.ru"
    assert route.model == "imaging-model"


def test_resolve_complex_and_review_routes_use_aitunnel() -> None:
    """Complex and review tasks should stay on aitunnel.ru."""
    settings = make_test_settings()

    complex_route = resolve_model_route(LlmTask.COMPLEX_SYMPTOMS, settings)
    review_route = resolve_model_route(LlmTask.REVIEW, settings)

    assert complex_route.provider == "aitunnel.ru"
    assert complex_route.model == "complex-model"
    assert review_route.provider == "aitunnel.ru"
    assert review_route.model == "review-model"


def test_resolve_symptom_task_uses_review_mode() -> None:
    """Review mode should always route to the review model."""
    complaint = ComplaintCreate(
        symptoms="Насморк",
        occurred_at=date(2026, 5, 20),
    )

    task = resolve_symptom_task("review", complaint, MedicalProfile())

    assert task == LlmTask.REVIEW


def test_resolve_symptom_task_auto_complex_for_long_text() -> None:
    """Long multi-symptom complaints should route to the complex model."""
    complaint = ComplaintCreate(
        symptoms=(
            "Сильная головная боль, тошнота, слабость, головокружение, "
            "онемение руки и ухудшение зрения уже третий день"
        ),
        occurred_at=date(2026, 5, 20),
    )

    task = resolve_symptom_task("standard", complaint, MedicalProfile())

    assert task == LlmTask.COMPLEX_SYMPTOMS
