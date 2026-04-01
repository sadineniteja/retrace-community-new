"""
Brain Browser Manager — manages Playwright browser sessions for Brain tasks.

Extends the existing browser_manager pattern but scoped to brain_id + task_id
instead of conversation_id. Supports:
  - Cookie injection for connected accounts (LinkedIn, etc.)
  - Live screenshot streaming to Brain detail WebSocket clients
  - Anti-detection measures (user agent rotation, human-like delays)
  - Session reuse across multiple tasks for the same brain
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger()

MAX_BRAIN_SESSIONS = 5
SCREENSHOT_INTERVAL = 0.5  # ~2 FPS (saves bandwidth vs 3 FPS, still smooth)
SCREENSHOT_QUALITY = 55   # Lower quality = smaller payloads
VIEWPORT_WIDTH = 1024
VIEWPORT_HEIGHT = 700
IDLE_TIMEOUT = 15 * 60  # 15 minutes

# Rotate user agents to reduce detection
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


@dataclass
class BrainBrowserSession:
    """A browser session tied to a brain (not a conversation)."""

    brain_id: str
    task_id: Optional[str] = None
    browser: Any = None
    context: Any = None
    page: Any = None
    playwright: Any = None
    websocket_clients: set = field(default_factory=set)
    screenshot_task: Optional[asyncio.Task] = None
    last_activity: float = field(default_factory=time.time)
    current_url: str = "about:blank"
    current_title: str = ""
    status_message: str = ""
    is_running: bool = False
    # Human intervention state
    needs_human: bool = False
    alert_type: str = ""           # "captcha", "login_required", "blocked", "verification", "error"
    alert_message: str = ""
    human_resolved: bool = False
    _human_event: Optional[asyncio.Event] = field(default=None, repr=False)

    async def get_screenshot_base64(self) -> Optional[str]:
        if not self.page:
            return None
        try:
            data = await self.page.screenshot(type="jpeg", quality=SCREENSHOT_QUALITY, full_page=False)
            return base64.b64encode(data).decode("ascii")
        except Exception:
            return None

    async def navigate(self, url: str) -> dict:
        if not self.page:
            return {"error": "No browser page"}
        self.last_activity = time.time()
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self.current_url = self.page.url
            self.current_title = await self.page.title()
            return {"url": self.current_url, "title": self.current_title}
        except Exception as e:
            return {"error": str(e)}

    async def broadcast_status(self, message: str):
        """Send a status message to all connected WebSocket clients."""
        self.status_message = message
        disconnected = set()
        msg = json.dumps({"type": "brain_status", "message": message, "brain_id": self.brain_id, "task_id": self.task_id})
        for ws in self.websocket_clients:
            try:
                await ws.send_text(msg)
            except Exception:
                disconnected.add(ws)
        self.websocket_clients -= disconnected

    async def broadcast_alert(self, alert_type: str, message: str):
        """
        Send an alert to all connected clients that human intervention is needed.
        Alert types: captcha, login_required, blocked, verification, error
        """
        self.needs_human = True
        self.alert_type = alert_type
        self.alert_message = message
        self.human_resolved = False
        logger.warning("brain_needs_human", brain_id=self.brain_id, alert_type=alert_type, message=message)

        disconnected = set()
        msg = json.dumps({
            "type": "brain_alert",
            "alert_type": alert_type,
            "message": message,
            "brain_id": self.brain_id,
            "task_id": self.task_id,
            "needs_human": True,
        })
        for ws in self.websocket_clients:
            try:
                await ws.send_text(msg)
            except Exception:
                disconnected.add(ws)
        self.websocket_clients -= disconnected

    async def request_human_help(self, alert_type: str, message: str, timeout_seconds: int = 300) -> bool:
        """
        Pause task execution and wait for human to resolve a blockage.

        Broadcasts an alert, then waits up to `timeout_seconds` for the user
        to interact with the browser (solve captcha, log in, etc.) and click
        "Resume" in the UI.

        Returns True if human resolved it, False if timed out.
        """
        self._human_event = asyncio.Event()
        self.human_resolved = False

        await self.broadcast_alert(alert_type, message)

        try:
            await asyncio.wait_for(self._human_event.wait(), timeout=timeout_seconds)
            return self.human_resolved
        except asyncio.TimeoutError:
            logger.warning("human_help_timeout", brain_id=self.brain_id, alert_type=alert_type)
            self.needs_human = False
            self.alert_type = ""
            self.alert_message = ""
            await self.broadcast_status("Human help timed out — resuming task")
            return False

    def resolve_human_help(self):
        """Called when the user clicks 'Resume' after resolving a blockage."""
        self.needs_human = False
        self.human_resolved = True
        self.alert_type = ""
        self.alert_message = ""
        if self._human_event:
            self._human_event.set()


class BrainBrowserManager:
    """Manages browser sessions for Brain tasks, keyed by brain_id."""

    def __init__(self):
        self._sessions: dict[str, BrainBrowserSession] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def get_session(self, brain_id: str) -> Optional[BrainBrowserSession]:
        """Get an existing session for a brain (if any)."""
        return self._sessions.get(brain_id)

    async def get_or_create(
        self,
        brain_id: str,
        task_id: Optional[str] = None,
        cookies: Optional[list[dict]] = None,
        user_agent: Optional[str] = None,
    ) -> BrainBrowserSession:
        """Get or create a browser session for a brain."""
        async with self._lock:
            if brain_id in self._sessions:
                session = self._sessions[brain_id]
                session.task_id = task_id
                session.last_activity = time.time()
                session.is_running = True
                return session

            # Evict oldest if at capacity
            if self.active_count >= MAX_BRAIN_SESSIONS:
                oldest_id = min(self._sessions, key=lambda k: self._sessions[k].last_activity)
                await self._close_session_unlocked(oldest_id)

            session = BrainBrowserSession(brain_id=brain_id, task_id=task_id)
            try:
                from playwright.async_api import async_playwright

                session.playwright = await async_playwright().start()
                session.browser = await session.playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                )

                ua = user_agent or random.choice(USER_AGENTS)
                session.context = await session.browser.new_context(
                    viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                    user_agent=ua,
                    locale="en-US",
                    timezone_id="America/New_York",
                )

                # Inject anti-detection scripts
                await session.context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    window.chrome = {runtime: {}};
                """)

                # Inject cookies if provided
                if cookies:
                    await session.context.add_cookies(cookies)
                    logger.info("brain_cookies_injected", brain_id=brain_id, count=len(cookies))

                session.page = await session.context.new_page()
                session.is_running = True

                # Start screenshot streaming
                session.screenshot_task = asyncio.create_task(self._screenshot_loop(session))

                self._sessions[brain_id] = session
                logger.info("brain_browser_created", brain_id=brain_id, active=self.active_count)
                return session

            except Exception as e:
                logger.error("brain_browser_create_failed", error=str(e))
                await self._cleanup_session(session)
                raise

    async def close_session(self, brain_id: str):
        async with self._lock:
            await self._close_session_unlocked(brain_id)

    async def _close_session_unlocked(self, brain_id: str):
        session = self._sessions.pop(brain_id, None)
        if session:
            await self._cleanup_session(session)
            logger.info("brain_browser_closed", brain_id=brain_id)

    async def _cleanup_session(self, session: BrainBrowserSession):
        session.is_running = False
        if session.screenshot_task:
            session.screenshot_task.cancel()
            try:
                await session.screenshot_task
            except (asyncio.CancelledError, Exception):
                pass

        for ws in list(session.websocket_clients):
            try:
                await ws.send_text(json.dumps({
                    "type": "brain_browser_closed",
                    "brain_id": session.brain_id,
                }))
            except Exception:
                pass
        session.websocket_clients.clear()

        try:
            if session.context:
                await session.context.close()
            if session.browser:
                await session.browser.close()
            if session.playwright:
                await session.playwright.stop()
        except Exception as e:
            logger.warning("brain_browser_cleanup_error", error=str(e))

    async def _screenshot_loop(self, session: BrainBrowserSession):
        """Broadcast screenshots to WebSocket clients at ~3 FPS."""
        last_data = None
        while True:
            try:
                await asyncio.sleep(SCREENSHOT_INTERVAL)

                if not session.websocket_clients:
                    continue

                screenshot_b64 = await session.get_screenshot_base64()
                if not screenshot_b64 or screenshot_b64 == last_data:
                    continue
                last_data = screenshot_b64

                if session.page:
                    try:
                        session.current_url = session.page.url
                        session.current_title = await session.page.title()
                    except Exception:
                        pass

                message = json.dumps({
                    "type": "brain_screenshot",
                    "data": screenshot_b64,
                    "url": session.current_url,
                    "title": session.current_title,
                    "brain_id": session.brain_id,
                    "task_id": session.task_id,
                    "status": session.status_message,
                })

                disconnected = set()
                for ws in session.websocket_clients:
                    try:
                        await ws.send_text(message)
                    except Exception:
                        disconnected.add(ws)
                session.websocket_clients -= disconnected

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("brain_screenshot_error", error=str(e))
                await asyncio.sleep(1)

    async def close_all(self):
        async with self._lock:
            for bid in list(self._sessions.keys()):
                await self._close_session_unlocked(bid)


# Singleton
brain_browser_manager = BrainBrowserManager()
