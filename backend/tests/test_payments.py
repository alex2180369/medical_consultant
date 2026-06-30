"""Tests for YooKassa payment gateway (phase 3)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import ensure_user_profile, get_connection
from app.services.payment_service import (
    PaymentGatewayError,
    complete_payment_order,
    create_payment_order,
    get_payment_gateway_status,
    handle_yookassa_notification,
)
from tests.test_settings import make_test_settings


def _mock_yookassa_response(*, payment_id: str, confirmation_url: str) -> dict:
    return {
        "id": payment_id,
        "status": "pending",
        "confirmation": {
            "type": "redirect",
            "confirmation_url": confirmation_url,
        },
    }


def test_payment_gateway_status_disabled_by_default() -> None:
    """Gateway should stay unavailable without credentials."""
    settings = make_test_settings(
        payment_gateway_enabled=False,
        yookassa_shop_id=None,
        yookassa_secret_key=None,
    )
    assert get_payment_gateway_status(settings) == "coming_soon"


def test_payment_gateway_status_enabled_with_credentials() -> None:
    """Gateway should become enabled when configured."""
    settings = make_test_settings(
        payment_gateway_enabled=True,
        yookassa_shop_id="shop-id",
        yookassa_secret_key="secret-key",
    )
    assert get_payment_gateway_status(settings) == "enabled"


def test_payment_packages_endpoint(auth_client: TestClient) -> None:
    """Packages endpoint should expose predefined top-up options."""
    response = auth_client.get("/api/account/payments/packages")

    assert response.status_code == 200
    payload = response.json()
    assert payload["payment_gateway_status"] == "coming_soon"
    assert len(payload["packages"]) >= 3
    assert payload["packages"][0]["credits"] == 100


def test_create_payment_requires_enabled_gateway(auth_client: TestClient) -> None:
    """Payment creation should fail when the gateway is disabled."""
    response = auth_client.post(
        "/api/account/payments",
        json={"package_id": "pack_100"},
    )

    assert response.status_code == 503


@patch("app.services.payment_service.load_settings")
@patch("app.services.payment_service.httpx.Client")
def test_create_payment_order_returns_confirmation_url(
    mock_client_cls,
    mock_load_settings,
    auth_client: TestClient,
) -> None:
    """Enabled gateway should create an order and return confirmation URL."""
    mock_load_settings.return_value = make_test_settings(
        payment_gateway_enabled=True,
        yookassa_shop_id="shop-id",
        yookassa_secret_key="secret-key",
        frontend_url="https://example.test",
    )

    mock_response = httpx.Response(
        200,
        json=_mock_yookassa_response(
            payment_id="yk-test-payment",
            confirmation_url="https://pay.yookassa.ru/confirm",
        ),
        request=httpx.Request("POST", "https://api.yookassa.ru/v3/payments"),
    )
    mock_client_cls.return_value.__enter__.return_value.post.return_value = (
        mock_response
    )

    response = auth_client.post(
        "/api/account/payments",
        json={"package_id": "pack_100"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["credits"] == 100
    assert payload["confirmation_url"] == "https://pay.yookassa.ru/confirm"


def test_yookassa_webhook_credits_wallet_once(auth_client: TestClient) -> None:
    """Successful webhook should credit the wallet exactly once."""
    user_id = "test-user"
    ensure_user_profile(user_id, email="test@example.com", display_name="Test")

    order_id = str(uuid.uuid4())
    provider_payment_id = f"yk-{uuid.uuid4().hex[:12]}"

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
                provider_payment_id,
                idempotency_key
            )
            VALUES (%s, %s, 'pack_100', %s, 100, 'pending', 'yookassa', %s, %s)
            """,
            (order_id, user_id, Decimal("10.00"), provider_payment_id, str(uuid.uuid4())),
        )

    wallet_before = auth_client.get("/api/account/wallet").json()["credits_balance"]

    webhook_payload = {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": provider_payment_id,
            "status": "succeeded",
            "metadata": {"order_id": order_id, "user_id": user_id},
        },
    }

    first = auth_client.post("/api/payments/yookassa/webhook", json=webhook_payload)
    second = auth_client.post("/api/payments/yookassa/webhook", json=webhook_payload)

    assert first.status_code == 200
    assert second.status_code == 200

    wallet_after = auth_client.get("/api/account/wallet").json()["credits_balance"]
    assert wallet_after == wallet_before + 100

    order_response = auth_client.get(f"/api/account/payments/{order_id}")
    assert order_response.status_code == 200
    assert order_response.json()["status"] == "succeeded"


def test_complete_payment_order_is_idempotent() -> None:
    """Direct completion helper should ignore already paid orders."""
    user_id = f"pay-user-{uuid.uuid4().hex[:8]}"
    ensure_user_profile(user_id, email=f"{user_id}@example.com", display_name="Pay")
    provider_payment_id = f"yk-{uuid.uuid4().hex[:12]}"

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
                provider_payment_id,
                idempotency_key,
                paid_at
            )
            VALUES (%s, %s, 'pack_100', %s, 100, 'succeeded', 'yookassa', %s, %s, NOW())
            """,
            (
                str(uuid.uuid4()),
                user_id,
                Decimal("10.00"),
                provider_payment_id,
                str(uuid.uuid4()),
            ),
        )

    assert complete_payment_order(provider_payment_id=provider_payment_id) is None


def test_handle_yookassa_notification_marks_canceled(auth_client: TestClient) -> None:
    """Canceled webhook should update pending order status."""
    user_id = "test-user"
    ensure_user_profile(user_id, email="test@example.com", display_name="Test")
    order_id = str(uuid.uuid4())
    provider_payment_id = f"yk-{uuid.uuid4().hex[:12]}"

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
                provider_payment_id,
                idempotency_key
            )
            VALUES (%s, %s, 'pack_500', %s, 500, 'pending', 'yookassa', %s, %s)
            """,
            (order_id, user_id, Decimal("50.00"), provider_payment_id, str(uuid.uuid4())),
        )

    handle_yookassa_notification(
        {
            "event": "payment.canceled",
            "object": {"id": provider_payment_id, "status": "canceled"},
        }
    )

    order_response = auth_client.get(f"/api/account/payments/{order_id}")
    assert order_response.status_code == 200
    assert order_response.json()["status"] == "canceled"
