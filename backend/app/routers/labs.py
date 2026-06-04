"""Routes for laboratory results and trend tracking."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.database import get_connection
from app.schemas import LabResult, LabResultCreate
from app.services.auth_service import AuthContext, get_auth_context
from app.services.lab_trends import calculate_trend

router = APIRouter(prefix="/labs", tags=["labs"])


@router.get("", response_model=list[LabResult])
def list_lab_results(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[LabResult]:
    """Return laboratory results with trend information."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM lab_results
            WHERE user_id = ?
            ORDER BY measured_at DESC, id DESC
            """,
            (auth.effective_user_id,),
        ).fetchall()

        results = []
        for row in rows:
            data = dict(row)
            trend = calculate_trend(
                connection=connection,
                marker_name=data["marker_name"],
                current_value=float(data["value"]),
                current_id=int(data["id"]),
                user_id=auth.effective_user_id,
            )
            results.append(LabResult(**data, trend=trend))

    return results


@router.post("", response_model=LabResult, status_code=201)
def create_lab_result(
    payload: LabResultCreate,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> LabResult:
    """Store a laboratory marker and compare it with previous values."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO lab_results (
                user_id,
                marker_name,
                value,
                unit,
                reference_range,
                measured_at,
                comment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                auth.effective_user_id,
                payload.marker_name,
                payload.value,
                payload.unit,
                payload.reference_range,
                payload.measured_at.isoformat(),
                payload.comment,
            ),
        )
        result_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT * FROM lab_results WHERE id = ? AND user_id = ?",
            (result_id, auth.effective_user_id),
        ).fetchone()
        trend = calculate_trend(
            connection=connection,
            marker_name=payload.marker_name,
            current_value=payload.value,
            current_id=result_id,
            user_id=auth.effective_user_id,
        )

    return LabResult(**dict(row), trend=trend)
