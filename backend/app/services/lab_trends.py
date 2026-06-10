"""Utilities for comparing laboratory markers with previous values."""

from sqlite3 import Connection

from app.schemas import LabTrend


def calculate_trend(
    connection: Connection,
    marker_name: str,
    current_value: float,
    current_id: int,
    user_id: str,
) -> LabTrend:
    """Compare a result with the previous value of the same marker."""
    previous = connection.execute(
        """
        SELECT value
        FROM lab_results
        WHERE marker_name = %s AND id != %s AND user_id = %s
        ORDER BY measured_at DESC, id DESC
        LIMIT 1
        """,
        (marker_name, current_id, user_id),
    ).fetchone()

    if previous is None:
        return LabTrend(previous_value=None, delta=None, direction="baseline")

    previous_value = float(previous["value"])
    delta = current_value - previous_value

    if delta > 0:
        direction = "up"
    elif delta < 0:
        direction = "down"
    else:
        direction = "same"

    return LabTrend(previous_value=previous_value, delta=delta, direction=direction)
