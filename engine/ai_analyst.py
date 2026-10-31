"""Gemini-based risk confirmation for technical entry signals."""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Mapping, TypedDict

from google import genai
from google.genai import types

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MIN_AI_CONFIDENCE,
)

logger = logging.getLogger(__name__)
_client: genai.Client | None = None


class AIDecision(TypedDict):
    """Validated Gemini decision and the exact context sent for review."""

    approved: bool
    confidence: float
    reasoning: str
    context: dict[str, Any]


def _get_client() -> genai.Client:
    """Create the Gemini API client lazily, with a bounded request timeout."""
    global _client
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    if _client is None:
        _client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=15_000),
        )
    return _client


def _market_session(now: datetime) -> str:
    """Summarize commonly monitored FX sessions using UTC hour windows."""
    hour = now.astimezone(timezone.utc).hour
    sessions: list[str] = []
    if 0 <= hour < 9:
        sessions.append("Asia")
    if 7 <= hour < 16:
        sessions.append("London")
    if 12 <= hour < 21:
        sessions.append("New York")
    return " / ".join(sessions) if sessions else "Low-liquidity/off-session"


def confirm_entry(
    symbol: str,
    signal_type: str,
    technical_data: Mapping[str, Any],
) -> AIDecision:
    """Ask Gemini for a structured risk review; fail closed on invalid responses."""
    if signal_type not in {"BUY", "SELL"}:
        raise ValueError("signal_type must be BUY or SELL.")

    now = datetime.now(timezone.utc)
    context = {
        "symbol": symbol,
        "signal": signal_type,
        "ema_trend": (
            "price_above_ema50_and_ema200"
            if float(technical_data["close"]) > float(technical_data["ema_50"])
            and float(technical_data["close"]) > float(technical_data["ema_200"])
            else "price_below_ema50_and_ema200"
        ),
        "technical_data": dict(technical_data),
        "session_utc": _market_session(now),
        "timestamp_utc": now.isoformat(),
    }
    prompt = (
        "Assess this proposed forex/metal entry for risk. Do not invent market "
        "facts; use only the supplied context. This is a risk filter, not a "
        "prediction or guarantee. Return only JSON with exactly these fields: "
        '{"approved": boolean, "confidence": number from 0 to 1, '
        '"reasoning": short string}. Reject if context is incomplete, conditions '
        "are ambiguous, or the setup appears unusually risky.\n"
        f"Context: {json.dumps(context, ensure_ascii=True, allow_nan=False)}"
    )
    try:
        response = _get_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=256,
                response_mime_type="application/json",
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        parsed = json.loads(response.text)
        approved = parsed.get("approved")
        confidence_value = parsed.get("confidence")
        reasoning = parsed.get("reasoning")
        if not isinstance(approved, bool):
            raise ValueError("Gemini response field 'approved' must be boolean.")
        if (
            isinstance(confidence_value, bool)
            or not isinstance(confidence_value, (int, float))
            or not math.isfinite(float(confidence_value))
            or not 0 <= float(confidence_value) <= 1
        ):
            raise ValueError("Gemini response confidence must be a finite number from 0 to 1.")
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise ValueError("Gemini response field 'reasoning' must be non-empty text.")

        confidence = float(confidence_value)
        return {
            "approved": approved and confidence >= MIN_AI_CONFIDENCE,
            "confidence": confidence,
            "reasoning": reasoning.strip(),
            "context": context,
        }
    except Exception:
        logger.exception("Gemini confirmation failed for %s %s.", symbol, signal_type)
        raise
