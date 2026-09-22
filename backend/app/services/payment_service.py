"""YooKassa payment gateway for wallet top-ups."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.config import Settings, load_settings
from app.database import get_connection
from app.services.wallet_service import WalletSnapshot, _apply_credit_delta

YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"
PAYMENT_PROVIDER = "yookassa"


class PaymentGatewayError(Exception):
    """Raised when the payment provider returns an error."""


class PaymentPackageNotFoundError(Exception):
    """Raised when an unknown top-up package is requested."""


class PaymentOrderNotFoundError(Exception):
    """Raised when a payment order cannot be found."""


@dataclass(frozen=True, slots=True)
class TopUpPackage:
    """Predefined wallet top-up package."""

    id: str
    credits: int
    amount_rub: Decimal
    title: str


TOP_UP_PACKAGES: tuple[TopUpPackage, ...] = (
    TopUpPackage("pack_100", 100, Decimal("10.00"), "100 кредитов"),
    TopUpPackage("pack_500", 500, Decimal("50.00"), "500 кредитов"),
    TopUpPackage("pack_1000", 1000, Decimal("100.00"), "1000 кредитов"),
    TopUpPackage("pack_2500", 2500, Decimal("250.00"), "2500 кредитов"),
)

_PACKAGE_BY_ID = {package.id: package for package in TOP_UP_PACKAGES}


def get_payment_gateway_status(settings: Settings | None = None) -> str:
    """Return payment gateway availability for the UI."""
    runtime = settings or load_settings()
    if (
        runtime.payment_gateway_enabled
        and runtime.yookassa_shop_id
        and runtime.yookassa_secret_key
    ):
        return "enabled"
    return "coming_soon"


def list_top_up_packages() -> list[TopUpPackage]:
    """Return available top-up packages."""
    return list(TOP_UP_PACKAGES)


def get_top_up_package(package_id: str) -> TopUpPackage:
    """Return one package or raise if it is unknown."""
    package = _PACKAGE_BY_ID.get(package_id)
    if package is None:
        raise PaymentPackageNotFoundError("Неизвестный пакет пополнения.")
    return package


def create_payment_order(*, user_id: str, package_id: str) -> dict[str, Any]:
    """Create a pending payment and request a YooKassa confirmation URL."""
    settings = load_settings()
    if get_payment_gateway_status(settings) != "enabled":
        raise PaymentGatewayError("Онлайн-оплата пока недоступна.")

    package = get_top_up_package(package_id)
    order_id = str(uuid.uuid4())
    idempotency_key = str(uuid.uuid4())
    return_url = (
        f"{settings.frontend_url.rstrip('/')}/?view=settings&tab=billing"
        f"&payment=return&order_id={order_id}"
    )

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO payment_orders (
                id,
                user_id,
                package_id,
                amount_rub,
                credits,
                status,
                provider,
                idempotency_key
            )
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
            """,
            (
                order_id,
                user_id,
                package.id,
                package.amount_rub,
                package.credits,
                PAYMENT_PROVIDER,
                idempotency_key,
            ),
        )

    payload = _create_yookassa_payment(
        settings=settings,
        order_id=order_id,
        user_id=user_id,
        package=package,
        return_url=return_url,
        idempotency_key=idempotency_key,
    )

    provider_payment_id = str(payload["id"])
    confirmation_url = payload["confirmation"]["confirmation_url"]

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE payment_orders
            SET provider_payment_id = %s,
                confirmation_url = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (provider_payment_id, confirmation_url, order_id),
        )

    return get_payment_order(order_id=order_id, user_id=user_id)


def get_payment_order(*, order_id: str, user_id: str) -> dict[str, Any]:
    """Return one payment order for the authenticated user."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                user_id,
                package_id,
                amount_rub,
                credits,
                status,
                provider,
                provider_payment_id,
                confirmation_url,
                created_at,
                updated_at,
                paid_at
            FROM payment_orders
            WHERE id = %s AND user_id = %s
            """,
            (order_id, user_id),
        ).fetchone()

    if row is None:
        raise PaymentOrderNotFoundError("Платёж не найден.")
    return _serialize_payment_order(row)


def handle_yookassa_notification(payload: dict[str, Any]) -> None:
    """Process a YooKassa webhook notification.

    Auto-crediting is disabled unless ``YOOKASSA_WEBHOOK_ENABLED=true``.
    When enabled, the payment is re-fetched from YooKassa and only credited
    after it is confirmed as ``succeeded`` (payload is not trusted blindly).
    """
    settings = load_settings()
    if not settings.yookassa_webhook_enabled:
        return

    event = str(payload.get("event", ""))
    payment_object = payload.get("object")
    if not isinstance(payment_object, dict):
        return

    provider_payment_id = str(payment_object.get("id", ""))
    if not provider_payment_id:
        return

    if event == "payment.succeeded":
        if not _verify_yookassa_payment(settings, provider_payment_id):
            return
        complete_payment_order(provider_payment_id=provider_payment_id)
        return

    if event == "payment.canceled":
        mark_payment_order_canceled(provider_payment_id=provider_payment_id)


def _verify_yookassa_payment(
    settings: Settings,
    provider_payment_id: str,
) -> bool:
    """Confirm with YooKassa that the payment is actually succeeded."""
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                f"{YOOKASSA_API_URL}/{provider_payment_id}",
                auth=(settings.yookassa_shop_id, settings.yookassa_secret_key),
            )
    except httpx.HTTPError:
        return False

    if response.status_code != 200:
        return False

    payment = response.json()
    return (
        isinstance(payment, dict)
        and str(payment.get("status")) == "succeeded"
    )


def complete_payment_order(*, provider_payment_id: str) -> WalletSnapshot | None:
    """Mark an order as paid and credit the user's wallet once."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, user_id, credits, status
            FROM payment_orders
            WHERE provider_payment_id = %s
            FOR UPDATE
            """,
            (provider_payment_id,),
        ).fetchone()
        if row is None:
            return None

        if str(row["status"]) == "succeeded":
            return None

        if str(row["status"]) != "pending":
            return None

        connection.execute(
            """
            UPDATE payment_orders
            SET status = 'succeeded',
                paid_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (row["id"],),
        )

    return _apply_credit_delta(
        user_id=str(row["user_id"]),
        delta_credits=int(row["credits"]),
        reason="payment_top_up",
        reference_id=f"yookassa:{provider_payment_id}",
    )


def mark_payment_order_canceled(*, provider_payment_id: str) -> None:
    """Mark a pending payment order as canceled."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE payment_orders
            SET status = 'canceled',
                updated_at = NOW()
            WHERE provider_payment_id = %s
              AND status = 'pending'
            """,
            (provider_payment_id,),
        )


def _create_yookassa_payment(
    *,
    settings: Settings,
    order_id: str,
    user_id: str,
    package: TopUpPackage,
    return_url: str,
    idempotency_key: str,
) -> dict[str, Any]:
    request_payload = {
        "amount": {
            "value": f"{package.amount_rub:.2f}",
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "description": f"Пополнение баланса: {package.title}",
        "metadata": {
            "order_id": order_id,
            "user_id": user_id,
            "package_id": package.id,
            "credits": str(package.credits),
        },
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            YOOKASSA_API_URL,
            auth=(settings.yookassa_shop_id, settings.yookassa_secret_key),
            headers={
                "Idempotence-Key": idempotency_key,
                "Content-Type": "application/json",
            },
            json=request_payload,
        )

    if response.status_code >= 400:
        raise PaymentGatewayError(
            f"YooKassa вернула ошибку HTTP {response.status_code}."
        )

    payload = response.json()
    if (
        "confirmation" not in payload
        or "confirmation_url" not in payload["confirmation"]
    ):
        raise PaymentGatewayError("YooKassa не вернула ссылку для оплаты.")
    return payload


def _serialize_payment_order(row: dict[str, Any]) -> dict[str, Any]:
    amount_rub = row["amount_rub"]
    if not isinstance(amount_rub, Decimal):
        amount_rub = Decimal(str(amount_rub))

    return {
        "id": str(row["id"]),
        "package_id": str(row["package_id"]),
        "amount_rub": float(amount_rub),
        "credits": int(row["credits"]),
        "status": str(row["status"]),
        "provider": str(row["provider"]),
        "confirmation_url": row.get("confirmation_url"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "paid_at": row.get("paid_at"),
    }
