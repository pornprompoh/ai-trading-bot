"""Scan configured MT5 symbols and synchronize closed trades to Supabase."""

from __future__ import annotations

import logging
import time

from config.settings import SCAN_INTERVAL_SECONDS, WATCHLIST
from database.db_manager import (
    get_open_trade_tickets,
    record_trade_close,
    sync_account,
)
from engine.mt5_connector import (
    connect,
    get_account_status,
    get_closed_deal,
    get_ohlcv,
    shutdown,
)

logger = logging.getLogger("trading_engine")


def configure_logging() -> None:
    """Configure concise console logging for the engine."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def scan_watchlist() -> None:
    """Fetch the latest bar for each asset; no entry strategy is configured."""
    for symbol, asset in WATCHLIST.items():
        try:
            bars = get_ohlcv(symbol, asset.timeframe, n_bars=100)
            latest = bars.iloc[-1]
            logger.info(
                "%s %s close=%.5f volume=%.0f; risk=%.2f%%",
                symbol,
                asset.timeframe,
                float(latest["close"]),
                float(latest["volume"]),
                asset.risk_percent,
            )
        except Exception:
            logger.exception("Market scan failed for %s.", symbol)


def synchronize_closed_trades() -> None:
    """Synchronize fully closed MT5 positions tracked as open in Supabase."""
    for ticket in get_open_trade_tickets():
        try:
            deal = get_closed_deal(ticket)
            if deal is None:
                continue
            record_trade_close(
                deal.position_id,
                deal.close_price,
                deal.profit_loss,
                deal.reason,
            )
        except Exception:
            logger.exception("Could not synchronize closed position %s.", ticket)


def synchronize_account_balance() -> None:
    """Keep the latest MT5 balance in Supabase."""
    account = get_account_status()
    sync_account(
        int(account["login"]), str(account["server"]), float(account["balance"])
    )


def run() -> None:
    """Run the market scan and trade synchronization loop."""
    configure_logging()
    connect()
    try:
        account = get_account_status()
        account_id = sync_account(
            int(account["login"]), str(account["server"]), float(account["balance"])
        )
        logger.info(
            "Engine started for account %s (DB account_id=%s).",
            account["login"],
            account_id,
        )

        while True:
            try:
                synchronize_account_balance()
                synchronize_closed_trades()
                scan_watchlist()
            except Exception:
                logger.exception("Unexpected scan-cycle failure.")
            time.sleep(SCAN_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        shutdown()


if __name__ == "__main__":
    run()