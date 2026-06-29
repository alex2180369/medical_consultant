"""Tests for wallet billing (phase 1)."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import ensure_user_profile
from app.services.llm_router import LlmTask
from app.services.pricing import CREDITS_PER_RUB
from app.services.usage_service import UsageContext, log_llm_usage
from app.services.wallet_service import (
    FREE_TURNS_AT_ZERO,
    STARTER_CREDITS,
    InsufficientCreditsError,
    admin_top_up,
    ensure_llm_allowed,
    get_wallet,
    grant_welcome_bonus,
)

ADMIN_EMAIL = "admin@example.com"
os.environ["ADMIN_EMAIL"] = ADMIN_EMAIL


def test_grant_welcome_bonus_is_idempotent(auth_client) -> None:
    """Welcome bonus should be granted only once."""
    before = get_wallet("test-user").credits_balance
    after_first = grant_welcome_bonus("test-user").credits_balance
    after_second = grant_welcome_bonus("test-user").credits_balance

    assert after_first == after_second
    assert after_first >= before


def _ensure_test_profile(user_id: str) -> None:
    ensure_user_profile(user_id, email=f"{user_id}@example.com", display_name="Test")


def test_free_turns_allow_llm_at_zero_balance(auth_client) -> None:
    """Users with zero balance should still have free turns."""
    user_id = f"zero-{uuid.uuid4().hex[:8]}"
    _ensure_test_profile(user_id)

    from app.database import get_connection

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_wallets (user_id, credits_balance, free_turns_remaining)
            VALUES (%s, 0, %s)
            """,
            (user_id, FREE_TURNS_AT_ZERO),
        )

    ensure_llm_allowed(user_id)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE user_wallets
            SET free_turns_remaining = 0
            WHERE user_id = %s
            """,
            (user_id,),
        )

    with pytest.raises(InsufficientCreditsError):
        ensure_llm_allowed(user_id)


def test_log_llm_usage_charges_wallet(auth_client) -> None:
    """Billable usage should deduct credits from wallet."""
    wallet_before = admin_top_up(
        user_id="test-user",
        credits=500,
        admin_id="admin-user",
        note="test setup",
    )

    result = log_llm_usage(
        context=UsageContext(
            user_id="test-user",
            operation_type="chat_turn",
            task=LlmTask.SYMPTOMS,
        ),
        provider="aitunnel.ru",
        model="qwen3.5-plus-02-15",
        prompt_tokens=5000,
        completion_tokens=2000,
        total_tokens=7000,
    )

    assert result is not None
    assert result.charged_credits > 0
    assert result.balance_remaining == wallet_before.credits_balance - result.charged_credits


def test_free_turn_used_when_balance_zero(auth_client) -> None:
    """Zero balance should consume a free turn instead of credits."""
    user_id = f"free-turn-{uuid.uuid4().hex[:8]}"
    _ensure_test_profile(user_id)
    get_wallet(user_id)

    from app.database import get_connection

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE user_wallets
            SET credits_balance = 0,
                free_turns_remaining = 1
            WHERE user_id = %s
            """,
            (user_id,),
        )

    result = log_llm_usage(
        context=UsageContext(
            user_id=user_id,
            operation_type="chat_turn",
            task=LlmTask.SYMPTOMS,
        ),
        provider="aitunnel.ru",
        model="qwen3.5-plus-02-15",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
    )

    assert result is not None
    assert result.used_free_turn is True
    assert result.charged_credits == 0
    assert result.free_turns_remaining == 0


def test_wallet_endpoint(auth_client) -> None:
    """Wallet API should expose balance and exchange rate."""
    response = auth_client.get("/api/account/wallet")

    assert response.status_code == 200
    payload = response.json()
    assert payload["credits_per_rub"] == CREDITS_PER_RUB
    assert payload["starter_credits"] == STARTER_CREDITS
    assert payload["payment_gateway_status"] == "coming_soon"


def test_admin_top_up_endpoint(client: TestClient) -> None:
    """Admin should be able to top up a user's wallet."""
    email = f"wallet-user-{uuid.uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/auth/register",
        json={
            "name": "Wallet User",
            "email": email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "ignored"},
    )
    if login_response.status_code != 200:
        pytest.skip("Admin login is not configured in this test environment.")

    admin_token = login_response.json()["access_token"]
    pending = client.get(
        "/api/admin/applications",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pending.status_code == 200
    application = next(item for item in pending.json() if item["email"] == email)

    approved = client.post(
        f"/api/admin/users/{application['id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approved.status_code == 200

    top_up_response = client.post(
        f"/api/admin/users/{application['id']}/wallet/top-up",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"credits": 250, "note": "manual bonus"},
    )

    assert top_up_response.status_code == 200
    payload = top_up_response.json()
    assert payload["credits_balance"] >= 250 + STARTER_CREDITS


def test_admin_top_up_service(auth_client) -> None:
    """Direct admin top-up should increase wallet balance."""
    user_id = f"top-up-{uuid.uuid4().hex[:8]}"
    _ensure_test_profile(user_id)
    get_wallet(user_id)
    wallet = admin_top_up(
        user_id=user_id,
        credits=300,
        admin_id="admin-user",
        note="test",
    )
    assert wallet.credits_balance == 300
