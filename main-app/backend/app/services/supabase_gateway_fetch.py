"""
Fetch per-user LLM edge HMAC secret from Supabase after remote-login.

Uses the end-user's Supabase access token + anon key against PostgREST so RLS applies
(auth.uid() = user_id). No service role on ReTrace required.

Expected table (connect-ask-act / Lovable):

  create table public.gateway_edge_secrets (
    user_id uuid primary key references auth.users (id) on delete cascade,
    hmac_secret text not null
  );
  alter table public.gateway_edge_secrets enable row level security;
  create policy "read own"
    on public.gateway_edge_secrets for select
    using (auth.uid() = user_id);
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def fetch_gateway_hmac_from_supabase(
    supabase_access_token: str,
    supabase_user_sub: str,
) -> Optional[str]:
    """
    Return plaintext HMAC secret for Cloudflare X-Gateway-Sig, or None if unset / error.
    """
    base = (settings.SUPABASE_URL or "").strip().rstrip("/")
    anon = (settings.SUPABASE_ANON_KEY or "").strip()
    table = (settings.SUPABASE_GATEWAY_SECRET_TABLE or "").strip()
    col = (settings.SUPABASE_GATEWAY_SECRET_COLUMN or "hmac_secret").strip()
    uid_col = (settings.SUPABASE_GATEWAY_USER_ID_COLUMN or "user_id").strip()

    if not base or not anon or not table:
        return None

    # PostgREST filter: user_id must match JWT sub (Supabase auth user id)
    url = f"{base}/rest/v1/{table}"
    params = {uid_col: f"eq.{supabase_user_sub}", "select": col}

    headers = {
        "apikey": anon,
        "Authorization": f"Bearer {supabase_access_token}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url, params=params, headers=headers)
    except Exception as exc:
        logger.warning("supabase_gateway_fetch_http_error", extra={"error": str(exc)})
        return None

    if r.status_code == 404:
        return None
    if not r.is_success:
        logger.warning(
            "supabase_gateway_fetch_failed",
            extra={"status": r.status_code, "body": r.text[:200]},
        )
        return None

    try:
        rows = r.json()
    except Exception:
        return None

    if not rows or not isinstance(rows, list):
        return None

    row = rows[0]
    if not isinstance(row, dict):
        return None

    raw = row.get(col)
    if raw is None or not isinstance(raw, str):
        return None

    secret = raw.strip()
    return secret or None
