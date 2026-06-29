"""User credit wallet and billing charges."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.database import get_connection
from app.services.pricing import CREDITS_PER_RUB

STARTER_CREDITS = 100
FREE_TURNS_AT_ZERO = 2


class InsufficientCreditsError(Exception):
    """Raised when a user cannot afford an LLM operation."""

    def __init__(
        self,
        message: str = (
            "Недостаточно кредитов. Пополните баланс или используйте "
            "бесплатные ходы при нулевом балансе."
        ),
    ) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class WalletSnapshot:
    """Current wallet state for one user."""

    user_id: str
    credits_balance: int
    free_turns_remaining: int


@dataclass(frozen=True, slots=True)
class ChargeResult:
    """Result of charging credits for one usage event."""

    charged_credits: int
    estimated_credits: int
    balance_remaining: int
    free_turns_remaining: int
    used_free_turn: bool
    is_charged: bool


def get_wallet(user_id: str) -> WalletSnapshot:
    """Return wallet state, creating a row if needed."""
    wallet = _fetch_wallet(user_id)
    if wallet is None:
        _create_wallet(user_id)
        wallet = _fetch_wallet(user_id)
    if wallet is None:
        raise RuntimeError("Failed to initialize user wallet.")
    return wallet


def get_wallet_balance(user_id: str) -> WalletSnapshot:
    """Return wallet snapshot for API responses."""
    return get_wallet(user_id)


def ensure_llm_allowed(user_id: str) -> None:
    """Reject billable LLM calls when the wallet is empty and free turns are gone."""
    wallet = get_wallet(user_id)
    if wallet.credits_balance > 0 or wallet.free_turns_remaining > 0:
        return
    raise InsufficientCreditsError()


def grant_welcome_bonus(user_id: str) -> WalletSnapshot:
    """Grant starter credits once for a newly approved user."""
    if _has_transaction(user_id, "welcome_bonus"):
        return get_wallet(user_id)
    return _apply_credit_delta(
        user_id=user_id,
        delta_credits=STARTER_CREDITS,
        reason="welcome_bonus",
        reference_id=None,
    )


def admin_top_up(
    *,
    user_id: str,
    credits: int,
    admin_id: str,
    note: str = "",
) -> WalletSnapshot:
    """Manually add credits to a user wallet."""
    if credits <= 0:
        raise ValueError("Количество кредитов должно быть больше нуля.")

    reference = f"admin:{admin_id}"
    if note.strip():
        reference = f"{reference}:{note.strip()[:120]}"
    return _apply_credit_delta(
        user_id=user_id,
        delta_credits=credits,
        reason="admin_top_up",
        reference_id=reference,
    )


def apply_usage_charge(
    *,
    user_id: str,
    usage_event_id: int,
    estimated_credits: int,
    billable: bool,
) -> ChargeResult:
    """Charge a logged usage event against the user's wallet."""
    if not billable or estimated_credits <= 0:
        wallet = get_wallet(user_id)
        _mark_usage_charged(usage_event_id, charged_credits=0, is_charged=False)
        return ChargeResult(
            charged_credits=0,
            estimated_credits=estimated_credits,
            balance_remaining=wallet.credits_balance,
            free_turns_remaining=wallet.free_turns_remaining,
            used_free_turn=False,
            is_charged=False,
        )

    with get_connection() as connection:
        wallet_row = connection.execute(
            """
            SELECT credits_balance, free_turns_remaining
            FROM user_wallets
            WHERE user_id = %s
            FOR UPDATE
            """,
            (user_id,),
        ).fetchone()
        if wallet_row is None:
            connection.execute(
                """
                INSERT INTO user_wallets (
                    user_id,
                    credits_balance,
                    free_turns_remaining
                )
                VALUES (%s, 0, %s)
                """,
                (user_id, FREE_TURNS_AT_ZERO),
            )
            wallet_row = connection.execute(
                """
                SELECT credits_balance, free_turns_remaining
                FROM user_wallets
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            ).fetchone()

        balance = int(wallet_row["credits_balance"])
        free_turns = int(wallet_row["free_turns_remaining"])
        charged = 0
        used_free_turn = False
        is_charged = False

        if balance >= estimated_credits:
            charged = estimated_credits
            balance -= estimated_credits
            is_charged = True
        elif balance > 0:
            charged = balance
            balance = 0
            is_charged = True
        elif free_turns > 0:
            free_turns -= 1
            used_free_turn = True
            is_charged = False
        else:
            raise InsufficientCreditsError()

        connection.execute(
            """
            UPDATE user_wallets
            SET credits_balance = %s,
                free_turns_remaining = %s,
                updated_at = NOW()
            WHERE user_id = %s
            """,
            (balance, free_turns, user_id),
        )
        connection.execute(
            """
            UPDATE llm_usage_events
            SET is_charged = %s
            WHERE id = %s
            """,
            (is_charged, usage_event_id),
        )

    return ChargeResult(
        charged_credits=charged,
        estimated_credits=estimated_credits,
        balance_remaining=balance,
        free_turns_remaining=free_turns,
        used_free_turn=used_free_turn,
        is_charged=is_charged,
    )


def list_wallet_transactions(user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent wallet transactions for one user."""
    safe_limit = max(1, min(limit, 100))
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, delta_credits, reason, reference_id, created_at
            FROM wallet_transactions
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_wallet(user_id: str) -> WalletSnapshot | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT user_id, credits_balance, free_turns_remaining
            FROM user_wallets
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return WalletSnapshot(
        user_id=str(row["user_id"]),
        credits_balance=int(row["credits_balance"]),
        free_turns_remaining=int(row["free_turns_remaining"]),
    )


def _create_wallet(user_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_wallets (
                user_id,
                credits_balance,
                free_turns_remaining
            )
            VALUES (%s, 0, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, FREE_TURNS_AT_ZERO),
        )


def _has_transaction(user_id: str, reason: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM wallet_transactions
            WHERE user_id = %s AND reason = %s
            LIMIT 1
            """,
            (user_id, reason),
        ).fetchone()
    return row is not None


def _apply_credit_delta(
    *,
    user_id: str,
    delta_credits: int,
    reason: str,
    reference_id: str | None,
) -> WalletSnapshot:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_wallets (
                user_id,
                credits_balance,
                free_turns_remaining
            )
            VALUES (%s, 0, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, FREE_TURNS_AT_ZERO),
        )
        row = connection.execute(
            """
            UPDATE user_wallets
            SET credits_balance = credits_balance + %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING credits_balance, free_turns_remaining
            """,
            (delta_credits, user_id),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO wallet_transactions (
                user_id,
                delta_credits,
                reason,
                reference_id
            )
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, delta_credits, reason, reference_id),
        )

    return WalletSnapshot(
        user_id=user_id,
        credits_balance=int(row["credits_balance"]),
        free_turns_remaining=int(row["free_turns_remaining"]),
    )


def _mark_usage_charged(
    usage_event_id: int,
    *,
    charged_credits: int,
    is_charged: bool,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE llm_usage_events
            SET is_charged = %s,
                estimated_credits = %s
            WHERE id = %s
            """,
            (is_charged, charged_credits, usage_event_id),
        )


def backfill_wallets_for_approved_users() -> None:
    """Create wallets for approved users and grant missing welcome bonuses."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id
            FROM users
            WHERE status = 'approved'
            """
        ).fetchall()

    for row in rows:
        user_id = str(row["id"])
        _create_wallet(user_id)
        grant_welcome_bonus(user_id)
