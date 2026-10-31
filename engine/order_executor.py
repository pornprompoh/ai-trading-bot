"""Risk-based position sizing and protected MT5 market-order execution."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

import MetaTrader5 as mt5

from config.settings import AUTO_TRADING_ENABLED, DEMO_ACCOUNT_ONLY
from database.db_manager import record_trade_open, sync_account
from engine.mt5_connector import get_account_status, is_demo_account

logger = logging.getLogger(__name__)
MAGIC_NUMBER = 20261031


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
        "deviation": 20,
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
        trade_id = record_trade_open(
            trade_data, indicator_snapshot, reasoning, context_dict=context
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