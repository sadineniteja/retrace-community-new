"""
Fetch ScreenOps coordinate-finder settings from the managed gateway (Zuplo behind Cloudflare).

Zuplo exposes GET {GATEWAY_BASE_URL}/retrace/screenops-config returning JSON:
  {
    "coord_model": "gpt-4o-mini",
    "coord_path":  "/screenops/v1"
  }

Backend always calls through GATEWAY_BASE_URL (never a different host).
  - coord_model → model name for the request body; missing = main chat model
  - coord_path  → path prefix on the gateway (e.g. /screenops/v1); missing = /v1 (same as chat)
  - coord_api_key → Bearer for non-JWT users; missing = Supabase JWT (same as chat)

When coord_path differs from /v1, Zuplo must have a matching route that forwards
to the ScreenOps-specific upstream with its own API key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx
import structlog

from app.services.gateway_session import gateway_llm_headers

logger = structlog.get_logger(__name__)

SCREENOPS_GATEWAY_CONFIG_PATH = "retrace/screenops-config"


@dataclass
class ScreenOpsGatewayConfig:
    coord_model: str = ""
    coord_path: str = ""
    coord_api_key: str = ""
    chat_model: str = ""


def _first_str(payload: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def parse_screenops_gateway_payload(data: Any) -> ScreenOpsGatewayConfig:
    if not isinstance(data, dict):
        return ScreenOpsGatewayConfig()
    return ScreenOpsGatewayConfig(
        coord_model=_first_str(
            data,
            ("coord_model", "screenops_coord_model", "screenops_model", "model"),
        ),
        coord_path=_first_str(
            data,
            ("coord_path", "screenops_path"),
        ),
        coord_api_key=_first_str(
            data,
            ("coord_api_key", "screenops_api_key"),
        ),
        chat_model=_first_str(
            data,
            ("chat_model", "default_model"),
        ),
    )


async def fetch_screenops_gateway_config(
    gateway_base: str,
    config_path: str,
    supabase_bearer: Optional[str],
) -> ScreenOpsGatewayConfig:
    """Load ScreenOps model/key from gateway JSON, or empty config if unavailable."""
    base = (gateway_base or "").strip().rstrip("/")
    path = (config_path or "").strip().strip("/")
    if not base or not path:
        return ScreenOpsGatewayConfig()

    url = f"{base}/{path}"
    headers: dict[str, str] = {}
    token = (supabase_bearer or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers.update(gateway_llm_headers())
    if not headers:
        return ScreenOpsGatewayConfig()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers=headers)
    except Exception as exc:
        logger.debug("gateway_screenops_config_http_error", url=url, error=str(exc))
        return ScreenOpsGatewayConfig()

    if r.status_code != 200:
        logger.debug("gateway_screenops_config_bad_status", url=url, status=r.status_code)
        return ScreenOpsGatewayConfig()

    try:
        data = r.json()
    except Exception:
        return ScreenOpsGatewayConfig()

    cfg = parse_screenops_gateway_payload(data)
    if cfg.coord_model or cfg.coord_path or cfg.coord_api_key:
        logger.debug(
            "gateway_screenops_config_ok",
            has_model=bool(cfg.coord_model),
            coord_path=cfg.coord_path or "/v1",
            has_key=bool(cfg.coord_api_key),
        )
    return cfg
