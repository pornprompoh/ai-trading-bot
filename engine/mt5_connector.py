"""MetaTrader 5 terminal connection and market/account data access."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import MetaTrader5 as mt5
import pandas as pd

from config.settings import MT5_LOGIN, MT5_SERVER

logger = logging.getLogger(__name__)

TIMEFRAMES: dict[str, int] = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


@dataclass(frozen=True)
class ClosedDeal:
    """Relevant details for an MT5 exit deal."""

    position_id: int
    close_price: float
    profit_loss: float
    reason: str


def connect() -> None:
    """Initialize the already-installed MT5 terminal."""
    if MT5_LOGIN is None or not MT5_SERVER:
        raise RuntimeError("MT5_LOGIN and MT5_SERVER must be configured.")
    if not mt5.initialize(login=MT5_LOGIN, server=MT5_SERVER):
        code, message = mt5.last_error()
        raise ConnectionError(f"Could not initialize MT5 (code={code}): {message}")

    account = mt5.account_info()
    if account is None:
        code, message = mt5.last_error()
        mt5.shutdown()
        raise ConnectionError(f"MT5 account is unavailable (code={code}): {message}")
    if int(account.login) != MT5_LOGIN:
        mt5.shutdown()
        raise ConnectionError("The connected MT5 account does not match MT5_LOGIN.")
    logger.info("Connected to MT5 account %s on %s.", account.login, MT5_SERVER)


def shutdown() -> None:
    """Release the MT5 terminal connection."""
    mt5.shutdown()


def _timeframe_value(timeframe: str) -> int:
    try:
        return TIMEFRAMES[timeframe.upper()]
    except KeyError as exc:
        raise ValueError(f"Unsupported MT5 timeframe: {timeframe}") from exc


def get_ohlcv(
    symbol: str, timeframe: str, n_bars: int = 100
) -> pd.DataFrame:
    """Return OHLCV bars indexed by UTC timestamp."""
    if n_bars <= 0:
        raise ValueError("n_bars must be positive.")
    if not mt5.symbol_select(symbol, True):
        code, message = mt5.last_error()
        raise RuntimeError(f"Could not select {symbol} (code={code}): {message}")

    rates = mt5.copy_rates_from_pos(symbol, _timeframe_value(timeframe), 0, n_bars)
    if rates is None or len(rates) == 0:
        code, message = mt5.last_error()
        raise RuntimeError(f"No OHLCV data for {symbol} (code={code}): {message}")

    frame = pd.DataFrame(rates)
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    return frame.set_index("time")[["open", "high", "low", "close", "tick_volume"]].rename(
        columns={"tick_volume": "volume"}
    )


def get_account_status() -> dict[str, int | float | str]:
    """Return the current terminal account and balance information."""
    account = mt5.account_info()
    if account is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"Could not read MT5 account (code={code}): {message}")
    return {
        "login": int(account.login),
        "server": str(account.server),
        "balance": float(account.balance),
        "equity": float(account.equity),
        "margin": float(account.margin),
        "free_margin": float(account.margin_free),
    }


def get_closed_deal(position_id: int) -> ClosedDeal | None:
    """Return aggregated exit data only after the MT5 position is fully closed."""
    positions = mt5.positions_get(ticket=position_id)
    if positions is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"Could not check position {position_id} (code={code}): {message}")
    if positions:
        return None

    deals = mt5.history_deals_get(position=position_id)
    if deals is None:
        code, message = mt5.last_error()
        raise RuntimeError(
            f"Could not read deal history for position {position_id} "
            f"(code={code}): {message}"
        )

    exit_entries = {mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY}
    exits = [deal for deal in deals if deal.entry in exit_entries]
    if not exits:
        return None

    exit_volume = sum(float(deal.volume) for deal in exits)
    if exit_volume <= 0:
        raise RuntimeError(f"MT5 returned invalid exit volume for position {position_id}.")
    close_price = sum(float(deal.price) * float(deal.volume) for deal in exits) / exit_volume
    profit_loss = sum(
        float(deal.profit + deal.commission + deal.swap) for deal in deals
    )
    last_reason = exits[-1].reason
    reason = (
        "stop loss"
        if last_reason == mt5.DEAL_REASON_SL
        else "take profit"
        if last_reason == mt5.DEAL_REASON_TP
        else "manual/other"
    )
    return ClosedDeal(
        position_id=position_id,
        close_price=close_price,
        profit_loss=profit_loss,
        reason=reason,
    )