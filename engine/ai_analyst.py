"""Gemini-based risk confirmation for technical entry signals."""

from __future__ import annotations

from typing import Any, Mapping, TypedDict

from google import genai
from google.genai import types

from config.settings import GEMINI_API_KEY

_client: genai.Client | None = None


class AIDecision(TypedDict):
    """Validated Gemini decision and the exact context sent for review."""

    approved: bool
    confidence: float
    reasoning: str
    context: dict[str, Any]


def get_gemini_client() -> genai.Client:
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


def confirm_entry(
    symbol: str,
    signal_type: str,
    technical_data: Mapping[str, Any],
    account_id: int,
) -> AIDecision:
    """Compatibility wrapper for callers of the former analyst entry point."""
    from engine.ai_validator import confirm_entry as validate_entry

    return validate_entry(symbol, signal_type, technical_data, account_id)
