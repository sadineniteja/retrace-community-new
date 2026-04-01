"""
ReTrace Main Application Entry Point

FastAPI backend with WebSocket support for browser and terminal sessions.
Lumena Technologies — lumenatech.io
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
import structlog
import time

from app.core.config import settings
from app.core.logging import setup_logging
from app.api import groups, products, training, query, health, settings as settings_api, files as files_api
from app.api import agent as agent_api
from app.api import terminal_ws as terminal_ws_api
from app.api import browser_ws as browser_ws_api
from app.api import mcp_builder as mcp_builder_api
from app.api import brains as brains_api
from app.api import brain_interview as brain_interview_api
from app.api import connected_accounts as connected_accounts_api
from app.api import brain_tasks as brain_tasks_api
from app.api import approvals as approvals_api
from app.api import brain_monitors as brain_monitors_api
from app.api import pipeline as pipeline_api
from app.api import brain_activity as brain_activity_api
from app.api import brain_dashboard as brain_dashboard_api
from app.api import brain_files as brain_files_api
from app.api import brain_browser_ws as brain_browser_ws_api
from app.services.websocket_manager import websocket_manager
from app.db.database import init_db
from app.models.automation_run import AutomationRun  # ensure table creation
# Import models to ensure they're registered with Base
from app.models import pod, folder_group, product, query as query_model, settings as settings_model
from app.models import agent_session as agent_session_model  # noqa: F401  – registers AgentSession table
from app.models import terminal_session as terminal_session_model  # noqa: F401  – registers TerminalSession table
from app.models import sop as sop_model  # noqa: F401  – registers SOP table
from app.models import documentation as documentation_model  # noqa: F401  – registers Documentation table
from app.rag import models as rag_models  # noqa: F401  – registers ChunkRecord table
from app.models import channel_connection as channel_connection_model  # noqa: F401
from app.models import tenant as tenant_model  # noqa: F401
# Brain platform models
from app.models import brain_template as brain_template_model  # noqa: F401
from app.models import brain as brain_model  # noqa: F401
from app.models import connected_account as connected_account_model  # noqa: F401
from app.models import brain_schedule as brain_schedule_model  # noqa: F401
from app.models import pipeline_item as pipeline_item_model  # noqa: F401
from app.models import brain_task as brain_task_model  # noqa: F401
from app.models import brain_monitor as brain_monitor_model  # noqa: F401
from app.models import brain_activity as brain_activity_model  # noqa: F401
from app.models import approval_request as approval_request_model  # noqa: F401
from app.models import user_session as user_session_model  # noqa: F401
from app.models import product_access as product_access_model  # noqa: F401
from app.models import audit_log as audit_log_model  # noqa: F401
from app.models import mcp_server as mcp_server_model  # noqa: F401  – registers McpServer table
from app.models import mcp_tool_config as mcp_tool_config_model  # noqa: F401
from app.api import auth as auth_api

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    # Startup
    setup_logging()
    logger.info("Starting ReTrace", version=settings.APP_VERSION)

    # Capture the asyncio event loop for PTY manager's background threads
    import asyncio as _asyncio
    from app.services.pty_manager import pty_manager as _pty_mgr
    _pty_mgr.set_event_loop(_asyncio.get_running_loop())

    await init_db()
    logger.info("Database initialized", db_url=settings.DATABASE_URL)
    print(f"[STARTUP] Database URL: {settings.DATABASE_URL}", flush=True)
    
    # Migration: add agent_tools_config column to llm_settings if missing
    try:
        import sqlite3
        from pathlib import Path
        from urllib.parse import unquote
        db_url = settings.DATABASE_URL
        if "sqlite" in db_url:
            # Extract path: sqlite+aiosqlite:///path or sqlite:///path
            parsed = db_url.split("///", 1)[-1].split("?", 1)[0]
            db_path = unquote(parsed)
            if not Path(db_path).is_absolute():
                # Resolve relative to backend/ (parent of app/), same as app CWD
                backend_dir = Path(__file__).parent.parent
                db_path = str((backend_dir / parsed).resolve())
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(llm_settings)")
            cols = [row[1] for row in cursor.fetchall()]
            if "agent_tools_config" not in cols:
                cursor.execute("ALTER TABLE llm_settings ADD COLUMN agent_tools_config TEXT")
                conn.commit()
                print("[STARTUP] Added agent_tools_config column to llm_settings", flush=True)
            if "debug_logging" not in cols:
                cursor.execute("ALTER TABLE llm_settings ADD COLUMN debug_logging INTEGER")
                conn.commit()
                print("[STARTUP] Added debug_logging column to llm_settings", flush=True)
            if "max_parallel_files" not in cols:
                cursor.execute("ALTER TABLE llm_settings ADD COLUMN max_parallel_files INTEGER DEFAULT 1")
                conn.commit()
                print("[STARTUP] Added max_parallel_files column to llm_settings", flush=True)
            if "screenops_mouse_timeout" not in cols:
                cursor.execute("ALTER TABLE llm_settings ADD COLUMN screenops_mouse_timeout INTEGER DEFAULT 30")
                conn.commit()
                print("[STARTUP] Added screenops_mouse_timeout column to llm_settings", flush=True)
            if "screenops_image_scale" not in cols:
                cursor.execute("ALTER TABLE llm_settings ADD COLUMN screenops_image_scale INTEGER DEFAULT 100")
                conn.commit()
                print("[STARTUP] Added screenops_image_scale column to llm_settings", flush=True)
            if "agent_max_iterations" not in cols:
                cursor.execute("ALTER TABLE llm_settings ADD COLUMN agent_max_iterations INTEGER DEFAULT 10")
                conn.commit()
                print("[STARTUP] Added agent_max_iterations column to llm_settings", flush=True)
            if "serper_api_key" not in cols:
                cursor.execute("ALTER TABLE llm_settings ADD COLUMN serper_api_key TEXT")
                conn.commit()
                print("[STARTUP] Added serper_api_key column to llm_settings", flush=True)
            conn.close()
    except Exception as exc:
        print(f"[STARTUP] llm_settings migration skipped: {exc}", flush=True)
    
    # Ensure synthetic __local__ pod exists for local filesystem browse
    try:
        from sqlalchemy import select
        from app.db.database import async_session_maker
        from app.models.pod import Pod

        async with async_session_maker() as session:
            result = await session.execute(select(Pod).where(Pod.pod_id == "__local__"))
            if result.scalar_one_or_none() is None:
                local_pod = Pod(
                    pod_id="__local__",
                    pod_name="Local",
                    os_type="local",
                    status="online",
                    metadata_json={"synthetic": True, "description": "Backend server local filesystem"},
                )
                session.add(local_pod)
                await session.commit()
                print("[STARTUP] Created synthetic __local__ pod for local filesystem browse", flush=True)
    except Exception as exc:
        print(f"[STARTUP] __local__ pod creation skipped: {exc}", flush=True)

    # Ensure default administrator account exists (login: administrator, password: D12345678)
    _DEFAULT_ADMIN_PASSWORD = "D12345678"
    try:
        from sqlalchemy import select, func
        from app.db.database import async_session_maker
        from app.models.user import User
        from app.core.security import hash_password

        async with async_session_maker() as session:
            # Case-insensitive lookup (DB may have "Administrator" or "administrator")
            result = await session.execute(
                select(User).where(func.lower(User.email) == "administrator")
            )
            admin = result.scalar_one_or_none()
            if admin is None:
                admin = User(
                    email="administrator",
                    display_name="Administrator",
                    hashed_password=hash_password(_DEFAULT_ADMIN_PASSWORD),
                    role="admin",
                    auth_provider="email",
                    force_password_change=False,
                )
                session.add(admin)
                await session.commit()
                print("[STARTUP] Created default administrator account (username: administrator, password: D12345678)", flush=True)
            else:
                # Normalize email to lowercase and reset password
                admin.email = "administrator"
                admin.hashed_password = hash_password(_DEFAULT_ADMIN_PASSWORD)
                admin.force_password_change = False
                admin.is_active = True
                await session.commit()
                print("[STARTUP] Reset administrator password to D12345678", flush=True)
    except Exception as exc:
        print(f"[STARTUP] Default admin creation skipped: {exc}", flush=True)

    # Ensure default organization (single-tenant) exists
    try:
        from app.models.tenant import Tenant
        async with async_session_maker() as session:
            result = await session.execute(select(Tenant))
            if result.scalar_one_or_none() is None:
                default_tenant = Tenant(
                    name="Default Organization",
                    domain="local",
                    auth_method="email",
                )
                session.add(default_tenant)
                await session.commit()
                print("[STARTUP] Created default organization (domain: local)", flush=True)
    except Exception as exc:
        print(f"[STARTUP] Default organization creation skipped: {exc}", flush=True)

    # Auto-install Playwright browsers if not already present
    try:
        import subprocess as _sp
        _check = _sp.run(
            ["python", "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=10,
        )
        if _check.returncode != 0:
            print("[STARTUP] Installing Playwright Chromium browser...", flush=True)
            _result = _sp.run(
                ["python", "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=120,
            )
            if _result.returncode == 0:
                print("[STARTUP] Playwright Chromium installed successfully", flush=True)
            else:
                print(f"[STARTUP] Playwright install warning: {_result.stderr[:200]}", flush=True)
        else:
            print("[STARTUP] Playwright Chromium already installed", flush=True)
    except Exception as _pw_exc:
        print(f"[STARTUP] Playwright auto-install skipped: {_pw_exc}", flush=True)

    # Seed brain templates
    try:
        from app.services.brain_template_seeder import seed_brain_templates
        await seed_brain_templates()
    except Exception as exc:
        print(f"[STARTUP] Brain template seeding skipped: {exc}", flush=True)

    # Start automation scheduler
    from app.services.scheduler_service import automation_scheduler
    await automation_scheduler.start()
    logger.info("Automation scheduler started")

    # Start WebSocket server in background
    asyncio.create_task(websocket_manager.start_server())
    logger.info("WebSocket server starting", port=settings.WEBSOCKET_PORT)

    # Start brain task worker and scheduler
    from app.services.task_worker import task_worker
    await task_worker.start()
    from app.services.brain_scheduler import brain_scheduler
    await brain_scheduler.start()
    from app.services.monitor_service import monitor_service
    await monitor_service.start()
    logger.info("Brain task worker, scheduler, and monitor service started")

    # Start email poller (checks every 60s for new unread emails)
    from app.services.email_poller import email_poller
    await email_poller.start()

    yield

    # Shutdown
    logger.info("Shutting down ReTrace")
    from app.services.pty_manager import pty_manager
    pty_manager.destroy_all()
    from app.services.scheduler_service import automation_scheduler
    await automation_scheduler.stop()
    from app.services.task_worker import task_worker as _tw
    await _tw.stop()
    from app.services.brain_scheduler import brain_scheduler as _bs
    await _bs.stop()
    from app.services.monitor_service import monitor_service as _ms
    await _ms.stop()
    from app.services.email_poller import email_poller as _ep
    await _ep.stop()
    # Close all browser sessions
    from app.services.browser_manager import browser_manager as _bm
    await _bm.close_all()
    from app.services.brain_browser_manager import brain_browser_manager as _bbm
    await _bbm.close_all()
    await websocket_manager.shutdown()


app = FastAPI(
    title="ReTrace API",
    description="Distributed Enterprise Knowledge Management — Lumena Technologies",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Request logging middleware (add before CORS) - simplified to avoid blocking
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    # Use print for immediate logging (structlog might be blocking)
    print(f"[REQUEST] {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        print(f"[REQUEST] {request.method} {request.url.path} - {response.status_code} ({process_time:.3f}s)")
        return response
    except Exception as e:
        process_time = time.time() - start_time
        print(f"[ERROR] {request.method} {request.url.path} - {str(e)} ({process_time:.3f}s)")
        raise


@app.middleware("http")
async def llm_gateway_user_context(request: Request, call_next):
    """
    Bind user_id and, for Supabase JWT bearers, the raw token itself to context.

    Supabase JWT path: the token is stored in gateway_supabase_token so
    get_active_llm_settings can use it as the api_key for the managed gateway.
    The Cloudflare Worker verifies the JWT via JWKS and injects the real API key —
    no HMAC secret ever touches this server.

    HMAC path (email / enterprise): existing session secret is used unchanged.
    """
    from jose import jwt as jose_jwt, JWTError
    from app.services.gateway_session import (
        llm_gateway_request_user_id,
        gateway_supabase_token,
    )
    from app.db.database import async_session_maker
    from app.services.auth.supabase_access import try_decode_supabase_access_token
    from app.services.auth.supabase_user import resolve_supabase_user

    user_id = None
    supabase_jwt: Optional[str] = None

    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            # Try ReTrace JWT first (email / enterprise logins)
            try:
                payload = jose_jwt.decode(
                    token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
                )
                if payload.get("type") == "access" and payload.get("sub"):
                    user_id = str(payload["sub"])
            except JWTError:
                pass

            # Supabase JWT (cloud auth) — just resolve the local user, store the token
            if not user_id and (settings.SUPABASE_URL or "").strip():
                sb = try_decode_supabase_access_token(token)
                if sb:
                    async with async_session_maker() as db:
                        try:
                            user = await resolve_supabase_user(db, sb, touch_login=False)
                            await db.commit()
                            if user:
                                user_id = user.user_id
                        except Exception:
                            await db.rollback()
                    if user_id:
                        supabase_jwt = token  # Worker will verify this directly

    tok_var = llm_gateway_request_user_id.set(user_id)
    sb_var = gateway_supabase_token.set(supabase_jwt)
    response = await call_next(request)
    # StreamingResponse returns before the body is consumed; resetting in `finally`
    # here would clear gateway_supabase_token before agent/SSE handlers run.
    if isinstance(response, StreamingResponse):
        original_iterator = response.body_iterator

        async def _gateway_context_preserved_stream():
            try:
                async for chunk in original_iterator:
                    yield chunk
            finally:
                llm_gateway_request_user_id.reset(tok_var)
                gateway_supabase_token.reset(sb_var)

        return StreamingResponse(
            _gateway_context_preserved_stream(),
            status_code=response.status_code,
            headers=response.headers,
            media_type=response.media_type,
            background=response.background,
        )

    llm_gateway_request_user_id.reset(tok_var)
    gateway_supabase_token.reset(sb_var)
    return response


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_api.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(health.router, tags=["Health"])
app.include_router(groups.router, prefix="/api/v1/groups", tags=["Folder Groups"])
app.include_router(products.router, prefix="/api/v1/products", tags=["Products"])
app.include_router(training.router, prefix="/api/v1/training", tags=["Training"])
app.include_router(query.router, prefix="/api/v1/query", tags=["Query"])
app.include_router(settings_api.router, prefix="/api/v1/settings", tags=["Settings"])
app.include_router(agent_api.router, prefix="/api/v1/agent", tags=["Agent"])
app.include_router(files_api.router, prefix="/api/v1/files", tags=["Local Files"])
app.include_router(terminal_ws_api.router, tags=["Terminal WebSocket"])
app.include_router(browser_ws_api.router, tags=["Browser WebSocket"])
app.include_router(mcp_builder_api.router, prefix="/api/v1/mcp-builder", tags=["MCP Builder"])
app.include_router(brains_api.router, prefix="/api/v1/brains", tags=["Brains"])
app.include_router(brain_interview_api.router, prefix="/api/v1/brains", tags=["Brain Interview"])
app.include_router(connected_accounts_api.router, prefix="/api/v1/brains", tags=["Connected Accounts"])
app.include_router(brain_tasks_api.router, prefix="/api/v1/brains", tags=["Brain Tasks"])
app.include_router(approvals_api.router, prefix="/api/v1/approvals", tags=["Approvals"])
app.include_router(brain_monitors_api.router, prefix="/api/v1/brains", tags=["Brain Monitors"])
app.include_router(pipeline_api.router, prefix="/api/v1/brains", tags=["Pipeline"])
app.include_router(brain_activity_api.router, prefix="/api/v1/brains", tags=["Brain Activity"])
app.include_router(brain_dashboard_api.router, prefix="/api/v1/brain-dashboard", tags=["Brain Dashboard"])
app.include_router(brain_files_api.router, prefix="/api/v1/brains", tags=["Brain Files"])
app.include_router(brain_browser_ws_api.router, tags=["Brain Browser WebSocket"])

# RAG product-assistant router
from app.rag.api import router as rag_router
app.include_router(rag_router, prefix="/api/v1/product-assistant", tags=["Product Assistant"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "ReTrace API",
        "version": settings.APP_VERSION,
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
