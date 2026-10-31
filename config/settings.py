"""Application configuration loaded from the project .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
MT5_SERVER = os.getenv("MT5_SERVER", "").strip()
AUTO_TRADING_ENABLED = os.getenv("AUTO_TRADING_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}
DEMO_ACCOUNT_ONLY = os.getenv("DEMO_ACCOUNT_ONLY", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}
AUTO_TRADE_RISK_PERCENT = 1.0
MIN_AI_CONFIDENCE = 0.70
MAX_RECONNECT_DELAY_SECONDS = 60

_mt5_login = os.getenv("MT5_LOGIN", "").strip()
try:
    MT5_LOGIN: int | None = int(_mt5_login) if _mt5_login else None
except ValueError as exc:
    raise ValueError("MT5_LOGIN must be an integer.") from exc


@dataclass(frozen=True)
class AssetConfig:
    """Trading parameters for a single watched symbol."""

    symbol: str
    timeframe: str
    risk_percent: float


WATCHLIST: list[AssetConfig] = [
    AssetConfig(symbol="XAUUSD.iux", timeframe="M15", risk_percent=1.0),
]

SCAN_INTERVAL_SECONDS = 60