"""Admin notifications for registration applications."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import load_settings
from app.services.email_service import send_admin_notification_email, smtp_configured


def _build_message(user: dict[str, Any]) -> str:
    lines = [
        f"Имя из заявки: {user.get('display_name') or 'не указано'}",
        f"Email: {user.get('email', '')}",
    ]

    if user.get("ai_suggested_name"):
        lines.append(f"AI-ФИО: {user['ai_suggested_name']}")
    if user.get("ai_confidence"):
        lines.append(f"Доверие: {user['ai_confidence']}")
    if user.get("ai_email_analysis"):
        lines.append(f"Анализ: {user['ai_email_analysis']}")

    recommendation = user.get("recommendation")
    if recommendation:
        lines.append(f"Рекомендация: {recommendation}")

    settings = load_settings()
    admin_url = f"{settings.frontend_url.rstrip('/')}/admin"
    lines.append(f"Панель: {admin_url}")
    return "\n".join(lines)


def notify_admin_new_application(user: dict[str, Any]) -> dict[str, Any]:
    """Notify the administrator about a new registration application."""
    settings = load_settings()
    title = "Новая заявка на регистрацию"
    message = _build_message(user)
    results: dict[str, Any] = {}

    if settings.ops_notify_url and settings.ops_token:
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    settings.ops_notify_url,
                    headers={
                        "X-Ops-Token": settings.ops_token,
                        "Content-Type": "application/json",
                    },
                    json={"title": title, "message": message},
                )
            results["ops_notify"] = {
                "ok": response.is_success,
                "status_code": response.status_code,
            }
        except httpx.HTTPError as error:
            results["ops_notify"] = {"ok": False, "error": str(error)}

    if settings.admin_email and smtp_configured():
        try:
            send_admin_notification_email(
                recipient=settings.admin_email,
                subject=title,
                body=message,
            )
            results["email"] = {"ok": True}
        except Exception as error:  # noqa: BLE001
            results["email"] = {"ok": False, "error": str(error)}

    return results
