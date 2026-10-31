"""Database operations for trading account and trade records."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from httpx import RequestError

from database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def _first_row(data: Any, operation: str) -> dict[str, Any]:
    """Validate a Supabase response and return its first row."""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"Supabase {operation} returned no row.")


def sync_account(
    login: int,
    server: str,
    balance: float,
    account_type: str,
    currency: str,
) -> int:
    """Update an existing account or insert it, then return its BIGINT ID."""
    if (
        login <= 0
        or not server.strip()
        or balance < 0
        or not account_type.strip()
        or not currency.strip()
    ):
        raise ValueError("Invalid account login, server, type, currency, or balance.")

    try:
        client = get_supabase_client()
        existing = (
            client.table("trading_accounts")
            .select("account_id")
            .eq("login", login)
            .eq("server", server)
            .limit(1)
            .execute()
        )
        values = {
            "login": login,
            "server": server,
            "account_type": account_type,
            "currency": currency,
            "balance": balance,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows = existing.data or []
        if rows:
            row = _first_row(rows, "account lookup")
            account_id = int(row["account_id"])
            (
                client.table("trading_accounts")
                .update(values)
                .eq("account_id", account_id)
                .execute()
            )
            return account_id

        response = client.table("trading_accounts").insert(values).execute()
        return int(_first_row(response.data, "account insert")["account_id"])
    except Exception:
        logger.exception("Could not sync trading account %s on %s.", login, server)
        raise


def record_account_snapshot(account_id: int, account_status: Mapping[str, Any]) -> None:
    """Persist a balance/equity sample for dashboard history."""
    snapshot = {
        "account_id": account_id,
        "balance": float(account_status["balance"]),
        "equity": float(account_status["equity"]),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if any(snapshot[key] < 0 for key in ("balance", "equity")):
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
) -> int:
    """Insert an opened trade plus its indicator, AI, and market context."""
    context = dict(context_dict or {})
    symbol = str(trade_data["symbol"])
    timeframe = context.get("timeframe")
    market_session = context.get("session_utc")
    if not isinstance(timeframe, str) or not timeframe:
        raise ValueError("Trade context must include a timeframe.")
    if not isinstance(market_session, str) or not market_session:
        raise ValueError("Trade context must include the market session.")

    log_data = {
        "symbol": symbol,
        "timeframe": timeframe,
        "indicators_snapshot": {
            "indicators": dict(indicators_dict),
            "context": context,
        },
        "ai_reasoning": reasoning,
        "market_session": market_session,
    }

    for attempt in range(3):
        try:
            client = get_supabase_client()
            existing_trade = (
                client.table("trades")
                .select("trade_id")
                .eq("account_id", trade_data["account_id"])
                .eq("ticket", trade_data["ticket"])
                .limit(1)
                .execute()
            )
            trade_rows = existing_trade.data or []
            if trade_rows:
                trade_id = int(
                    _first_row(trade_rows, "trade lookup")["trade_id"]
                )
            else:
                trade_response = (
                    client.table("trades").insert(dict(trade_data)).execute()
                )
                trade_id = int(
                    _first_row(trade_response.data, "trade insert")["trade_id"]
                )

            log_values = {"trade_id": trade_id, **log_data}
            existing_log = (
                client.table("ai_trade_logs")
                .select("log_id")
                .eq("trade_id", trade_id)
                .limit(1)
                .execute()
            )
            log_rows = existing_log.data or []
            if log_rows:
                log_id = int(_first_row(log_rows, "AI trade log lookup")["log_id"])
                (
                    client.table("ai_trade_logs")
                    .update(log_data)
                    .eq("log_id", log_id)
                    .execute()
                )
            else:
                client.table("ai_trade_logs").insert(log_values).execute()
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
                    "close_time": datetime.now(timezone.utc).isoformat(),
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