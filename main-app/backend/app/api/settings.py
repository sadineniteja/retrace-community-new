"""
Settings and configuration API endpoints.
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.config import settings as app_settings
from app.services.gateway_session import gateway_llm_headers
from app.db.database import get_session, async_session_maker
from app.models.settings import LLMSettingsModel
from app.models.mcp_tool_config import McpToolConfig

logger = structlog.get_logger()
router = APIRouter()


def _gateway_base_url() -> str:
    return (app_settings.GATEWAY_BASE_URL or "").strip().rstrip("/")


def llm_settings_blocking_message(llm: dict) -> Optional[str]:
    """Human-readable reason LLM calls must not proceed, or None if OK."""
    if llm.get("llm_unavailable_detail"):
        return str(llm["llm_unavailable_detail"])
    if not (llm.get("api_key") or "").strip():
        return "No LLM API key configured. Set one in Settings."
    return None


class LLMSettings(BaseModel):
    """Schema for LLM settings."""
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: str = Field(..., min_length=1)
    provider: str = Field(default="openai", pattern="^(openai|anthropic|custom)$")
    # ScreenOps — separate endpoint/key/model for coordinate finder
    screenops_api_url: Optional[str] = None
    screenops_api_key: Optional[str] = None
    screenops_model: Optional[str] = None
    # ScreenOps keyboard-only: seconds to wait when mouse click unavoidable (5–120)
    screenops_mouse_timeout: Optional[int] = None
    # ScreenOps image scale 25–100: percentage of screenshot size sent to model (reduces tokens)
    screenops_image_scale: Optional[int] = Field(None, ge=25, le=100)
    # Web Search — Serper API key for enhanced web search
    serper_api_key: Optional[str] = None
    # Enable thinking/reasoning for the main LLM
    enable_thinking: Optional[bool] = None
    # Training: when True, pipeline logs included/excluded folders and files
    debug_logging: Optional[bool] = None
    # Training Phase 3: max files to extract in parallel (1–32, default 1)
    max_parallel_files: Optional[int] = None

    class Config:
        # Allow extra fields to be ignored
        extra = "ignore"


class LLMSettingsResponse(BaseModel):
    """Schema for LLM settings response (hides API key)."""
    api_url: Optional[str] = None
    model_name: str
    provider: str
    api_key_set: bool
    serper_api_key_set: bool = False
    screenops_api_url: Optional[str] = None
    screenops_api_key_set: bool = False
    screenops_model: Optional[str] = None
    screenops_mouse_timeout: int = 30
    screenops_image_scale: int = 100
    enable_thinking: bool = False
    debug_logging: bool = False
    max_parallel_files: int = 1


class TestConnectionResponse(BaseModel):
    """Schema for connection test response."""
    success: bool
    message: str
    latency_ms: Optional[int] = None
    model_info: Optional[dict] = None


class AgentToolsUpdate(BaseModel):
    """Schema for updating agent tools (enabled/disabled)."""
    disabled_tools: list[str] = Field(default_factory=list, description="Tool names to disable")


async def get_or_create_settings(session: AsyncSession) -> LLMSettingsModel:
    """Get or create settings record (singleton - always id=1)."""
    import sys
    try:
        print("[DB] Executing SELECT query...", flush=True)
        result = await session.execute(
            select(LLMSettingsModel).where(LLMSettingsModel.id == 1)
        )
        print("[DB] Query executed, getting result...", flush=True)
        settings = result.scalar_one_or_none()
        print(f"[DB] Result: {'found' if settings else 'not found'}", flush=True)
        
        if not settings:
            print("[DB] Creating new settings record...", flush=True)
            # Create default settings
            settings = LLMSettingsModel(
                id=1,
                provider="openai",
                model_name=app_settings.REASONING_MODEL,
            )
            session.add(settings)
            # Flush to get the ID, but don't commit yet
            # Note: This is called from get_llm_settings which uses get_session dependency
            # The dependency will auto-commit, so we don't need to commit here
            print("[DB] Flushing new record...", flush=True)
            await session.flush()
            print("[DB] Refreshing record...", flush=True)
            await session.refresh(settings)
            print("[DB] New settings created (will be committed by get_session)", flush=True)
        
        return settings
    except Exception as e:
        print(f"[DB] ERROR in get_or_create_settings: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        logger.error("Error in get_or_create_settings", error=str(e), exc_info=True)
        raise


@router.get("/test")
async def test_settings_endpoint():
    """Test endpoint to verify settings API is reachable."""
    logger.info("=== TEST ENDPOINT CALLED ===")
    return {"status": "ok", "message": "Settings API is reachable"}


@router.post("/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(settings_data: LLMSettings):
    """Update LLM settings."""
    import asyncio
    import sys
    
    # Use print for immediate logging
    print(f"[SETTINGS] POST /llm - Provider: {settings_data.provider}, Model: {settings_data.model_name}", flush=True)
    sys.stdout.flush()
    
    logger.info("=== SETTINGS UPDATE REQUEST RECEIVED ===")
    logger.info(f"Provider: {settings_data.provider}, Model: {settings_data.model_name}")
    
    # Use manual session management with explicit transaction
    try:
        print("[SETTINGS] Creating database session...", flush=True)
        async with async_session_maker() as session:
            print("[SETTINGS] Session created, starting transaction...", flush=True)
            # Use explicit transaction context to ensure proper commit
            async with session.begin():
                print("[SETTINGS] Transaction started, getting settings...", flush=True)
                db_settings = await get_or_create_settings(session)
                print(f"[SETTINGS] Got settings from DB, ID: {db_settings.id}", flush=True)
                
                # Update chat settings - only update api_key when provided (partial save)
                if settings_data.api_key is not None and settings_data.api_key.strip():
                    db_settings.api_key = settings_data.api_key.strip()
                db_settings.model_name = settings_data.model_name
                db_settings.provider = settings_data.provider
                
                # For optional api_url: update if provided
                if settings_data.api_url is not None:
                    db_settings.api_url = settings_data.api_url if settings_data.api_url else None
                
                # ScreenOps separate config
                if settings_data.screenops_api_url is not None:
                    db_settings.screenops_api_url = settings_data.screenops_api_url.strip() or None
                if settings_data.screenops_api_key is not None and settings_data.screenops_api_key.strip():
                    db_settings.screenops_api_key = settings_data.screenops_api_key.strip()
                if settings_data.screenops_model is not None:
                    db_settings.screenops_model = settings_data.screenops_model.strip() or None
                if settings_data.screenops_mouse_timeout is not None:
                    db_settings.screenops_mouse_timeout = max(5, min(120, int(settings_data.screenops_mouse_timeout)))
                if settings_data.screenops_image_scale is not None:
                    db_settings.screenops_image_scale = max(25, min(100, int(settings_data.screenops_image_scale)))
                # Serper API key for web search
                if settings_data.serper_api_key is not None:
                    db_settings.serper_api_key = settings_data.serper_api_key if settings_data.serper_api_key else None
                if settings_data.enable_thinking is not None:
                    db_settings.enable_thinking = bool(settings_data.enable_thinking)
                if settings_data.debug_logging is not None:
                    db_settings.debug_logging = bool(settings_data.debug_logging)
                if settings_data.max_parallel_files is not None:
                    n = max(1, min(32, int(settings_data.max_parallel_files)))
                    db_settings.max_parallel_files = n

                print("[SETTINGS] Changes staged, flushing before commit...", flush=True)
                # Flush to ensure all changes are applied
                await session.flush()
                
                # Refresh to get updated values (before commit, while still in transaction)
                await session.refresh(db_settings)
                print("[SETTINGS] Object refreshed", flush=True)
                
                print("[SETTINGS] Transaction will commit on exit...", flush=True)
                # Transaction will auto-commit when exiting the 'begin()' context
                
            # Transaction committed here
            print("[SETTINGS] Transaction committed successfully", flush=True)
            
            # Close any remaining implicit transactions to prevent rollback
            if session.in_transaction():
                await session.commit()
                print("[SETTINGS] Committed any remaining implicit transaction", flush=True)
            
            # Verify the commit worked by checking the database directly
            import sqlite3 as sqlite_sync
            from pathlib import Path
            
            # Get database path from config
            db_url = app_settings.DATABASE_URL
            if db_url.startswith("sqlite+aiosqlite:///"):
                db_path = db_url.replace("sqlite+aiosqlite:///", "")
                if not db_path.startswith("/"):
                    # Relative path - resolve from backend directory
                    backend_dir = Path(__file__).parent.parent.parent
                    db_path = str(backend_dir / db_path)
            else:
                db_path = None
            
            # Quick sync check to verify data was written
            if db_path:
                try:
                    conn = sqlite_sync.connect(db_path, timeout=1.0)
                    cursor = conn.cursor()
                    cursor.execute("SELECT model_name, provider, api_key IS NOT NULL as has_key FROM llm_settings WHERE id = 1")
                    result = cursor.fetchone()
                    conn.close()
                    if result:
                        print(f"[SETTINGS] ✅ Verified in DB: model={result[0]}, provider={result[1]}, has_key={result[2]}", flush=True)
                    else:
                        print("[SETTINGS] ⚠️  WARNING: Settings not found in DB after commit!", flush=True)
                except Exception as verify_error:
                    print(f"[SETTINGS] Could not verify (non-critical): {verify_error}", flush=True)
            
            # Build response from the refreshed object
            response = LLMSettingsResponse(
                api_url=db_settings.api_url,
                model_name=db_settings.model_name or app_settings.REASONING_MODEL,
                provider=db_settings.provider or "openai",
                api_key_set=bool(db_settings.api_key),
                serper_api_key_set=bool(getattr(db_settings, "serper_api_key", None)),
                screenops_api_url=getattr(db_settings, "screenops_api_url", None),
                screenops_api_key_set=bool(getattr(db_settings, "screenops_api_key", None)),
                screenops_model=getattr(db_settings, "screenops_model", None),
                screenops_mouse_timeout=int(getattr(db_settings, "screenops_mouse_timeout", 30) or 30),
                screenops_image_scale=max(25, min(100, int(getattr(db_settings, "screenops_image_scale", 100) or 100))),
                enable_thinking=bool(getattr(db_settings, "enable_thinking", False)),
                debug_logging=bool(getattr(db_settings, "debug_logging", False)),
                max_parallel_files=int(getattr(db_settings, "max_parallel_files", 1) or 1),
            )
            print("[SETTINGS] Returning response", flush=True)
            return response
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SETTINGS] ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        logger.error("Failed to update LLM settings", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")


@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings(session: AsyncSession = Depends(get_session)):
    """Get current LLM settings."""
    print("[GET_SETTINGS] Loading settings from database...", flush=True)
    db_settings = await get_or_create_settings(session)
    
    print(f"[GET_SETTINGS] Loaded: provider={db_settings.provider}, model={db_settings.model_name}, api_url={db_settings.api_url}", flush=True)

    response = LLMSettingsResponse(
        api_url=db_settings.api_url,
        model_name=db_settings.model_name or app_settings.REASONING_MODEL,
        provider=db_settings.provider or "openai",
        api_key_set=bool(db_settings.api_key),
        serper_api_key_set=bool(getattr(db_settings, "serper_api_key", None)),
        screenops_api_url=getattr(db_settings, "screenops_api_url", None),
        screenops_api_key_set=bool(getattr(db_settings, "screenops_api_key", None)),
        screenops_model=getattr(db_settings, "screenops_model", None),
        screenops_mouse_timeout=int(getattr(db_settings, "screenops_mouse_timeout", 30) or 30),
        screenops_image_scale=max(25, min(100, int(getattr(db_settings, "screenops_image_scale", 100) or 100))),
        enable_thinking=bool(getattr(db_settings, "enable_thinking", False)),
        debug_logging=bool(getattr(db_settings, "debug_logging", False)),
        max_parallel_files=int(getattr(db_settings, "max_parallel_files", 1) or 1),
    )

    print(f"[GET_SETTINGS] Returning: provider={response.provider}, model={response.model_name}, api_url={response.api_url}", flush=True)
    return response


def _model_code(name: str) -> str:
    """Turn a model name into a cryptic code: claude-sonnet-4 → cs4, grok-4-nonreasoning-fast → g4nf"""
    parts = [p for p in name.replace(".", "-").split("-") if p]
    return "".join(p[0] for p in parts)


@router.post("/llm/test", response_model=TestConnectionResponse)
async def test_llm_connection(settings_data: LLMSettings, session: AsyncSession = Depends(get_session)):
    """Test connectivity to Chat and ScreenOps APIs."""
    import time
    from openai import AsyncOpenAI

    _DB_PLACEHOLDERS = {'saved-key-placeholder', 'saved-model-placeholder', ''}

    using_managed_gateway_signal = settings_data.api_key == 'sk-gateway-managed'

    db_settings = None
    if not using_managed_gateway_signal and (
        not settings_data.api_key or settings_data.api_key in _DB_PLACEHOLDERS
    ):
        db_settings = await get_or_create_settings(session)
        settings_data.api_key = db_settings.api_key or ""
        if not settings_data.model_name or settings_data.model_name in _DB_PLACEHOLDERS:
            settings_data.model_name = db_settings.model_name or app_settings.REASONING_MODEL
        if not settings_data.api_url:
            settings_data.api_url = db_settings.api_url or None
        settings_data.provider = db_settings.provider or "openai"

    results: dict = {"chat": {}, "screenops": {}, "web_search": {}}
    proxy_base = _gateway_base_url()

    # ── Detect custom LLM mode ──
    _is_custom = (
        settings_data.provider == "custom"
        and settings_data.api_url
        and settings_data.api_key
        and settings_data.api_key != "sk-gateway-managed"
    )

    if not _is_custom and not proxy_base:
        msg = "❌ No LLM configured. Set up a custom LLM in Settings, or configure GATEWAY_BASE_URL."
        results["chat"] = {"success": False, "message": msg, "latency_ms": 0}
        results["screenops"] = {"success": False, "message": "⚠️  ScreenOps: same as above", "latency_ms": 0}
        results["web_search"] = {"success": False, "message": "⚠️  Web search: same as above", "latency_ms": 0}
        return TestConnectionResponse(
            success=False,
            message=msg,
            latency_ms=0,
            model_info=results,
        )

    # ── Test Chat API ──
    try:
        start_time = time.time()

        if _is_custom:
            # Custom LLM: hit user's endpoint directly
            effective_url = settings_data.api_url
            effective_model = settings_data.model_name
            client_kwargs = {"api_key": settings_data.api_key, "base_url": effective_url}
        else:
            # Managed gateway path
            effective_url = f"{proxy_base}/v1"
            from app.services.gateway_session import gateway_supabase_token as _sb_tok_var

            sb_jwt = _sb_tok_var.get()

            if sb_jwt:
                client_kwargs = {"api_key": sb_jwt, "base_url": effective_url}
            else:
                gw_headers = gateway_llm_headers()
                if not gw_headers:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=(
                            "Managed gateway requires authentication. "
                            "Sign in with your Lumena cloud account (Supabase JWT), "
                            "or use an account with a configured per-user gateway HMAC secret."
                        ),
                    )
                effective_key = (settings_data.api_key or "").strip() or "sk-gateway-managed"
                client_kwargs = {"api_key": effective_key, "base_url": effective_url, "default_headers": gw_headers}

            # Fetch chat model from gateway config (same as agent flow)
            from app.services.gateway_screenops_config import (
                SCREENOPS_GATEWAY_CONFIG_PATH as _SO_CFG_PATH,
                fetch_screenops_gateway_config as _fetch_gw_cfg,
            )
            sb_jwt_val = _sb_tok_var.get() if not _is_custom else None
            _gw_cfg = await _fetch_gw_cfg(proxy_base, _SO_CFG_PATH, sb_jwt_val)
            _gw_chat_model = (_gw_cfg.chat_model or "").strip()
            effective_model = _gw_chat_model or settings_data.model_name

        if settings_data.provider not in ("openai", "custom", "anthropic"):
            raise ValueError("Invalid provider specified")

        import httpx
        client = AsyncOpenAI(
            **client_kwargs,
            timeout=httpx.Timeout(120.0, connect=30.0),
        )
        response = await client.chat.completions.create(
            model=effective_model,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        response_model = response.model
        response_content = response.choices[0].message.content

        latency_ms = int((time.time() - start_time) * 1000)
        label = "Custom LLM" if _is_custom else "Chat engine"
        results["chat"] = {
            "success": True,
            "message": f"✅ {label} connected [{_model_code(response_model)}]",
            "latency_ms": latency_ms,
            "response": response_content,
        }
    except HTTPException as e:
        d = e.detail
        detail_str = d if isinstance(d, str) else str(d)
        results["chat"] = {
            "success": False,
            "message": f"❌ Chat: {detail_str[:100]}",
            "latency_ms": 0,
        }
    except Exception as e:
        import traceback
        print(f"[TEST] Chat error: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        results["chat"] = {
            "success": False,
            "message": f"❌ Chat: {type(e).__name__}: {str(e)[:100]}",
            "latency_ms": 0,
        }

    # ── Test ScreenOps ──
    if _is_custom:
        # Custom LLM: use dedicated ScreenOps endpoint if configured in DB, else fall back to main
        try:
            start_time = time.time()
            if db_settings is None:
                db_settings = await get_or_create_settings(session)
            so_url = (getattr(db_settings, "screenops_api_url", None) or "").strip() or settings_data.api_url
            so_key = (getattr(db_settings, "screenops_api_key", None) or "").strip() or settings_data.api_key
            so_model = (getattr(db_settings, "screenops_model", None) or "").strip() or settings_data.model_name
            client = AsyncOpenAI(
                api_key=so_key,
                base_url=so_url,
                timeout=httpx.Timeout(120.0, connect=30.0),
            )
            response = await client.chat.completions.create(
                model=so_model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            so_label = f"ScreenOps [{so_url}]" if so_url != settings_data.api_url else "ScreenOps (main LLM)"
            results["screenops"] = {
                "success": True,
                "message": f"✅ {so_label} [{_model_code(so_model)}]",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            results["screenops"] = {
                "success": False,
                "message": f"❌ ScreenOps: {str(e)[:100]}",
                "latency_ms": 0,
            }
    elif proxy_base:
        try:
            import httpx
            from app.services.gateway_session import gateway_supabase_token as _sb_tok_var
            from app.services.gateway_screenops_config import (
                SCREENOPS_GATEWAY_CONFIG_PATH,
                fetch_screenops_gateway_config,
            )
            sb_jwt = _sb_tok_var.get()
            so_cfg = await fetch_screenops_gateway_config(proxy_base, SCREENOPS_GATEWAY_CONFIG_PATH, sb_jwt)
            coord_model = (so_cfg.coord_model or "").strip() or settings_data.model_name
            coord_key = (so_cfg.coord_api_key or "").strip() or (sb_jwt or "").strip()

            if not coord_key:
                results["screenops"] = {
                    "success": False,
                    "message": "⚠️  ScreenOps: No auth (JWT or coord_api_key)",
                    "latency_ms": 0,
                }
            else:
                so_url = f"{proxy_base}/screenops/v1/chat/completions"
                start_time = time.time()
                async with httpx.AsyncClient(timeout=15.0) as hc:
                    r = await hc.post(
                        so_url,
                        headers={"Authorization": f"Bearer {coord_key}", "Content-Type": "application/json"},
                        json={"model": coord_model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5},
                    )
                latency_ms = int((time.time() - start_time) * 1000)
                if r.is_success:
                    results["screenops"] = {
                        "success": True,
                        "message": f"✅ ScreenOps engine connected [{_model_code(coord_model)}]",
                        "latency_ms": latency_ms,
                    }
                else:
                    body = r.text[:120] if r.text else "(empty)"
                    results["screenops"] = {
                        "success": False,
                        "message": f"❌ ScreenOps: {r.status_code} — {body}",
                        "latency_ms": latency_ms,
                    }
        except Exception as e:
            results["screenops"] = {
                "success": False,
                "message": f"❌ ScreenOps: {str(e)[:100]}",
                "latency_ms": 0,
            }

    # ── Test Web Search ──
    if _is_custom:
        # Custom LLM mode: no managed gateway Serper; DuckDuckGo fallback is automatic at runtime
        results["web_search"] = {
            "success": True,
            "message": "✅ Web search: DuckDuckGo fallback (no managed gateway)",
            "latency_ms": 0,
        }
    elif proxy_base:
        try:
            from app.tools.web_search import SerperProvider

            llm_ctx = await get_active_llm_settings(session)
            # SerperProvider uses gateway_token (JWT); HMAC users leave it empty and use gateway_llm_headers() in search().
            serper_tok = (
                (llm_ctx.get("serper_gateway_bearer") or llm_ctx.get("serper_gateway_token") or "")
                .strip()
            )
            prov = SerperProvider(
                gateway_url=proxy_base,
                gateway_token=serper_tok,
                managed_bearer_key=(llm_ctx.get("api_key") or "").strip(),
            )
            if not prov.is_available():
                results["web_search"] = {
                    "success": False,
                    "message": "⚠️  Web search: managed gateway auth missing (same as chat: JWT or HMAC)",
                    "latency_ms": 0,
                }
            else:
                start_time = time.time()
                sr = prov.search("ReTrace gateway connection test", num_results=3, gl="us", hl="en")
                latency_ms = int((time.time() - start_time) * 1000)
                results["web_search"] = {
                    "success": True,
                    "message": f"✅ Web search connected ({len(sr.organic)} results)",
                    "latency_ms": latency_ms,
                }
        except Exception as e:
            results["web_search"] = {
                "success": False,
                "message": f"❌ Web search: {str(e)[:120]}",
                "latency_ms": 0,
            }

    messages = [
        results["chat"].get("message", ""),
        results["screenops"].get("message", ""),
        results["web_search"].get("message", ""),
    ]
    total_latency = (
        results["chat"].get("latency_ms", 0)
        + results["screenops"].get("latency_ms", 0)
        + results["web_search"].get("latency_ms", 0)
    )

    all_ok = (
        results["chat"].get("success", False)
        and results["screenops"].get("success", False)
        and results["web_search"].get("success", False)
    )

    return TestConnectionResponse(
        success=all_ok,
        message="\n".join(m for m in messages if m),
        latency_ms=total_latency,
        model_info=results,
    )


_LEGACY_KB_TOOL_NAMES = {"search_knowledge_base", "list_kb_entries", "read_kb_file", "browse_kb_structure"}


@router.patch("/agent-tools")
async def update_agent_tools(
    data: AgentToolsUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update which agent tools are enabled/disabled. Pass disabled_tools list."""
    # Normalize: legacy KB tool names → knowledge_base
    disabled = list(data.disabled_tools) if data.disabled_tools else []
    normalized = []
    has_legacy_kb = False
    for name in disabled:
        if name in _LEGACY_KB_TOOL_NAMES:
            has_legacy_kb = True
        else:
            normalized.append(name)
    if has_legacy_kb and "knowledge_base" not in normalized:
        normalized.append("knowledge_base")
    normalized = list(dict.fromkeys(normalized))  # preserve order, dedupe

    db_settings = await get_or_create_settings(session)
    db_settings.agent_tools_config = json.dumps({"disabled": normalized})
    await session.flush()
    return {"ok": True, "disabled_tools": normalized}


@router.get("/llm/api-key")
async def get_api_key(session: AsyncSession = Depends(get_session)):
    """Get the current API key (for internal use)."""
    db_settings = await get_or_create_settings(session)
    return {
        "api_key": db_settings.api_key or ""
    }


@router.get("/llm/model")
async def get_model_name(session: AsyncSession = Depends(get_session)):
    """Get the current model name (for internal use)."""
    db_settings = await get_or_create_settings(session)
    return {
        "model_name": db_settings.model_name or app_settings.REASONING_MODEL,
        "provider": db_settings.provider or "openai"
    }


async def get_active_llm_settings(session: AsyncSession, consumer_key: str | None = None, *, supabase_jwt: str | None = None) -> dict:
    """
    Get active LLM settings for internal use.

    Two modes:
    1. **Custom LLM** (provider == "custom", api_url + api_key set in DB):
       bypass the managed gateway and hit the user's endpoint directly.
    2. **Managed gateway** (default): route through GATEWAY_BASE_URL.
    """
    db_settings = await get_or_create_settings(session)
    agent_tools_config = None
    if getattr(db_settings, "agent_tools_config", None):
        try:
            agent_tools_config = json.loads(db_settings.agent_tools_config)
        except (json.JSONDecodeError, TypeError):
            pass

    main_model = db_settings.model_name or app_settings.REASONING_MODEL
    provider = db_settings.provider or "openai"

    # ── Custom LLM bypass: user configured their own endpoint in Settings ──
    custom_url = (db_settings.api_url or "").strip()
    custom_key = (db_settings.api_key or "").strip()
    if provider == "custom" and custom_url and custom_key:
        # ScreenOps: use dedicated config if set, otherwise fall back to main LLM config
        so_api_url = (getattr(db_settings, "screenops_api_url", None) or "").strip() or custom_url
        so_api_key = (getattr(db_settings, "screenops_api_key", None) or "").strip() or custom_key
        so_model = (getattr(db_settings, "screenops_model", None) or "").strip() or main_model
        # If screenops model differs from main model, set main as fallback
        so_fallback = main_model if so_model != main_model else None
        return {
            "api_key": custom_key,
            "api_url": custom_url,
            "default_headers": {},
            "llm_unavailable_detail": None,
            "model_name": main_model,
            "provider": provider,
            "screenops_api_key": so_api_key,
            "screenops_api_url": so_api_url,
            "screenops_model": so_model,
            "screenops_coord_fallback_model": so_fallback,
            "screenops_mouse_timeout": max(5, min(120, int(getattr(db_settings, "screenops_mouse_timeout", 30) or 30))),
            "screenops_image_scale": max(25, min(100, int(getattr(db_settings, "screenops_image_scale", 100) or 100))),
            "serper_api_key": getattr(db_settings, "serper_api_key", None),
            "serper_gateway_url": "",
            "serper_gateway_token": "",
            "serper_gateway_bearer": "",
            "serper_gateway_extra_headers": {},
            "agent_tools_config": agent_tools_config,
            "enable_thinking": bool(getattr(db_settings, "enable_thinking", False)),
            "debug_logging": bool(getattr(db_settings, "debug_logging", True)),
            "max_parallel_files": 10,
        }

    # ── Managed gateway path ──
    proxy_base = _gateway_base_url()

    if not proxy_base:
        return {
            "api_key": "",
            "api_url": None,
            "default_headers": {},
            "llm_unavailable_detail": (
                "GATEWAY_BASE_URL must be configured. Managed gateway is required; "
                "or configure a custom LLM in Settings."
            ),
            "model_name": main_model,
            "provider": provider,
            "screenops_api_key": "",
            "screenops_api_url": None,
            "screenops_model": main_model,
            "screenops_coord_fallback_model": None,
            "screenops_mouse_timeout": max(5, min(120, int(getattr(db_settings, "screenops_mouse_timeout", 30) or 30))),
            "screenops_image_scale": max(25, min(100, int(getattr(db_settings, "screenops_image_scale", 100) or 100))),
            "serper_api_key": None,
            "serper_gateway_url": "",
            "serper_gateway_token": "",
            "serper_gateway_bearer": "",
            "serper_gateway_extra_headers": {},
            "agent_tools_config": agent_tools_config,
            "enable_thinking": bool(getattr(db_settings, "enable_thinking", False)),
            "debug_logging": bool(getattr(db_settings, "debug_logging", True)),
            "max_parallel_files": 10,
        }

    api_key = (db_settings.api_key or "").strip()
    api_url = f"{proxy_base}/v1"
    gw_headers: dict = {}
    llm_unavailable_detail: Optional[str] = None

    from app.services.gateway_session import gateway_supabase_token as _sb_tok_var

    sb_jwt = supabase_jwt or _sb_tok_var.get()

    if sb_jwt:
        # Enterprise path: pass Supabase JWT as api_key.
        # Worker validates it via JWKS and injects the real upstream API key.
        api_key = sb_jwt
        gw_headers = {}
    else:
        # Legacy HMAC path (email / enterprise logins without Supabase JWT).
        gw_headers = gateway_llm_headers()
        if not gw_headers:
            api_key = ""
            llm_unavailable_detail = (
                "Managed LLM gateway requires authentication. "
                "Sign in with your Lumena cloud account (Supabase JWT), "
                "or use an account with a per-user gateway HMAC secret configured."
            )
        elif not api_key:
            api_key = "sk-gateway-managed"

    if consumer_key:
        api_key = consumer_key

    # Serper and ScreenOps: always via the same gateway host (Zuplo routes /search, /screenops, etc.).
    serper_gateway_url = proxy_base
    screenops_via_gateway = True

    from app.services.gateway_screenops_config import (
        SCREENOPS_GATEWAY_CONFIG_PATH,
        ScreenOpsGatewayConfig,
        fetch_screenops_gateway_config,
    )

    gw_so_cfg = ScreenOpsGatewayConfig()
    # ScreenOps: fetch coord_api_url / coord_model / coord_api_key from Zuplo.
    if proxy_base and screenops_via_gateway:
        gw_so_cfg = await fetch_screenops_gateway_config(
            proxy_base,
            SCREENOPS_GATEWAY_CONFIG_PATH,
            sb_jwt or None,
        )

    # Chat model: prefer gateway-provided model over DB value.
    # This lets Zuplo control which model is used without touching the DB.
    gw_chat_model = (gw_so_cfg.chat_model or "").strip()
    if gw_chat_model:
        main_model = gw_chat_model

    so_url_out: Optional[str] = None
    so_key = ""
    coord_primary = main_model
    coord_fallback: Optional[str] = None

    if screenops_via_gateway and proxy_base:
        # Same gateway host, but Zuplo can route a different path to a different upstream.
        coord_path = (gw_so_cfg.coord_path or "").strip().strip("/") or "v1"
        so_url_out = f"{proxy_base}/{coord_path}"

        # Key: Zuplo-provided dedicated key for non-JWT users; otherwise JWT (same as chat)
        so_key = (gw_so_cfg.coord_api_key or "").strip() or (sb_jwt or "").strip()

        # Model name only — Zuplo tells us what to put in the request body
        zuplo_m = (gw_so_cfg.coord_model or "").strip()
        if zuplo_m and zuplo_m != main_model:
            coord_primary = zuplo_m
            coord_fallback = main_model
        else:
            coord_primary = main_model
            coord_fallback = None

    serper_bearer = (sb_jwt or "").strip()
    serper_extra_headers: dict[str, str] = dict(gw_headers) if not sb_jwt else {}

    return {
        "api_key": api_key,
        "api_url": api_url,
        "default_headers": gw_headers,
        "llm_unavailable_detail": llm_unavailable_detail,
        "model_name": main_model,
        "provider": db_settings.provider or "openai",
        # ScreenOps: Zuplo-provided URL/key/model; fallback to main on same gateway.
        "screenops_api_key": so_key,
        "screenops_api_url": so_url_out,
        "screenops_model": coord_primary,
        "screenops_coord_fallback_model": coord_fallback,
        "screenops_mouse_timeout": max(5, min(120, int(getattr(db_settings, "screenops_mouse_timeout", 30) or 30))),
        "screenops_image_scale": max(25, min(100, int(getattr(db_settings, "screenops_image_scale", 100) or 100))),
        # Serper: gateway only (Zuplo /search); no local API key
        "serper_api_key": None,
        "serper_gateway_url": serper_gateway_url,
        "serper_gateway_token": serper_bearer,
        "serper_gateway_bearer": serper_bearer,
        "serper_gateway_extra_headers": serper_extra_headers,
        "agent_tools_config": agent_tools_config,
        "enable_thinking": bool(getattr(db_settings, "enable_thinking", False)),
        "debug_logging": bool(getattr(db_settings, "debug_logging", True)),
        "max_parallel_files": 10,
    }


# ── MCP Tool Configs CRUD ──────────────────────────────────────


class McpToolConfigCreate(BaseModel):
    """Schema for creating MCP tool config(s). Accepts raw mcpServers JSON."""
    name: Optional[str] = None
    config_json: Optional[dict] = None
    # Bulk import: paste full mcpServers block
    mcp_servers: Optional[dict] = None
    enabled: bool = True


class McpToolConfigUpdate(BaseModel):
    """Schema for updating an MCP tool config."""
    name: Optional[str] = None
    config_json: Optional[dict] = None
    enabled: Optional[bool] = None


@router.get("/mcp-tools")
async def list_mcp_tool_configs(session: AsyncSession = Depends(get_session)):
    """List all configured MCP tool servers."""
    result = await session.execute(
        select(McpToolConfig).order_by(McpToolConfig.created_at.desc())
    )
    configs = result.scalars().all()
    return [c.to_dict() for c in configs]


@router.post("/mcp-tools")
async def create_mcp_tool_config(
    data: McpToolConfigCreate,
    session: AsyncSession = Depends(get_session),
):
    """Add MCP server(s) as tool sources.

    Accepts either:
    - Single server: {name, config_json}
    - Bulk import: {mcp_servers: {"github": {...}, "slack": {...}}}
    """
    created = []

    # Bulk import from mcpServers JSON
    if data.mcp_servers:
        for server_name, server_config in data.mcp_servers.items():
            config = McpToolConfig(
                name=server_name,
                config_json=server_config,
                enabled=data.enabled,
            )
            session.add(config)
            created.append(config)
        await session.flush()
        for c in created:
            await session.refresh(c)
        return [c.to_dict() for c in created]

    # Single server
    if not data.name:
        raise HTTPException(status_code=400, detail="name is required")
    if not data.config_json:
        raise HTTPException(status_code=400, detail="config_json is required")

    config = McpToolConfig(
        name=data.name,
        config_json=data.config_json,
        enabled=data.enabled,
    )
    session.add(config)
    await session.flush()
    await session.refresh(config)
    return config.to_dict()


@router.put("/mcp-tools/{config_id}")
async def update_mcp_tool_config(
    config_id: str,
    data: McpToolConfigUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an existing MCP tool config."""
    result = await session.execute(
        select(McpToolConfig).where(McpToolConfig.config_id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="MCP tool config not found")

    from datetime import datetime
    if data.name is not None:
        config.name = data.name
    if data.config_json is not None:
        config.config_json = data.config_json
    if data.enabled is not None:
        config.enabled = data.enabled
    config.updated_at = datetime.utcnow()
    await session.flush()
    return config.to_dict()


@router.delete("/mcp-tools/{config_id}")
async def delete_mcp_tool_config(
    config_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete an MCP tool config."""
    result = await session.execute(
        select(McpToolConfig).where(McpToolConfig.config_id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="MCP tool config not found")

    await session.delete(config)
    await session.flush()
    return {"ok": True}


@router.post("/mcp-tools/{config_id}/toggle")
async def toggle_mcp_tool_config(
    config_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Toggle enabled/disabled for an MCP tool config."""
    result = await session.execute(
        select(McpToolConfig).where(McpToolConfig.config_id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="MCP tool config not found")

    from datetime import datetime
    config.enabled = not config.enabled
    config.updated_at = datetime.utcnow()
    await session.flush()
    return config.to_dict()
