"""Lazy, shared Supabase client."""

from __future__ import annotations

from supabase import Client, create_client

from config.settings import SUPABASE_KEY, SUPABASE_URL

_client: Client | None = None


def get_supabase_client() -> Client:
    """Return the shared Supabase client, creating it on first use."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured.")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client

