"""Ephemeral dialog mode for special demo users (e.g. «Апрель»)."""

from __future__ import annotations

from dataclasses import dataclass

from app.database import get_connection
from app.schemas import MedicalProfile
from app.services.wallet_service import WalletSnapshot, set_wallet_balance

# Display names that use ephemeral (no-history) dialogs.
EPHEMERAL_DIALOG_DISPLAY_NAMES = frozenset({"Апрель"})
EPHEMERAL_DIALOG_CREDITS = 300


@dataclass(frozen=True, slots=True)
class NewDialogResult:
    """Result of starting a fresh ephemeral dialog."""

    profile: MedicalProfile
    wallet: WalletSnapshot
    deleted_consultations: int
    deleted_complaints: int


def is_ephemeral_dialog_user(user_id: str) -> bool:
    """Return True when the user should not keep dialog history."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT display_name FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT display_name FROM profiles WHERE user_id = %s",
                (user_id,),
            ).fetchone()
    if row is None:
        return False
    return str(row["display_name"] or "").strip() in EPHEMERAL_DIALOG_DISPLAY_NAMES


def is_ephemeral_dialog_name(name: str) -> bool:
    """Frontend-facing check by display name from the session."""
    return name.strip() in EPHEMERAL_DIALOG_DISPLAY_NAMES


def reset_health_questionnaire(user_id: str) -> MedicalProfile:
    """Clear medical questionnaire fields while keeping account identity."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE profiles
            SET full_name = '',
                age = NULL,
                birth_date = NULL,
                sex = '',
                blood_type = '',
                height_cm = NULL,
                weight_kg = NULL,
                diabetes_status = '',
                cardiovascular_status = '',
                chronic_conditions = '',
                allergies = '',
                medications = '',
                family_history = '',
                lifestyle = '',
                activity_level = '',
                smoking_status = '',
                sleep_hours = NULL,
                stress_level = '',
                family_members = NULL,
                notes = '',
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = connection.execute(
            "SELECT * FROM profiles WHERE user_id = %s",
            (user_id,),
        ).fetchone()

    if row is None:
        return MedicalProfile()
    return MedicalProfile(**dict(row))


def delete_user_dialogs(user_id: str) -> tuple[int, int]:
    """Delete all consultations and complaint history for one user."""
    with get_connection() as connection:
        consultations = connection.execute(
            "DELETE FROM consultations WHERE user_id = %s",
            (user_id,),
        ).rowcount
        complaints = connection.execute(
            "DELETE FROM complaints WHERE user_id = %s",
            (user_id,),
        ).rowcount
    return int(consultations or 0), int(complaints or 0)


def complete_consultation_without_history(
    *,
    consultation_id: int,
    user_id: str,
) -> None:
    """Mark a consultation completed without writing a history complaint."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE consultations
            SET status = 'completed',
                complaint_id = NULL
            WHERE id = %s AND user_id = %s
            """,
            (consultation_id, user_id),
        )


def start_new_ephemeral_dialog(user_id: str) -> NewDialogResult:
    """
    Start a fresh dialog for an ephemeral user.

    Deletes old dialogs/history, resets the health questionnaire, and restores
    the non-burnable dialog balance of EPHEMERAL_DIALOG_CREDITS.
    """
    if not is_ephemeral_dialog_user(user_id):
        raise PermissionError(
            "Новый ephemeral-диалог доступен только специальным пользователям."
        )

    deleted_consultations, deleted_complaints = delete_user_dialogs(user_id)
    profile = reset_health_questionnaire(user_id)
    wallet = set_wallet_balance(
        user_id=user_id,
        credits=EPHEMERAL_DIALOG_CREDITS,
        reason="ephemeral_dialog_reset",
    )
    return NewDialogResult(
        profile=profile,
        wallet=wallet,
        deleted_consultations=deleted_consultations,
        deleted_complaints=deleted_complaints,
    )
