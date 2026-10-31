"""Scan configured MT5 symbols and synchronize closed trades to Supabase."""

from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler

from config.settings import (
    AUTO_TRADE_RISK_PERCENT,
    AUTO_TRADING_ENABLED,
    MAX_RECONNECT_DELAY_SECONDS,
    PROJECT_ROOT,
    SCAN_INTERVAL_SECONDS,
    WATCHLIST,
)
from engine.ai_analyst import AIDecision, confirm_entry
from database.db_manager import (
    get_open_trade_tickets,
    record_account_snapshot,
    record_trade_close,
    sync_account,
)
from engine.mt5_connector import (
    ensure_connected,
    get_account_status,
    get_closed_deal,
    get_ohlcv,
    get_symbol_point,
    has_open_position,
    is_demo_account,
    shutdown,
)
from engine.order_executor import calculate_lot_size, open_order
from engine.strategy import detect_signal

logger = logging.getLogger("trading_engine")
_processed_signal_candles: dict[str, str] = {}
_ai_retry_state: dict[str, tuple[str, float, int]] = {}
_ai_decision_cache: dict[str, tuple[str, AIDecision]] = {}
_last_snapshot_at = 0.0
ACCOUNT_SNAPSHOT_INTERVAL_SECONDS = 300


def configure_logging() -> None:
    """Configure console and rotating-file logs for unattended operation."""
    log_directory = PROJECT_ROOT / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                log_directory / "trading_engine.log",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            ),
        ],
    )


def scan_watchlist() -> None:
    """Analyze completed candles, request AI confirmation, and trade if enabled."""
    for symbol, asset in WATCHLIST.items():
        try:
            if has_open_position(symbol):
                logger.info("Skipping %s: an MT5 position is already open.", symbol)
                continue

            bars = get_ohlcv(symbol, asset.timeframe, n_bars=300)
            completed_bars = bars.iloc[:-1]
            signal = detect_signal(completed_bars, point=get_symbol_point(symbol))
            if signal.signal_type == "NONE":
                logger.info("%s %s: no entry signal.", symbol, asset.timeframe)
                continue
            if (
                signal.candle_time is None
                or signal.technical_data is None
                or signal.entry_price is None
                or signal.stop_loss is None
                or signal.take_profit is None
                or signal.sl_points is None
                or signal.tp_points is None
            ):
                raise RuntimeError(f"Strategy returned incomplete signal data for {symbol}.")
            if _processed_signal_candles.get(symbol) == signal.candle_time:
                continue
            retry_state = _ai_retry_state.get(symbol)
            if (
                retry_state is not None
                and retry_state[0] == signal.candle_time
                and time.monotonic() < retry_state[1]
            ):
                continue
            logger.info(
                "%s %s %s signal at %.5f, SL=%.5f, TP=%.5f.",
                symbol,
                asset.timeframe,
                signal.signal_type,
                signal.entry_price,
                signal.stop_loss,
                signal.take_profit,
            )
            cached_decision = _ai_decision_cache.get(symbol)
            if cached_decision is not None and cached_decision[0] == signal.candle_time:
                decision = cached_decision[1]
            else:
                try:
                    decision = confirm_entry(
                        symbol, signal.signal_type, signal.technical_data
                    )
                except Exception:
                    previous_attempts = (
                        retry_state[2]
                        if retry_state is not None and retry_state[0] == signal.candle_time
                        else 0
                    )
                    delay = min(60 * (2**previous_attempts), 15 * 60)
                    _ai_retry_state[symbol] = (
                        signal.candle_time,
                        time.monotonic() + delay,
                        previous_attempts + 1,
                    )
                    logger.exception(
                        "AI confirmation failed for %s; retrying in %s seconds.",
                        symbol,
                        delay,
                    )
                    continue
                _ai_retry_state.pop(symbol, None)
                _ai_decision_cache[symbol] = (signal.candle_time, decision)
            logger.info(
                "Gemini %s %s: approved=%s confidence=%.2f reason=%s",
                symbol,
                signal.signal_type,
                decision["approved"],
                decision["confidence"],
                decision["reasoning"],
            )
            if not decision["approved"]:
                _processed_signal_candles[symbol] = signal.candle_time
                _ai_decision_cache.pop(symbol, None)
                continue
            if not AUTO_TRADING_ENABLED:
                logger.warning(
                    "AI approved %s %s, but order sending is disabled.",
                    symbol,
                    signal.signal_type,
                )
                _processed_signal_candles[symbol] = signal.candle_time
                _ai_decision_cache.pop(symbol, None)
                continue
            if not is_demo_account():
                logger.error("Refusing to trade %s: connected MT5 account is not a demo.", symbol)
                _processed_signal_candles[symbol] = signal.candle_time
                _ai_decision_cache.pop(symbol, None)
                continue
            try:
                lot = calculate_lot_size(
                    symbol, signal.sl_points, AUTO_TRADE_RISK_PERCENT
                )
                context = {
                    **decision["context"],
                    "timeframe": asset.timeframe,
                    "risk_percent": AUTO_TRADE_RISK_PERCENT,
                    "ai_confidence": decision["confidence"],
                    "ai_reasoning": decision["reasoning"],
                }
                open_order(
                    symbol=symbol,
                    action=signal.signal_type,
                    lot=lot,
                    sl_points=signal.sl_points,
                    tp_points=signal.tp_points,
                    indicator_snapshot=signal.technical_data,
                    reasoning=decision["reasoning"],
                    context=context,
                )
            except ValueError:
                _processed_signal_candles[symbol] = signal.candle_time
                _ai_decision_cache.pop(symbol, None)
                logger.exception("Signal for %s cannot be safely traded.", symbol)
                continue
            except Exception:
                previous_attempts = (
                    retry_state[2]
                    if retry_state is not None and retry_state[0] == signal.candle_time
                    else 0
                )
                delay = min(60 * (2**previous_attempts), 15 * 60)
                _ai_retry_state[symbol] = (
                    signal.candle_time,
                    time.monotonic() + delay,
                    previous_attempts + 1,
                )
                logger.exception(
                    "Order handling failed for %s; retrying in %s seconds.",
                    symbol,
                    delay,
                )
                continue
            _processed_signal_candles[symbol] = signal.candle_time
            _ai_decision_cache.pop(symbol, None)
        except Exception:
            logger.exception("Market analysis or trade execution failed for %s.", symbol)


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


def run() -> None:
    """Run indefinitely, reconnecting after transient MT5/network failures."""
    global _last_snapshot_at
    configure_logging()
    retry_delay = 2
    connected_logged = False
    try:
        while True:
            try:
                ensure_connected()
                account = get_account_status()
                account_id = sync_account(
                    int(account["login"]),
                    str(account["server"]),
                    float(account["balance"]),
                )
                if (
                    not _last_snapshot_at
                    or time.monotonic() - _last_snapshot_at
                    >= ACCOUNT_SNAPSHOT_INTERVAL_SECONDS
                ):
                    record_account_snapshot(account_id, account)
                    _last_snapshot_at = time.monotonic()
                if not connected_logged:
                    logger.info(
                        "Engine active for account %s (DB account_id=%s, demo=%s, "
                        "auto_trading=%s).",
                        account["login"],
                        account_id,
                        is_demo_account(),
                        AUTO_TRADING_ENABLED,
                    )
                    connected_logged = True
                synchronize_closed_trades()
                scan_watchlist()
                retry_delay = 2
            except Exception:
                logger.exception("Engine cycle failed; retrying in %s seconds.", retry_delay)
                connected_logged = False
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RECONNECT_DELAY_SECONDS)
                continue
            time.sleep(SCAN_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        try:
            shutdown()
        except Exception:
            logger.exception("Could not shut down the MT5 connector cleanly.")


if __name__ == "__main__":
    run()