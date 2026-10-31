"""Fail-closed spread and high-impact economic-calendar entry filters."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import MetaTrader5 as mt5

from config.settings import (
    ECONOMIC_CALENDAR_URL,
    MAX_SLIPPAGE_POINTS,
    NEWS_BLACKOUT_MINUTES,
    NEWS_CALENDAR_REFRESH_SECONDS,
    NEWS_CALENDAR_REQUEST_TIMEOUT_SECONDS,
    NEWS_IMPACT_CURRENCIES,
    SPREAD_AVERAGE_MULTIPLIER,
    SPREAD_HARD_CEILING_POINTS,
    SPREAD_MINIMUM_SAMPLES,
    SPREAD_SAMPLE_WINDOW,
)

logger = logging.getLogger(__name__)
_spread_samples: dict[str, deque[float]] = defaultdict(
    lambda: deque(maxlen=SPREAD_SAMPLE_WINDOW)
)
_calendar_events: list[dict[str, Any]] | None = None
_calendar_fetched_at: float | None = None


@dataclass(frozen=True)
class RiskAssessment:
    """Entry-gate result and auditable market conditions."""

    approved: bool
    reason: str
    context: dict[str, float | int | str | bool]


def _spread_points(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None or float(info.point) <= 0:
        code, message = mt5.last_error()
        raise RuntimeError(
            f"Cannot read spread for {symbol} (code={code}): {message}"
        )
    bid = float(tick.bid)
    ask = float(tick.ask)
    if bid <= 0 or ask <= bid:
        raise RuntimeError(f"Broker returned an invalid bid/ask for {symbol}.")
    return (ask - bid) / float(info.point)


def observe_spread(symbol: str) -> RiskAssessment:
    """Add one market spread sample and report whether it passes both ceilings."""
    current = _spread_points(symbol)
    samples = _spread_samples[symbol]
    previous_mean = sum(samples) / len(samples) if samples else 0.0
    samples.append(current)
    sample_count = len(samples)
    average = sum(samples) / sample_count
    context: dict[str, float | int | str | bool] = {
        "spread_points": current,
        "spread_average_points": average,
        "spread_samples": sample_count,
        "spread_hard_ceiling_points": SPREAD_HARD_CEILING_POINTS,
        "spread_average_multiplier": SPREAD_AVERAGE_MULTIPLIER,
        "slippage_limit_points": MAX_SLIPPAGE_POINTS,
    }

    if current > SPREAD_HARD_CEILING_POINTS:
        return RiskAssessment(
            False,
            f"Spread {current:.1f} points exceeds hard ceiling "
            f"{SPREAD_HARD_CEILING_POINTS}.",
            context,
        )
    if sample_count < SPREAD_MINIMUM_SAMPLES:
        return RiskAssessment(
            False,
            f"Spread baseline warming up ({sample_count}/{SPREAD_MINIMUM_SAMPLES} samples).",
            context,
        )
    baseline = previous_mean if previous_mean > 0 else average
    if current > baseline * SPREAD_AVERAGE_MULTIPLIER:
        return RiskAssessment(
            False,
            f"Spread {current:.1f} points exceeds {SPREAD_AVERAGE_MULTIPLIER:.2f}x "
            f"rolling average ({baseline:.1f}).",
            context,
        )
    return RiskAssessment(True, "Spread within dynamic and hard limits.", context)


def _parse_event_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Economic-calendar event is missing its date.")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Economic-calendar event date must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _load_calendar_events() -> list[dict[str, Any]]:
    global _calendar_events, _calendar_fetched_at
    now_monotonic = time.monotonic()
    if (
        _calendar_events is not None
        and _calendar_fetched_at is not None
        and now_monotonic - _calendar_fetched_at < NEWS_CALENDAR_REFRESH_SECONDS
    ):
        return _calendar_events

    try:
        with httpx.Client(
            timeout=httpx.Timeout(
                NEWS_CALENDAR_REQUEST_TIMEOUT_SECONDS,
                connect=min(3.0, NEWS_CALENDAR_REQUEST_TIMEOUT_SECONDS),
            ),
            follow_redirects=False,
        ) as client:
            response = client.get(ECONOMIC_CALENDAR_URL)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Economic-calendar response must be a JSON array.")
        events: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Economic-calendar response contains an invalid event.")
            if (
                str(item.get("country", "")).upper() in NEWS_IMPACT_CURRENCIES
                and str(item.get("impact", "")).strip().lower() == "high"
            ):
                event = dict(item)
                event["_event_time_utc"] = _parse_event_time(item.get("date"))
                events.append(event)
        _calendar_events = events
        _calendar_fetched_at = now_monotonic
        logger.info("Loaded %s USD high-impact calendar events.", len(events))
        return events
    except Exception as exc:
        logger.exception("Could not refresh the high-impact economic calendar.")
        raise RuntimeError(
            "News calendar is unavailable; new trades are blocked until refreshed."
        ) from exc


def check_news_blackout(
    now: datetime | None = None,
) -> tuple[bool, dict[str, str] | None]:
    """Block inside the configured UTC window around high-impact USD events."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("News-check time must include a timezone.")
    current = current.astimezone(timezone.utc)
    window = timedelta(minutes=NEWS_BLACKOUT_MINUTES)
    for event in _load_calendar_events():
        event_time = event["_event_time_utc"]
        if abs(current - event_time) <= window:
            return True, {
                "title": str(event.get("title", "High-impact USD event")),
                "event_time_utc": event_time.isoformat(),
                "impact": str(event.get("impact", "High")),
                "country": str(event.get("country", "USD")),
            }
    return False, None


def check_entry_risk(symbol: str) -> RiskAssessment:
    """Recheck the live spread and calendar immediately before an entry order."""
    current = _spread_points(symbol)
    samples = _spread_samples[symbol]
    sample_count = len(samples)
    average = sum(samples) / sample_count if samples else 0.0
    context: dict[str, float | int | str | bool] = {
        "spread_points": current,
        "spread_average_points": average,
        "spread_samples": sample_count,
        "spread_hard_ceiling_points": SPREAD_HARD_CEILING_POINTS,
        "spread_average_multiplier": SPREAD_AVERAGE_MULTIPLIER,
        "slippage_limit_points": MAX_SLIPPAGE_POINTS,
    }
    if current > SPREAD_HARD_CEILING_POINTS:
        return RiskAssessment(
            False,
            f"Spread {current:.1f} points exceeds hard ceiling "
            f"{SPREAD_HARD_CEILING_POINTS}.",
            context,
        )
    if sample_count < SPREAD_MINIMUM_SAMPLES:
        return RiskAssessment(
            False,
            f"Spread baseline warming up ({sample_count}/{SPREAD_MINIMUM_SAMPLES} samples).",
            context,
        )
    if average <= 0 or current > average * SPREAD_AVERAGE_MULTIPLIER:
        return RiskAssessment(
            False,
            f"Spread {current:.1f} points exceeds "
            f"{SPREAD_AVERAGE_MULTIPLIER:.2f}x rolling average ({average:.1f}).",
            context,
        )

    blocked, event = check_news_blackout()
    context["news_blackout"] = blocked
    if blocked and event is not None:
        context["news_event"] = event["title"]
        context["news_event_time_utc"] = event["event_time_utc"]
        return RiskAssessment(
            False,
            f"High-impact USD event blackout: {event['title']} "
            f"at {event['event_time_utc']}.",
            context,
        )
    return RiskAssessment(True, "Spread and high-impact news filters passed.", context)