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


def get_auto_trading_setting(account_id: int) -> bool:
    """Read the account-level trading switch; fail closed if the row is missing."""
    try:
        response = (
            get_supabase_client()
            .table("trading_accounts")
            .select("auto_trading")
            .eq("account_id", account_id)
            .single()
            .execute()
        )
        row = _first_row(response.data, "auto-trading setting lookup")
        return row.get("auto_trading") is True
    except Exception:
        logger.exception("Could not read auto-trading setting for account %s.", account_id)
        raise


def record_account_snapshot(account_id: int, account_status: Mapping[str, Any]) -> None:
    """Persist a balance/equity sample for dashboard history."""
    snapshot = {
        "account_id": account_id,
        "balance": float(account_status["balance"]),
        "equity": float(account_status["equity"]),
        "margin": float(account_status["margin"]),
        "free_margin": float(account_status["free_margin"]),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if snapshot["margin"] < 0:
        raise ValueError("Account margin cannot be negative.")
    try:
        get_supabase_client().table("account_equity_snapshots").insert(snapshot).execute()
    except Exception:
        logger.exception("Could not record account snapshot for account %s.", account_id)
        raise


def record_market_scan(account_id: int, scan: Mapping[str, Any]) -> None:
    """Upsert the latest market scan row for one account/symbol pair."""
    required = {
        "symbol",
        "timeframe",
        "last_price",
        "rsi",
        "ema_trend",
        "signal_status",
        "reason",
    }
    if required.difference(scan):
        raise ValueError("Market scan is missing required fields.")
    values = {
        "account_id": account_id,
        **dict(scan),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        (
            get_supabase_client()
            .table("dashboard_market_scans")
            .upsert(values, on_conflict="account_id,symbol")
            .execute()
        )
    except Exception:
        logger.exception(
            "Could not record market scan for account %s symbol %s.",
            account_id,
            scan.get("symbol"),
        )
        raise


def get_pending_bot_commands(account_id: int) -> list[dict[str, Any]]:
    """Load queued commands for this engine account."""
    try:
        response = (
            get_supabase_client()
            .table("bot_commands")
            .select("command_id,command_type,account_id")
            .eq("account_id", account_id)
            .eq("status", "queued")
            .order("created_at")
            .execute()
        )
        return [dict(row) for row in response.data or []]
    except Exception:
        logger.exception("Could not load queued commands for account %s.", account_id)
        raise


def update_bot_command(
    command_id: int,
    status: str,
    result: str | None = None,
) -> None:
    """Record command progress and its final outcome."""
    if status not in {"processing", "completed", "failed"}:
        raise ValueError("Invalid bot command status.")
    values: dict[str, Any] = {"status": status, "result": result}
    if status in {"completed", "failed"}:
        values["processed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        response = (
            get_supabase_client()
            .table("bot_commands")
            .update(values)
            .eq("command_id", command_id)
            .eq("status", "queued" if status == "processing" else "processing")
            .select("command_id")
            .execute()
        )
        if not response.data:
            raise RuntimeError(f"Bot command {command_id} changed state before update.")
    except Exception:
        logger.exception("Could not update bot command %s to %s.", command_id, status)
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