"""Risk-based position sizing and protected MT5 market-order execution."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

import MetaTrader5 as mt5

from config.settings import AUTO_TRADING_ENABLED, DEMO_ACCOUNT_ONLY
from config.settings import MAX_SLIPPAGE_POINTS
from database.db_manager import (
    get_auto_trading_setting,
    record_trade_open,
    sync_account,
)
from engine.mt5_connector import get_account_status, get_ohlcv, is_demo_account
from engine.risk_manager import check_entry_risk
from engine.strategy import calculate_indicators

logger = logging.getLogger(__name__)
MAGIC_NUMBER = 20261031
PARTIAL_CLOSE_COMMENT = "EnginePartial"


def calculate_lot_size(symbol: str, sl_points: float, risk_percent: float) -> float:
    """Calculate volume from account balance, stop distance, and broker limits."""
    if sl_points <= 0 or not 0 < risk_percent <= 100:
        raise ValueError("sl_points and risk_percent must be positive and valid.")

    account = mt5.account_info()
    info = mt5.symbol_info(symbol)
    if account is None or info is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"Cannot calculate lot size for {symbol} (code={code}): {message}")
    if info.point <= 0 or info.trade_tick_size <= 0 or info.trade_tick_value <= 0:
        raise RuntimeError(f"Broker returned invalid tick data for {symbol}.")

    risk_amount = float(account.balance) * risk_percent / 100.0
    loss_per_lot = (
        sl_points * float(info.point) / float(info.trade_tick_size)
    ) * float(info.trade_tick_value)
    raw_volume = risk_amount / loss_per_lot
    step = float(info.volume_step)
    if step <= 0:
        raise RuntimeError(f"Broker returned an invalid volume step for {symbol}.")

    volume = math.floor((raw_volume + 1e-12) / step) * step
    volume = min(volume, float(info.volume_max))
    if volume < float(info.volume_min):
        raise ValueError(
            f"Risk-based volume for {symbol} is below broker minimum; "
            "refusing to increase risk to the minimum lot."
        )
    precision = max(0, -Decimal(str(step)).normalize().as_tuple().exponent)
    return round(volume, precision)


def open_order(
    symbol: str,
    action: str,
    lot: float,
    sl_points: float,
    tp_points: float,
    indicator_snapshot: Mapping[str, Any],
    reasoning: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a market order with mandatory SL/TP and persist it immediately."""
    if not AUTO_TRADING_ENABLED:
        raise RuntimeError("Order sending is disabled; set AUTO_TRADING_ENABLED=true to enable.")
    if not DEMO_ACCOUNT_ONLY or not is_demo_account():
        raise RuntimeError("Automatic orders are restricted to MT5 demo accounts.")
    direction = action.strip().upper()
    if direction not in {"BUY", "SELL"}:
        raise ValueError("action must be BUY or SELL.")
    if lot <= 0 or sl_points <= 0 or tp_points <= 0:
        raise ValueError("lot, sl_points, and tp_points must all be positive.")
    if tp_points / sl_points < 2.0:
        raise ValueError("Trade setup must provide a minimum 1:2 reward-to-risk ratio.")

    risk_assessment = check_entry_risk(symbol)
    if not risk_assessment.approved:
        raise ValueError(f"Entry blocked by risk manager: {risk_assessment.reason}")

    if not mt5.symbol_select(symbol, True):
        code, message = mt5.last_error()
        raise RuntimeError(f"Could not select {symbol} (code={code}): {message}")
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"Cannot read market data for {symbol} (code={code}): {message}")

    volume = float(lot)
    step = float(info.volume_step)
    if (
        step <= 0
        or volume < float(info.volume_min)
        or volume > float(info.volume_max)
        or not math.isclose(volume / step, round(volume / step), abs_tol=1e-7)
    ):
        raise ValueError(f"Lot size {lot} is outside broker volume constraints for {symbol}.")

    is_buy = direction == "BUY"
    price = float(tick.ask if is_buy else tick.bid)
    if price <= 0:
        raise RuntimeError(f"Broker returned an invalid price for {symbol}.")
    point = float(info.point)
    stops_level = int(info.trade_stops_level)
    if sl_points < stops_level or tp_points < stops_level:
        raise ValueError(
            f"SL/TP distance is below broker minimum of {stops_level} points for {symbol}."
        )
    stop_loss = price - sl_points * point if is_buy else price + sl_points * point
    take_profit = price + tp_points * point if is_buy else price - tp_points * point

    filling_mode = (
        mt5.ORDER_FILLING_IOC
        if int(info.filling_mode) & 2
        else mt5.ORDER_FILLING_FOK
        if int(info.filling_mode) & 1
        else mt5.ORDER_FILLING_RETURN
    )
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": round(stop_loss, int(info.digits)),
        "tp": round(take_profit, int(info.digits)),
        "deviation": MAX_SLIPPAGE_POINTS,
        "magic": MAGIC_NUMBER,
        "comment": "MultiAssetEngine",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    account = get_account_status()
    account_id = sync_account(
        int(account["login"]),
        str(account["server"]),
        float(account["balance"]),
        str(account["account_type"]),
        str(account["currency"]),
    )
    if not get_auto_trading_setting(account_id):
        raise RuntimeError("Account auto-trading is disabled in dashboard controls.")
    result = mt5.order_send(request)
    if result is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"MT5 returned no order result (code={code}): {message}")
    if result.retcode not in {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL}:
        raise RuntimeError(
            f"Order rejected for {symbol}: retcode={result.retcode}, comment={result.comment}"
        )
    if not result.order:
        raise RuntimeError(
            f"MT5 reported a successful order without an order ticket for {symbol}."
        )

    actual_volume = float(result.volume) if result.volume else volume
    trade_data: dict[str, Any] = {
        "account_id": account_id,
        "ticket": int(result.order),
        "symbol": symbol,
        "action": direction,
        "volume": actual_volume,
        "open_price": float(result.price or price),
        "sl_price": float(request["sl"]),
        "tp_price": float(request["tp"]),
        "open_time": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }
    try:
        execution_context = {
            **dict(context or {}),
            "execution_risk": risk_assessment.context,
        }
        trade_id = record_trade_open(
            trade_data,
            indicator_snapshot,
            reasoning,
            context_dict=execution_context,
        )
    except Exception:
        logger.critical(
            "MT5 accepted order ticket=%s, but Supabase logging failed. "
            "The open position must be reconciled.",
            result.order,
            exc_info=True,
        )
        raise
    logger.info(
        "Opened %s %s %.2f lots (ticket=%s, trade_id=%s).",
        direction,
        symbol,
        actual_volume,
        result.order,
        trade_id,
    )
    return {"trade_id": trade_id, "ticket": int(result.order), "volume": actual_volume}


def _filling_mode(info: Any) -> int:
    return (
        mt5.ORDER_FILLING_IOC
        if int(info.filling_mode) & 2
        else mt5.ORDER_FILLING_FOK
        if int(info.filling_mode) & 1
        else mt5.ORDER_FILLING_RETURN
    )


def _modify_position_stop(
    position: Any,
    stop_loss: float,
    info: Any,
    tick: Any,
) -> bool:
    """Tighten a position stop without violating broker distance constraints."""
    is_buy = position.type == mt5.POSITION_TYPE_BUY
    point = float(info.point)
    min_distance = max(
        int(info.trade_stops_level),
        int(getattr(info, "trade_freeze_level", 0)),
    ) * point
    quote = float(tick.bid if is_buy else tick.ask)
    invalid_distance = (
        stop_loss >= quote - min_distance
        if is_buy
        else stop_loss <= quote + min_distance
    )
    if quote <= 0 or invalid_distance:
        return False
    current_stop = float(position.sl)
    if is_buy and current_stop > 0 and stop_loss <= current_stop:
        return False
    if not is_buy and current_stop > 0 and stop_loss >= current_stop:
        return False
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": int(position.ticket),
        "sl": round(stop_loss, int(info.digits)),
        "tp": float(position.tp),
        "magic": MAGIC_NUMBER,
        "comment": "EngineStopManagement",
    }
    result = mt5.order_send(request)
    if result is None:
        code, message = mt5.last_error()
        raise RuntimeError(
            f"Stop update returned no result for {position.ticket} "
            f"(code={code}): {message}"
        )
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(
            f"Stop update rejected for {position.ticket}: "
            f"retcode={result.retcode}, comment={result.comment}"
        )
    logger.info(
        "Moved stop for %s position %s to %.*f.",
        position.symbol,
        position.ticket,
        int(info.digits),
        stop_loss,
    )
    return True


def _partial_close_completed(position: Any) -> bool:
    deals = mt5.history_deals_get(position=int(position.identifier))
    if deals is None:
        code, message = mt5.last_error()
        raise RuntimeError(
            f"Could not inspect partial-close history for {position.ticket} "
            f"(code={code}): {message}"
        )
    exit_entries = {mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY}
    return any(
        deal.entry in exit_entries
        and int(getattr(deal, "magic", 0)) == MAGIC_NUMBER
        and PARTIAL_CLOSE_COMMENT in str(getattr(deal, "comment", ""))
        for deal in deals
    )


def _close_half_position(position: Any, info: Any, tick: Any) -> bool:
    """Close exactly half only when broker volume increments allow it."""
    step = float(info.volume_step)
    volume = float(position.volume)
    half = volume / 2.0
    if step <= 0:
        raise RuntimeError(f"Broker returned invalid volume step for {position.symbol}.")
    close_volume = math.floor((half + 1e-12) / step) * step
    precision = max(0, -Decimal(str(step)).normalize().as_tuple().exponent)
    close_volume = round(close_volume, precision)
    remaining = round(volume - close_volume, precision)
    if (
        not math.isclose(close_volume, half, rel_tol=0.0, abs_tol=step * 1e-7)
        or close_volume < float(info.volume_min)
        or remaining < float(info.volume_min)
    ):
        logger.warning(
            "Cannot close exactly 50%% of position %s within broker volume limits.",
            position.ticket,
        )
        return False

    is_buy = position.type == mt5.POSITION_TYPE_BUY
    price = float(tick.bid if is_buy else tick.ask)
    if price <= 0:
        raise RuntimeError(f"Broker returned invalid quote for {position.symbol}.")
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": close_volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "position": int(position.ticket),
        "price": price,
        "deviation": MAX_SLIPPAGE_POINTS,
        "magic": MAGIC_NUMBER,
        "comment": PARTIAL_CLOSE_COMMENT,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling_mode(info),
    }
    result = mt5.order_send(request)
    if result is None:
        code, message = mt5.last_error()
        raise RuntimeError(
            f"Partial close returned no result for {position.ticket} "
            f"(code={code}): {message}"
        )
    if result.retcode not in {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL}:
        raise RuntimeError(
            f"Partial close rejected for {position.ticket}: "
            f"retcode={result.retcode}, comment={result.comment}"
        )
    logger.info(
        "Closed %.2f lots (50%%) from position %s at 1.5R.",
        close_volume,
        position.ticket,
    )
    return True


def _chandelier_stop(position: Any) -> float | None:
    """Compute a 22-bar M15 Chandelier stop from completed candles only."""
    bars = get_ohlcv(position.symbol, "M15", n_bars=60)
    completed = bars.iloc[:-1]
    if len(completed) < 30:
        return None
    indicators = calculate_indicators(completed)
    atr = float(indicators.iloc[-1]["atr_14"])
    if not math.isfinite(atr) or atr <= 0:
        return None
    recent = completed.iloc[-22:]
    if position.type == mt5.POSITION_TYPE_BUY:
        return float(recent["high"].max()) - 3.0 * atr
    return float(recent["low"].min()) + 3.0 * atr


def manage_open_positions() -> None:
    """Apply 1R break-even, 1.5R partial close, then M15 Chandelier trailing."""
    if not DEMO_ACCOUNT_ONLY or not is_demo_account():
        return
    positions = mt5.positions_get()
    if positions is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"Could not list positions for management (code={code}): {message}")

    for position in positions:
        if int(getattr(position, "magic", 0)) != MAGIC_NUMBER:
            continue
        try:
            info = mt5.symbol_info(position.symbol)
            tick = mt5.symbol_info_tick(position.symbol)
            if info is None or tick is None:
                code, message = mt5.last_error()
                raise RuntimeError(
                    f"Missing quote/metadata for position {position.ticket} "
                    f"(code={code}): {message}"
                )
            target = float(position.tp)
            entry = float(position.price_open)
            initial_risk = abs(target - entry) / 2.0
            if target <= 0 or initial_risk <= 0:
                raise RuntimeError(
                    f"Position {position.ticket} has no valid 1:2 target for R calculation."
                )

            is_buy = position.type == mt5.POSITION_TYPE_BUY
            market_price = float(tick.bid if is_buy else tick.ask)
            profit_distance = market_price - entry if is_buy else entry - market_price
            r_multiple = profit_distance / initial_risk
            if r_multiple >= 1.0:
                _modify_position_stop(position, entry, info, tick)

            partial_done = _partial_close_completed(position)
            if r_multiple >= 1.5 and not partial_done:
                partial_done = _close_half_position(position, info, tick)

            if partial_done:
                trail = _chandelier_stop(position)
                trail_is_profitable = (
                    trail > entry if is_buy and trail is not None
                    else trail < entry if trail is not None
                    else False
                )
                if trail is not None and trail_is_profitable:
                    _modify_position_stop(position, trail, info, tick)
        except Exception:
            logger.exception(
                "Could not manage open position %s (%s).",
                position.ticket,
                position.symbol,
            )


def close_all_positions() -> int:
    """Close every position on the connected demo account, failing if any remain."""
    if not DEMO_ACCOUNT_ONLY or not is_demo_account():
        raise RuntimeError("Emergency close is restricted to MT5 demo accounts.")

    positions = mt5.positions_get()
    if positions is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"Could not list MT5 positions (code={code}): {message}")

    closed_count = 0
    failures: list[str] = []
    for position in positions:
        info = mt5.symbol_info(position.symbol)
        tick = mt5.symbol_info_tick(position.symbol)
        if info is None or tick is None:
            code, message = mt5.last_error()
            failures.append(
                f"ticket {position.ticket}: missing market data (code={code}): {message}"
            )
            continue

        is_buy_position = int(position.type) == mt5.POSITION_TYPE_BUY
        filling_mode = (
            mt5.ORDER_FILLING_IOC
            if int(info.filling_mode) & 2
            else mt5.ORDER_FILLING_FOK
            if int(info.filling_mode) & 1
            else mt5.ORDER_FILLING_RETURN
        )
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": float(position.volume),
            "type": mt5.ORDER_TYPE_SELL if is_buy_position else mt5.ORDER_TYPE_BUY,
            "position": int(position.ticket),
            "price": float(tick.bid if is_buy_position else tick.ask),
            "deviation": MAX_SLIPPAGE_POINTS,
            "magic": MAGIC_NUMBER,
            "comment": "EmergencyCloseAll",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }
        if request["price"] <= 0:
            failures.append(f"ticket {position.ticket}: invalid close quote")
            continue
        result = mt5.order_send(request)
        if result is None:
            code, message = mt5.last_error()
            failures.append(
                f"ticket {position.ticket}: no result (code={code}): {message}"
            )
        elif result.retcode not in {
            mt5.TRADE_RETCODE_DONE,
            mt5.TRADE_RETCODE_DONE_PARTIAL,
        }:
            failures.append(
                f"ticket {position.ticket}: retcode={result.retcode} "
                f"comment={result.comment}"
            )
        else:
            closed_count += 1

    remaining = mt5.positions_get()
    if remaining is None:
        code, message = mt5.last_error()
        failures.append(f"Could not verify remaining positions (code={code}): {message}")
    elif remaining:
        failures.append(
            "Positions remain open: "
            + ", ".join(str(position.ticket) for position in remaining)
        )
    if failures:
        raise RuntimeError("Emergency close incomplete: " + "; ".join(failures))

    logger.warning("Emergency close completed; closed %s MT5 positions.", closed_count)
    return closed_count