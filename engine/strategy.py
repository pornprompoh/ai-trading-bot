"""Multi-timeframe structure, liquidity, and regime analysis for XAUUSD M15."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

SignalType = Literal["BUY", "SELL", "NONE"]
MarketRegime = Literal["TRENDING", "RANGING", "VOLATILE_SHOCK", "UNAVAILABLE"]


@dataclass(frozen=True)
class TradeSignal:
    """Multi-timeframe setup and broker-point protection levels."""

    signal_type: SignalType
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    sl_points: float | None = None
    tp_points: float | None = None
    technical_data: dict[str, float | str] | None = None
    candle_time: str | None = None


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate EMA, Wilder RSI/ATR/ADX, and rolling ATR percentile."""
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

    up_move = high.diff()
    down_move = -low.diff()
    positive_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    negative_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    smoothed_tr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    positive_di = 100 * positive_dm.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean() / smoothed_tr
    negative_di = 100 * negative_dm.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean() / smoothed_tr
    di_sum = positive_di + negative_di
    dx = (100 * (positive_di - negative_di).abs() / di_sum).where(di_sum != 0)
    result["adx_14"] = dx.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean()
    result["atr_percentile"] = result["atr_14"].rolling(
        window=100, min_periods=30
    ).apply(
        lambda values: float(
            (
                (values < values[-1]).sum()
                + 0.5 * (values == values[-1]).sum()
            )
            / len(values)
        ),
        raw=True,
    )
    result["atr_median_100"] = result["atr_14"].rolling(
        window=100, min_periods=30
    ).median()
    return result


def classify_market_regime(indicators: pd.DataFrame) -> MarketRegime:
    """Classify current ATR expansion and directional strength; unknown fails closed."""
    if indicators.empty or not {
        "atr_percentile",
        "atr_median_100",
        "atr_14",
        "adx_14",
    }.issubset(indicators.columns):
        return "UNAVAILABLE"
    current = indicators.iloc[-1]
    atr_percentile = current["atr_percentile"]
    atr = current["atr_14"]
    atr_median = current["atr_median_100"]
    adx = current["adx_14"]
    if (
        pd.isna(atr_percentile)
        or pd.isna(atr)
        or pd.isna(atr_median)
        or pd.isna(adx)
        or float(atr_median) <= 0
    ):
        return "UNAVAILABLE"
    if float(atr_percentile) >= 0.95 and float(atr) >= 1.5 * float(atr_median):
        return "VOLATILE_SHOCK"
    if (
        float(adx) < 20
        or (
            float(atr_percentile) <= 0.20
            and float(atr) <= 0.8 * float(atr_median)
        )
    ):
        return "RANGING"
    return "TRENDING"


def _market_structure_trend(indicators: pd.DataFrame) -> str:
    if len(indicators) < 201:
        return "unavailable"
    current = indicators.iloc[-1]
    if pd.isna(current["ema_50"]) or pd.isna(current["ema_200"]):
        return "unavailable"
    if current["close"] > current["ema_50"] > current["ema_200"]:
        return "bullish"
    if current["close"] < current["ema_50"] < current["ema_200"]:
        return "bearish"
    return "mixed"


def _latest_pivot_levels(
    candles: pd.DataFrame,
    radius: int = 2,
    lookback: int = 80,
) -> tuple[float | None, float | None]:
    """Return the latest confirmed pivot low and high in a bounded candle window."""
    recent = candles.iloc[-lookback:]
    lows: list[float] = []
    highs: list[float] = []
    for index in range(radius, len(recent) - radius):
        low_window = recent["low"].iloc[index - radius : index + radius + 1]
        high_window = recent["high"].iloc[index - radius : index + radius + 1]
        low = float(recent["low"].iloc[index])
        high = float(recent["high"].iloc[index])
        if low == float(low_window.min()):
            lows.append(low)
        if high == float(high_window.max()):
            highs.append(high)
    return (lows[-1] if lows else None, highs[-1] if highs else None)


def detect_signal(
    m15_df: pd.DataFrame,
    point: float = 0.0,
    h1_df: pd.DataFrame | None = None,
    h4_df: pd.DataFrame | None = None,
) -> TradeSignal:
    """Require aligned H4/H1 structure plus an M15 sweep, CHoCH, and FVG.

    All input frames must contain completed candles only. Ranging, compressed,
    shock, and incomplete MTF regimes fail closed. Orders are sized at a minimum
    1:2 reward-to-risk ratio.
    """
    if point < 0:
        raise ValueError("point cannot be negative.")
    if h1_df is None or h4_df is None:
        return TradeSignal("NONE")
    if len(m15_df) < 100 or len(h1_df) < 201 or len(h4_df) < 201:
        return TradeSignal("NONE")

    m15 = calculate_indicators(m15_df)
    h1 = calculate_indicators(h1_df)
    h4 = calculate_indicators(h4_df)
    regime = classify_market_regime(m15)
    h4_trend = _market_structure_trend(h4)
    h1_trend = _market_structure_trend(h1)
    if regime != "TRENDING" or h4_trend not in {"bullish", "bearish"}:
        return TradeSignal("NONE")

    if h1_trend != h4_trend:
        return TradeSignal("NONE")

    current = m15.iloc[-1]
    atr = float(current["atr_14"])
    h1_atr = float(h1.iloc[-1]["atr_14"])
    atr_percentile = float(current["atr_percentile"])
    adx = float(current["adx_14"])
    if not all(map(lambda value: pd.notna(value) and value > 0, (atr, h1_atr, adx))):
        return TradeSignal("NONE")

    close = float(current["close"])
    support, resistance = _latest_pivot_levels(h1_df)
    if support is None or resistance is None:
        return TradeSignal("NONE")
    near_demand = abs(close - support) <= 0.75 * h1_atr and close >= support
    near_supply = abs(resistance - close) <= 0.75 * h1_atr and close <= resistance

    # Require a recent sweep, followed by a separate M15 displacement/CHoCH bar.
    window = 20
    previous_lows = m15["low"].rolling(window).min().shift(1)
    previous_highs = m15["high"].rolling(window).max().shift(1)
    sweep_index: int | None = None
    sweep_direction: SignalType = "NONE"
    sweep_extreme: float | None = None
    sweep_wick_ratio = 0.0
    first_sweep = max(window, len(m15) - 8)
    for index in range(first_sweep, len(m15)):
        candle = m15.iloc[index]
        candle_range = float(candle["high"] - candle["low"])
        if candle_range <= 0:
            continue
        lower_wick = min(float(candle["open"]), float(candle["close"])) - float(candle["low"])
        upper_wick = float(candle["high"]) - max(float(candle["open"]), float(candle["close"]))
        prior_low = previous_lows.iloc[index]
        prior_high = previous_highs.iloc[index]
        if (
            h4_trend == "bullish"
            and pd.notna(prior_low)
            and float(candle["low"]) < float(prior_low)
        ):
            ratio = lower_wick / candle_range
            if float(candle["close"]) > float(prior_low) and ratio >= 0.35:
                sweep_index = index
                sweep_direction = "BUY"
                sweep_extreme = float(candle["low"])
                sweep_wick_ratio = ratio
        elif (
            h4_trend == "bearish"
            and pd.notna(prior_high)
            and float(candle["high"]) > float(prior_high)
        ):
            ratio = upper_wick / candle_range
            if float(candle["close"]) < float(prior_high) and ratio >= 0.35:
                sweep_index = index
                sweep_direction = "SELL"
                sweep_extreme = float(candle["high"])
                sweep_wick_ratio = ratio

    if sweep_index is None or sweep_extreme is None:
        return TradeSignal("NONE")
    prior_structure = m15.iloc[max(0, sweep_index - 5) : sweep_index]
    if prior_structure.empty:
        return TradeSignal("NONE")
    choch_up = close > float(prior_structure["high"].max())
    choch_down = close < float(prior_structure["low"].min())
    bullish_fvg = float(current["low"]) > float(m15["high"].iloc[-3])
    bearish_fvg = float(current["high"]) < float(m15["low"].iloc[-3])

    direction: SignalType = "NONE"
    if (
        h4_trend == "bullish"
        and near_demand
        and sweep_direction == "BUY"
        and choch_up
        and bullish_fvg
    ):
        direction = "BUY"
    elif (
        h4_trend == "bearish"
        and near_supply
        and sweep_direction == "SELL"
        and choch_down
        and bearish_fvg
    ):
        direction = "SELL"
    if direction == "NONE":
        return TradeSignal("NONE")

    stop_loss = sweep_extreme - 0.2 * atr if direction == "BUY" else sweep_extreme + 0.2 * atr
    stop_distance = abs(close - stop_loss)
    if stop_distance <= 0 or stop_distance > 3.0 * atr:
        return TradeSignal("NONE")
    target_distance = 2.0 * stop_distance
    take_profit = close + target_distance if direction == "BUY" else close - target_distance
    if min(stop_loss, take_profit) <= 0:
        return TradeSignal("NONE")

    time_value = m15.index[-1]
    candle_time = time_value.isoformat() if hasattr(time_value, "isoformat") else str(time_value)
    technical_data: dict[str, float | str] = {
        "close": close,
        "atr_14": atr,
        "atr_percentile": atr_percentile,
        "adx_14": adx,
        "market_regime": regime,
        "h4_trend": h4_trend,
        "h4_ema_50": float(h4.iloc[-1]["ema_50"]),
        "h4_ema_200": float(h4.iloc[-1]["ema_200"]),
        "h1_trend": h1_trend,
        "h1_demand_pivot": support,
        "h1_supply_pivot": resistance,
        "liquidity_sweep": "low" if direction == "BUY" else "high",
        "choch": "bullish" if direction == "BUY" else "bearish",
        "fair_value_gap": "bullish" if direction == "BUY" else "bearish",
        "rejection_wick_ratio": sweep_wick_ratio,
        "ema_50": float(m15.iloc[-1]["ema_50"]),
        "ema_200": float(m15.iloc[-1]["ema_200"]),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward_ratio": 2.0,
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
