"""Scan configured MT5 symbols and synchronize closed trades to Supabase."""

from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler

from config.settings import (
    AUTO_TRADING_ENABLED,
    MAX_RECONNECT_DELAY_SECONDS,
    POSITION_MANAGEMENT_INTERVAL_SECONDS,
    PROJECT_ROOT,
    SCAN_INTERVAL_SECONDS,
    WATCHLIST,
)
from engine.ai_analyst import AIDecision
from engine.ai_reflector import reflect_closed_trades
from engine.ai_validator import confirm_entry
from database.db_manager import (
    get_auto_trading_setting,
    get_pending_bot_commands,
    get_open_trade_tickets,
    record_account_snapshot,
    record_market_scan,
    record_trade_close,
    sync_account,
    update_bot_command,
)
from engine.mt5_connector import (
    ensure_connected,
    get_account_status,
    get_closed_deal,
    get_last_price,
    get_ohlcv,
    get_symbol_point,
    has_open_position,
    is_demo_account,
    shutdown,
)
from engine.order_executor import (
    calculate_lot_size,
    close_all_positions,
    manage_open_positions,
    open_order,
)
from engine.risk_manager import check_entry_risk, observe_spread
from engine.strategy import (
    calculate_indicators,
    classify_market_regime,
    detect_signal,
)

logger = logging.getLogger("trading_engine")
_processed_signal_candles: dict[str, str] = {}
_ai_retry_state: dict[str, tuple[str, float, int]] = {}
_ai_decision_cache: dict[str, tuple[str, AIDecision]] = {}
_last_snapshot_at = 0.0
ACCOUNT_SNAPSHOT_INTERVAL_SECONDS = 300
COMMAND_POLL_INTERVAL_SECONDS = 5


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


def _scanner_reason(
    market_regime: str,
    h4_trend: str,
    h1_trend: str,
) -> str:
    if market_regime != "TRENDING":
        return f"Market regime {market_regime}; entries require TRENDING"
    if h4_trend != h1_trend or h4_trend not in {"bullish", "bearish"}:
        return "H4/H1 macro structure is mixed; waiting for alignment"
    return "Waiting for M15 liquidity sweep, CHoCH, and FVG near H1 zone"


def scan_watchlist(account_id: int, account_auto_trading: bool) -> None:
    """Analyze completed candles, request AI confirmation, and trade if enabled."""
    for asset in WATCHLIST:
        symbol = asset.symbol
        try:
            m15_bars = get_ohlcv(symbol, "M15", n_bars=300)
            h1_bars = get_ohlcv(symbol, "H1", n_bars=300)
            h4_bars = get_ohlcv(symbol, "H4", n_bars=300)
            completed_bars = m15_bars.iloc[:-1]
            completed_h1_bars = h1_bars.iloc[:-1]
            completed_h4_bars = h4_bars.iloc[:-1]
            indicator_frame = calculate_indicators(completed_bars)
            h1_indicator_frame = calculate_indicators(completed_h1_bars)
            h4_indicator_frame = calculate_indicators(completed_h4_bars)
            current = indicator_frame.iloc[-1] if not indicator_frame.empty else None
            current_rsi = (
                float(current["rsi_14"])
                if current is not None and current["rsi_14"] == current["rsi_14"]
                else None
            )
            last_price = get_last_price(symbol)
            market_regime = classify_market_regime(indicator_frame)
            current_h1 = h1_indicator_frame.iloc[-1]
            current_h4 = h4_indicator_frame.iloc[-1]
            h1_trend = (
                "bullish"
                if current_h1["close"] > current_h1["ema_50"] > current_h1["ema_200"]
                else "bearish"
                if current_h1["close"] < current_h1["ema_50"] < current_h1["ema_200"]
                else "mixed"
            )
            h4_trend = (
                "bullish"
                if current_h4["close"] > current_h4["ema_50"] > current_h4["ema_200"]
                else "bearish"
                if current_h4["close"] < current_h4["ema_50"] < current_h4["ema_200"]
                else "mixed"
            )
            ema_trend = (
                "bullish"
                if current is not None
                and last_price > current["ema_50"]
                and last_price > current["ema_200"]
                else "bearish"
                if current is not None
                and last_price < current["ema_50"]
                and last_price < current["ema_200"]
                else "mixed"
            )
            point = get_symbol_point(symbol)
            signal = detect_signal(
                completed_bars,
                point=point,
                h1_df=completed_h1_bars,
                h4_df=completed_h4_bars,
            )
            spread_assessment = observe_spread(symbol)
            position_open = has_open_position(symbol)
            signal_status = (
                "position_open"
                if position_open
                else "condition_met"
                if signal.signal_type != "NONE"
                else "no_signal"
            )
            reason = (
                "Position already open"
                if position_open
                else "Entry conditions met; awaiting AI review"
                if signal.signal_type != "NONE"
                else _scanner_reason(market_regime, h4_trend, h1_trend)
            )
            record_market_scan(
                account_id,
                {
                    "symbol": symbol,
                    "timeframe": asset.timeframe,
                    "last_price": last_price,
                    "rsi": current_rsi,
                    "ema_trend": ema_trend,
                    "signal_status": signal_status,
                    "reason": reason,
                },
            )
            if position_open:
                logger.info("Skipping %s: an MT5 position is already open.", symbol)
                continue
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
            if not spread_assessment.approved:
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": last_price,
                        "rsi": current_rsi,
                        "ema_trend": ema_trend,
                        "signal_status": "condition_met",
                        "reason": f"Risk filter: {spread_assessment.reason}",
                    },
                )
                logger.warning("Risk gate blocked %s: %s", symbol, spread_assessment.reason)
                continue
            risk_assessment = check_entry_risk(symbol)
            if not risk_assessment.approved:
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": last_price,
                        "rsi": current_rsi,
                        "ema_trend": ema_trend,
                        "signal_status": "condition_met",
                        "reason": f"Risk filter: {risk_assessment.reason}",
                    },
                )
                logger.warning("Risk gate blocked %s: %s", symbol, risk_assessment.reason)
                continue
            if not is_demo_account():
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": last_price,
                        "rsi": current_rsi,
                        "ema_trend": ema_trend,
                        "signal_status": "condition_met",
                        "reason": "Signal detected; automated trading is Demo-only",
                    },
                )
                _processed_signal_candles[symbol] = signal.candle_time
                _ai_decision_cache.pop(symbol, None)
                continue
            if not AUTO_TRADING_ENABLED or not account_auto_trading:
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": last_price,
                        "rsi": current_rsi,
                        "ema_trend": ema_trend,
                        "signal_status": "condition_met",
                        "reason": (
                            "Engine trading gate is disabled"
                            if not AUTO_TRADING_ENABLED
                            else "Auto-trading is disabled in Dashboard"
                        ),
                    },
                )
                _processed_signal_candles[symbol] = signal.candle_time
                _ai_decision_cache.pop(symbol, None)
                continue
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
                    analysis_data = {
                        **signal.technical_data,
                        **{
                            f"risk_{key}": value
                            for key, value in risk_assessment.context.items()
                        },
                    }
                    decision = confirm_entry(
                        symbol,
                        signal.signal_type,
                        analysis_data,
                        account_id,
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
                    record_market_scan(
                        account_id,
                        {
                            "symbol": symbol,
                            "timeframe": asset.timeframe,
                            "last_price": last_price,
                            "rsi": current_rsi,
                            "ema_trend": ema_trend,
                            "signal_status": "unavailable",
                            "reason": f"Gemini unavailable; retry in {delay}s",
                        },
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
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": last_price,
                        "rsi": current_rsi,
                        "ema_trend": ema_trend,
                        "signal_status": "rejected",
                        "reason": f"Gemini rejected entry: {decision['reasoning']}",
                    },
                )
                _processed_signal_candles[symbol] = signal.candle_time
                _ai_decision_cache.pop(symbol, None)
                continue
            try:
                lot = calculate_lot_size(symbol, signal.sl_points, asset.risk_percent)
                context = {
                    **decision["context"],
                    "timeframe": asset.timeframe,
                    "risk_percent": asset.risk_percent,
                    "ai_confidence": decision["confidence"],
                    "ai_reasoning": decision["reasoning"],
                    "entry_risk": risk_assessment.context,
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
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": last_price,
                        "rsi": current_rsi,
                        "ema_trend": ema_trend,
                        "signal_status": "condition_met",
                        "reason": "Signal blocked by risk or broker constraints",
                    },
                )
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
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": last_price,
                        "rsi": current_rsi,
                        "ema_trend": ema_trend,
                        "signal_status": "unavailable",
                        "reason": f"Order handling failed; retry in {delay}s",
                    },
                )
                continue
            record_market_scan(
                account_id,
                {
                    "symbol": symbol,
                    "timeframe": asset.timeframe,
                    "last_price": last_price,
                    "rsi": current_rsi,
                    "ema_trend": ema_trend,
                    "signal_status": "position_open",
                    "reason": f"{signal.signal_type} order opened",
                },
            )
            _processed_signal_candles[symbol] = signal.candle_time
            _ai_decision_cache.pop(symbol, None)
        except Exception:
            logger.exception("Market analysis or trade execution failed for %s.", symbol)
            try:
                record_market_scan(
                    account_id,
                    {
                        "symbol": symbol,
                        "timeframe": asset.timeframe,
                        "last_price": None,
                        "rsi": None,
                        "ema_trend": "unknown",
                        "signal_status": "unavailable",
                        "reason": "Market data or analysis unavailable",
                    },
                )
            except Exception:
                logger.exception("Could not save scanner error state for %s.", symbol)


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


def process_bot_commands(account_id: int) -> None:
    """Run queued dashboard controls on the MT5-owning engine process."""
    for command in get_pending_bot_commands(account_id):
        command_id = int(command["command_id"])
        try:
            update_bot_command(command_id, "processing", "Emergency close requested")
            if command["command_type"] != "close_all":
                raise ValueError(f"Unsupported bot command: {command['command_type']}")
            closed_count = close_all_positions()
            synchronize_closed_trades()
            update_bot_command(
                command_id,
                "completed",
                f"Closed {closed_count} MT5 position(s); auto-trading remains disabled.",
            )
        except Exception as exc:
            logger.exception("Dashboard bot command %s failed.", command_id)
            try:
                update_bot_command(command_id, "failed", str(exc)[:1000])
            except Exception:
                logger.exception("Could not persist failure state for command %s.", command_id)


def wait_for_next_scan(account_id: int) -> None:
    """Keep emergency-command latency low without running market scans continuously."""
    deadline = time.monotonic() + SCAN_INTERVAL_SECONDS
    next_management = time.monotonic()
    while True:
        process_bot_commands(account_id)
        if time.monotonic() >= next_management:
            try:
                manage_open_positions()
            except Exception:
                logger.exception("Could not run periodic position management.")
            next_management = (
                time.monotonic() + POSITION_MANAGEMENT_INTERVAL_SECONDS
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(COMMAND_POLL_INTERVAL_SECONDS, remaining))


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
                    str(account["account_type"]),
                    str(account["currency"]),
                )
                account_auto_trading = get_auto_trading_setting(account_id)
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
                        "env_auto_trading=%s, account_auto_trading=%s).",
                        account["login"],
                        account_id,
                        is_demo_account(),
                        AUTO_TRADING_ENABLED,
                        account_auto_trading,
                    )
                    connected_logged = True
                synchronize_closed_trades()
                reflect_closed_trades(account_id)
                process_bot_commands(account_id)
                manage_open_positions()
                account_auto_trading = get_auto_trading_setting(account_id)
                scan_watchlist(account_id, account_auto_trading)
                wait_for_next_scan(account_id)
                retry_delay = 2
            except Exception:
                logger.exception("Engine cycle failed; retrying in %s seconds.", retry_delay)
                connected_logged = False
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RECONNECT_DELAY_SECONDS)
                continue
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        try:
            shutdown()
        except Exception:
            logger.exception("Could not shut down the MT5 connector cleanly.")


if __name__ == "__main__":
    run()