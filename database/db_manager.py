"""Database operations for trading account and trade records."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def _first_row(data: Any, operation: str) -> dict[str, Any]:
    """Validate a Supabase response and return its first row."""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"Supabase {operation} returned no row.")


def sync_account(login: int, server: str, balance: float) -> str:
    """Insert or update a trading account and return its database ID."""
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
                    "balance": balance,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="login,server",
            )
            .execute()
        )
        return str(_first_row(response.data, "account sync")["id"])
    except Exception:
        logger.exception("Could not sync trading account %s on %s.", login, server)
        raise


def record_trade_open(
    trade_data: Mapping[str, Any],
    indicators_dict: Mapping[str, Any],
    reasoning: str,
) -> str:
    """Insert an opened trade and its indicator/reasoning snapshot."""
    try:
        trade_response = (
            get_supabase_client().table("trades").insert(dict(trade_data)).execute()
        )
        trade_id = str(_first_row(trade_response.data, "trade insert")["id"])
        log_response = (
            get_supabase_client()
            .table("ai_trade_logs")
            .insert(
                {
                    "trade_id": trade_id,
                    "indicators": dict(indicators_dict),
                    "timeframe": trade_data.get("timeframe"),
                    "reasoning": reasoning,
                }
            )
            .execute()
        )
        _first_row(log_response.data, "AI trade log insert")
        logger.info("Recorded opened trade ticket=%s id=%s.", trade_data.get("ticket"), trade_id)
        return trade_id
    except Exception:
        logger.exception(
            "Could not fully record opened trade ticket=%s.", trade_data.get("ticket")
        )
        raise


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