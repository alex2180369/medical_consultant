"""Shared billing HTTP helpers."""

from fastapi import HTTPException, status

from app.services.wallet_service import InsufficientCreditsError


def http_error_for_insufficient_credits(error: InsufficientCreditsError) -> HTTPException:
    """Convert wallet errors into HTTP 402 responses."""
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=error.message,
    )
