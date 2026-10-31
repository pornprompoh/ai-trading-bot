"""Indicator-based pullback strategy using completed MT5 candles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

SignalType = Literal["BUY", "SELL", "NONE"]


@dataclass(frozen=True)
class TradeSignal:
    """Signal and ATR-derived protection levels for a completed candle."""

    signal_type: SignalType
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    sl_points: float | None = None
    tp_points: float | None = None
    technical_data: dict[str, float | str] | None = None
    candle_time: str | None = None


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of OHLC data with EMA(50/200), Wilder RSI(14), and ATR(14)."""
    required = {"high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"OHLCV data is missing columns: {', '.join(sorted(missing))}")
    if not df.index.is_monotonic_increasing:
        raise ValueError("OHLCV data must be ordered from oldest to newest.")

    result = df.copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    high = pd.to_numeric(result["high"], errors="coerce")
    low = pd.to_numeric(result["low"], errors="coerce")
    if close.isna().any() or high.isna().any() or low.isna().any():
        raise ValueError("OHLCV prices must be numeric and contain no missing values.")

    result["ema_50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    result["ema_200"] = close.ewm(span=200, adjust=False, min_periods=200).mean()

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    average_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = average_gain / average_loss
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100.0)
    rsi = rsi.mask((average_loss == 0) & (average_gain == 0), 50.0)
    result["rsi_14"] = rsi

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr_14"] = true_range.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean()
    return result


def detect_signal(df: pd.DataFrame, point: float = 0.0) -> TradeSignal:
    """Detect an EMA-trend RSI reversal and derive 1.5x/2x ATR SL/TP levels.

    ``df`` must contain completed candles only; callers should exclude the
    currently forming MT5 candle. ``point`` is the broker's minimum price step.
    """
    if point < 0:
        raise ValueError("point cannot be negative.")
    indicators = calculate_indicators(df)
    if len(indicators) < 201:
        return TradeSignal("NONE")

    previous = indicators.iloc[-2]
    current = indicators.iloc[-1]
    values = [
        previous["rsi_14"],
        current["rsi_14"],
        current["ema_50"],
        current["ema_200"],
        current["atr_14"],
    ]
    if any(pd.isna(value) for value in values):
        return TradeSignal("NONE")

    close = float(current["close"])
    ema_50 = float(current["ema_50"])
    ema_200 = float(current["ema_200"])
    previous_rsi = float(previous["rsi_14"])
    current_rsi = float(current["rsi_14"])
    atr = float(current["atr_14"])

    direction: SignalType = "NONE"
    if close > ema_50 and close > ema_200 and previous_rsi < 45 and current_rsi > previous_rsi:
        direction = "BUY"
    elif (
        close < ema_50
        and close < ema_200
        and previous_rsi > 55
        and current_rsi < previous_rsi
    ):
        direction = "SELL"

    if direction == "NONE" or atr <= 0:
        return TradeSignal("NONE")

    stop_distance = 1.5 * atr
    target_distance = 2.0 * atr
    if direction == "BUY":
        stop_loss = close - stop_distance
        take_profit = close + target_distance
    else:
        stop_loss = close + stop_distance
        take_profit = close - target_distance
    if stop_loss <= 0 or take_profit <= 0:
        return TradeSignal("NONE")

    time_value = indicators.index[-1]
    candle_time = time_value.isoformat() if hasattr(time_value, "isoformat") else str(time_value)
    technical_data: dict[str, float | str] = {
        "close": close,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "rsi_14": current_rsi,
        "previous_rsi_14": previous_rsi,
        "atr_14": atr,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }
    return TradeSignal(
        signal_type=direction,
        entry_price=close,
        stop_loss=stop_loss,
        take_profit=take_profit,
        sl_points=stop_distance / point if point > 0 else None,
        tp_points=target_distance / point if point > 0 else None,
        technical_data=technical_data,
        candle_time=candle_time,
    )
