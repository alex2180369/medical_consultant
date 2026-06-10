"""Routes for AI nutrition planning."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.database import get_connection
from app.schemas import (
    ComplaintRecord,
    MedicalProfile,
    NutritionPlanRequest,
    NutritionPlanResponse,
)
from app.services.auth_service import AuthContext, get_auth_context
from app.services.nutrition_service import generate_weekly_nutrition_plan

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


def _load_profile(user_id: str) -> MedicalProfile:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM profiles WHERE user_id = %s",
            (user_id,),
        ).fetchone()

    if row is None:
        return MedicalProfile()

    return MedicalProfile(**dict(row))


def _load_recent_complaints(user_id: str) -> list[ComplaintRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM complaints
            WHERE user_id = %s
            ORDER BY occurred_at DESC, id DESC
            LIMIT 5
            """,
            (user_id,),
        ).fetchall()

    return [ComplaintRecord(**dict(row)) for row in rows]


@router.post("/weekly-menu", response_model=NutritionPlanResponse)
def generate_weekly_menu(
    payload: NutritionPlanRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> NutritionPlanResponse:
    """Generate a weekly menu for the current effective user."""
    user_id = auth.user_id
    complaints = (
        _load_recent_complaints(user_id)
        if payload.include_medical_recommendations
        else []
    )
    return generate_weekly_nutrition_plan(
        profile=_load_profile(user_id),
        complaints=complaints,
        pantry_items=payload.pantry_items,
        include_medical_recommendations=payload.include_medical_recommendations,
    )
