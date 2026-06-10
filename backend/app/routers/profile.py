"""Routes for the personal medical profile."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.database import get_connection
from app.schemas import MedicalProfile
from app.services.auth_service import AuthContext, get_auth_context

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=MedicalProfile)
def get_profile(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MedicalProfile:
    """Return the stored medical profile or an empty profile."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM profiles WHERE user_id = %s",
            (auth.user_id,),
        ).fetchone()

    if row is None:
        return MedicalProfile()

    return MedicalProfile(**dict(row))


@router.put("", response_model=MedicalProfile)
def save_profile(
    profile: MedicalProfile,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MedicalProfile:
    """Create or update the personal medical profile."""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO profiles (
                user_id,
                full_name,
                age,
                birth_date,
                sex,
                blood_type,
                height_cm,
                weight_kg,
                diabetes_status,
                cardiovascular_status,
                chronic_conditions,
                allergies,
                medications,
                family_history,
                lifestyle,
                activity_level,
                smoking_status,
                sleep_hours,
                stress_level,
                family_members,
                notes,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                age = excluded.age,
                birth_date = excluded.birth_date,
                sex = excluded.sex,
                blood_type = excluded.blood_type,
                height_cm = excluded.height_cm,
                weight_kg = excluded.weight_kg,
                diabetes_status = excluded.diabetes_status,
                cardiovascular_status = excluded.cardiovascular_status,
                chronic_conditions = excluded.chronic_conditions,
                allergies = excluded.allergies,
                medications = excluded.medications,
                family_history = excluded.family_history,
                lifestyle = excluded.lifestyle,
                activity_level = excluded.activity_level,
                smoking_status = excluded.smoking_status,
                sleep_hours = excluded.sleep_hours,
                stress_level = excluded.stress_level,
                family_members = excluded.family_members,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                auth.user_id,
                profile.full_name,
                profile.age,
                profile.birth_date,
                profile.sex,
                profile.blood_type,
                profile.height_cm,
                profile.weight_kg,
                profile.diabetes_status,
                profile.cardiovascular_status,
                profile.chronic_conditions,
                profile.allergies,
                profile.medications,
                profile.family_history,
                profile.lifestyle,
                profile.activity_level,
                profile.smoking_status,
                profile.sleep_hours,
                profile.stress_level,
                profile.family_members,
                profile.notes,
            ),
        )
        row = connection.execute(
            "SELECT * FROM profiles WHERE user_id = %s",
            (auth.user_id,),
        ).fetchone()

    if row is None:
        return profile.model_copy(update={"updated_at": datetime.now()})

    return MedicalProfile(**dict(row))
