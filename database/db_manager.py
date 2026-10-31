"""Database operations for trading account and trade records."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from httpx import RequestError

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

ACCOUNT_BALANCE_COLUMN = "balance"
ACCOUNT_CONFLICT_TARGET = "login,server"


def _first_row(data: Any, operation: str) -> dict[str, Any]:
    """Validate a Supabase response and return its first row."""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"Supabase {operation} returned no row.")


def sync_account(login: int, server: str, balance: float) -> str:
    """Upsert by the schema's login/server unique key and return the account ID.

    PostgREST ``on_conflict`` takes the unique key's column list, not the
    PostgreSQL constraint name.
    """
    if login <= 0 or not server.strip() or balance < 0:
        raise ValueError("Invalid account login, server, or balance.")

    try:
        response = (
            get_supabase_client()
            .table("trading_accounts")
            .upsert(
                {
                    "login": login,
                    "server": server,
                    ACCOUNT_BALANCE_COLUMN: balance,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict=ACCOUNT_CONFLICT_TARGET,
            )
            .execute()
        )
        row = _first_row(response.data, "account sync")
        return str(row.get("account_id") or row.get("id"))
    except Exception:
        logger.exception("Could not sync trading account %s on %s.", login, server)
        raise


def record_account_snapshot(account_id: str, account_status: Mapping[str, Any]) -> None:
    """Persist a balance/equity sample for dashboard history."""
    snapshot = {
        "account_id": account_id,
        "balance": float(account_status["balance"]),
        "equity": float(account_status["equity"]),
        "margin": float(account_status["margin"]),
        "free_margin": float(account_status["free_margin"]),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    if any(snapshot[key] < 0 for key in ("balance", "equity", "margin", "free_margin")):
        raise ValueError("Account snapshot values cannot be negative.")
    try:
        get_supabase_client().table("account_equity_snapshots").insert(snapshot).execute()
    except Exception:
        logger.exception("Could not record account snapshot for account %s.", account_id)
        raise


def record_trade_open(
    trade_data: Mapping[str, Any],
    indicators_dict: Mapping[str, Any],
    reasoning: str,
    context_dict: Mapping[str, Any] | None = None,
) -> str:
    """Insert an opened trade plus its indicator, AI, and market context."""
    context = dict(context_dict or {})
    for attempt in range(3):
        try:
            trade_response = (
                get_supabase_client()
                .table("trades")
                .upsert({**dict(trade_data), "context": context}, on_conflict="ticket")
                .execute()
            )
            trade_id = str(_first_row(trade_response.data, "trade upsert")["id"])
            log_response = (
                get_supabase_client()
                .table("ai_trade_logs")
                .upsert(
                    {
                        "trade_id": trade_id,
                        "indicators": dict(indicators_dict),
                        "context": context,
                        "timeframe": trade_data.get("timeframe"),
                        "reasoning": reasoning,
                    },
                    on_conflict="trade_id",
                )
                .execute()
            )
            _first_row(log_response.data, "AI trade log upsert")
            logger.info(
                "Recorded opened trade ticket=%s id=%s.",
                trade_data.get("ticket"),
                trade_id,
            )
            return trade_id
        except RequestError:
            if attempt == 2:
                logger.exception(
                    "Network retries exhausted recording trade ticket=%s.",
                    trade_data.get("ticket"),
                )
                raise
            delay = 2**attempt
            logger.warning(
                "Supabase request failed for ticket=%s; retrying in %s seconds.",
                trade_data.get("ticket"),
                delay,
                exc_info=True,
            )
            time.sleep(delay)
        except Exception:
            logger.exception(
                "Could not fully record opened trade ticket=%s.",
                trade_data.get("ticket"),
            )
            raise

    raise RuntimeError("Unexpected end of trade persistence retry loop.")


def record_trade_close(
    ticket: int,
    close_price: float,
    profit_loss: float,
    exit_reason: str,
) -> bool:
    """Close the matching open trade; return whether a row was updated."""
    if ticket <= 0 or close_price <= 0:
        raise ValueError("Ticket and close price must be positive.")

    try:
        response = (
            get_supabase_client()
            .table("trades")
            .update(
                {
                    "close_price": close_price,
                    "profit_loss": profit_loss,
                    "exit_reason": exit_reason,
                    "closed_at": datetime.now(timezone.utc).isoformat(),
                    "status": "closed",
                }
            )
            .eq("ticket", ticket)
            .eq("status", "open")
            .execute()
        )
        updated = bool(response.data)
        if updated:
            logger.info("Recorded close for ticket=%s, P/L=%.2f.", ticket, profit_loss)
        return updated
    except Exception:
        logger.exception("Could not record close for ticket=%s.", ticket)
        raise


def get_open_trade_tickets() -> list[int]:
    """Return MT5 position tickets that are still marked open in Supabase."""
    try:
        response = (
            get_supabase_client()
            .table("trades")
            .select("ticket")
            .eq("status", "open")
            .execute()
        )
        return [int(row["ticket"]) for row in response.data or []]
    except Exception:
        logger.exception("Could not fetch open trade tickets.")
        raise