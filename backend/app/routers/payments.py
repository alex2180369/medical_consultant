"""Payment provider webhooks."""

from typing import Any

from fastapi import APIRouter, Request, Response

from app.services.payment_service import handle_yookassa_notification

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/yookassa/webhook", status_code=200)
async def yookassa_webhook(request: Request) -> Response:
    """Handle YooKassa payment notifications."""
    payload: dict[str, Any] = await request.json()
    handle_yookassa_notification(payload)
    return Response(status_code=200)
