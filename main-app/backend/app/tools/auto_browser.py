"""
AutoBrowser — Enterprise browser automation tool for the ReTrace agent.

Provides granular, composable browser actions that the agent calls directly:
  navigate, screenshot, click, type, read_page, scroll, press_key, wait,
  extract_text, fill_form, select_option, hover, evaluate_js

All actions operate on the **shared BrowserManager session** so every action
is streamed live to the user's Browser Workspace panel via WebSocket.

Screenshots are analysed by the main LLM (via managed gateway) so the agent
can reason about what it sees on screen.

Hybrid content analysis strategy
---------------------------------
When the agent needs page content, it calls **analyze_page** first which
returns token costs for read_page vs screenshot approaches.

If the LLM chooses the *screenshot* path:
  1. screenshot_full_page — captures all viewport tiles, sends them bundled
     to the LLM in one vision call so it can see the entire page.
  2. The LLM identifies the section of interest and names a CSS selector.
  3. read_page(selector='#that-section') — targeted text extraction of just
     the relevant section (links, data, etc.).

If the LLM chooses the *read_page* path, it just reads directly — no
screenshot logic involved.
"""

from __future__ import annotations

import asyncio
import base64
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog
from langchain_core.tools import StructuredTool

from app.services.browser_manager import browser_manager, SCREENSHOT_HEIGHT
from app.tools.analysis import analyze_extraction_options
from app.tools.token_analyzer import calculate_screenshot_count
from app.tools.axtree import extract_interactive_nodes, get_overlay_roles, snapshot_hash
from app.tools.som_annotator import annotate_som

# Directory for saving screenshots sent to vision/coordinate models
_BROWSER_SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / "browser_screenshots"


def _save_screenshot(b64: str, label: str) -> Optional[str]:
    """Save a base64 screenshot to disk for debugging. Returns the file path or None."""
    try:
        _BROWSER_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        safe_label = label.replace(" ", "_").replace("/", "_")[:50]
        path = _BROWSER_SCREENSHOTS_DIR / f"{ts}_{safe_label}.jpg"
        path.write_bytes(base64.b64decode(b64))
        return str(path)
    except Exception:
        return None

logger = structlog.get_logger()

# Max chars returned from page text extraction
MAX_TEXT_LENGTH = 8000


async def _notify_ws_clients(session: Any, message: str) -> None:
    """Send a status message to all WebSocket clients watching this session."""
    import json as _json
    payload = _json.dumps({"type": "status", "message": message, "url": session.current_url})
    disconnected = set()
    for ws in session.websocket_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)
    session.websocket_clients -= disconnected


async def _notify_click_indicator(session: Any, x: int, y: int) -> None:
    """Broadcast click coordinates so the frontend can show a visual cursor indicator."""
    import json as _json
    payload = _json.dumps({"type": "click_indicator", "x": x, "y": y})
    disconnected = set()
    for ws in session.websocket_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)
    session.websocket_clients -= disconnected


async def _push_screenshot_to_ws(session: Any) -> None:
    """Force an immediate screenshot broadcast to WebSocket clients."""
    if not session.websocket_clients or not session.page:
        return
    try:
        b64 = await session.get_screenshot_base64()
        if not b64:
            return
        session.current_url = session.page.url
        session.current_title = await session.page.title()
        import json as _json
        payload = _json.dumps({
            "type": "screenshot",
            "data": b64,
            "url": session.current_url,
            "title": session.current_title,
        })
        disconnected = set()
        for ws in session.websocket_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.add(ws)
        session.websocket_clients -= disconnected
    except Exception:
        pass


async def _verify_click_effect(page: Any, pre_url: str, pre_hash: str) -> dict:
    """Check whether a click had any observable effect on the page.

    Returns dict with 'verified' bool and 'change' description.
    """
    import asyncio as _asyncio
    await _asyncio.sleep(0.6)
    try:
        new_url = page.url
        if new_url != pre_url:
            return {"verified": True, "change": "url"}
        new_hash = await snapshot_hash(page)
        if new_hash and pre_hash and new_hash != pre_hash:
            return {"verified": True, "change": "dom"}
    except Exception:
        pass
    return {"verified": False, "change": "none"}


async def _auto_browser(
    action: str,
    url: str = "",
    selector: str = "",
    text: str = "",
    x: int = 0,
    y: int = 0,
    key: str = "",
    direction: str = "down",
    amount: int = 300,
    js_expression: str = "",
    seconds: float = 1.0,
    describe_screenshot: bool = False,
    target: str = "",
    chat_model: Any = None,
    coordinate_finder: Optional[Any] = None,
    conversation_id: Optional[str] = None,
    output_callback: Optional[Any] = None,
) -> str:
    """Execute a browser action and return the result as JSON.

    Actions
    -------
    navigate     : Go to a URL. Params: url
    screenshot   : Take a screenshot. Set describe_screenshot=True to get an
                   LLM description of what's on screen.
    click        : Click at (x, y) coordinates.
    click_element: Click the first element matching a CSS selector.
    type         : Type text into the currently focused element.
    fill         : Fill a form field found by CSS selector with text.
    read_page    : Extract visible text content from the page (or a selector).
    scroll       : Scroll the page. Params: direction (up/down), amount (pixels).
    press_key    : Press a keyboard key (Enter, Tab, Escape, etc.).
    hover        : Hover over (x, y) coordinates or a CSS selector.
    select_option: Select a <select> option by value or label.
    wait         : Wait for a number of seconds (max 10).
    evaluate_js  : Run a JavaScript expression in the page and return the result.
    back         : Go back in history.
    forward      : Go forward in history.
    refresh      : Reload the page.
    get_url      : Return the current page URL and title.
    """
    if not conversation_id:
        return json.dumps({"error": "No conversation_id — cannot create browser session"})

    import time as _time
    _t0 = _time.monotonic()
    logger.info("auto_browser_start", action=action, url=url[:200] if url else "", describe_screenshot=describe_screenshot)

    try:
        session = await browser_manager.get_or_create(conversation_id)
        page = session.page
        if not page:
            return json.dumps({"error": "Browser page not available"})

        # Notify workspace clients that a tool action is happening
        await _notify_ws_clients(session, f"Agent: {action}...")

        result: dict[str, Any] = {"action": action, "ok": True}

        # ── Navigation ─────────────────────────────────────────────
        if action == "navigate":
            if not url:
                return json.dumps({"error": "url is required for navigate"})
            if output_callback:
                output_callback(f"Navigating to {url}...")
            nav = await session.navigate(url)
            if "error" in nav:
                return json.dumps({"error": nav["error"]})
            result["url"] = nav.get("url", url)
            result["title"] = nav.get("title", "")

            # Auto-describe only when explicitly requested via describe_screenshot.
            # Skipping by default keeps navigate fast (~1s vs ~10-40s with vision).
            if describe_screenshot and chat_model:
                await asyncio.sleep(1)  # wait for page to render
                b64 = await session.get_screenshot_base64()
                if b64:
                    _save_screenshot(b64, f"navigate_describe_{url[:40]}")
                    try:
                        from langchain_core.messages import HumanMessage
                        resp = await chat_model.ainvoke([HumanMessage(content=[
                            {"type": "text", "text": (
                                "Briefly describe this page. "
                                "List: purpose, main text, key UI elements. "
                                "Be concise — max 150 words."
                            )},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ])], max_tokens=300)
                        result["page_description"] = resp.content if hasattr(resp, "content") else str(resp)
                    except Exception as exc:
                        result["page_description"] = f"(vision failed: {exc})"
                else:
                    result["page_description"] = "(screenshot not available)"
            else:
                result["hint"] = "Page loaded. Use read_page() to extract text or screenshot(describe_screenshot=True) for visual analysis."

        # ── Screenshot (+ optional LLM description) ────────────────
        elif action == "screenshot":
            b64 = await session.get_screenshot_base64()
            if not b64:
                return json.dumps({"error": "Screenshot capture failed"})
            _save_screenshot(b64, "screenshot_describe" if describe_screenshot else "screenshot")
            result["screenshot_length"] = len(b64)
            result["url"] = session.current_url
            result["title"] = session.current_title

            if describe_screenshot and chat_model:
                try:
                    from langchain_core.messages import HumanMessage
                    prompt_text = (
                        "Briefly describe this browser screenshot. "
                        "List: page title/purpose, main visible text, key UI elements "
                        "(buttons, links, forms, inputs), and any errors. "
                        "Be concise — max 200 words."
                    )
                    resp = await chat_model.ainvoke(
                        [HumanMessage(content=[
                            {"type": "text", "text": prompt_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ])],
                        max_tokens=400,
                    )
                    result["description"] = resp.content if hasattr(resp, "content") else str(resp)
                except Exception as exc:
                    result["description"] = f"Vision analysis failed: {exc}"
            else:
                result["description"] = (
                    "Screenshot captured. Use describe_screenshot=True to get "
                    "an AI description of the page content."
                )

        # ── Full-page screenshot tiles bundled into one LLM call ──
        elif action == "screenshot_full_page":
            """Scroll through the entire page, capture viewport-sized tiles,
            and send ALL tiles to the LLM in a single vision call.

            The LLM describes each section it sees and suggests CSS selectors
            so the agent can follow up with a targeted read_page(selector=...).
            """
            if not chat_model:
                return json.dumps({"error": "screenshot_full_page requires a chat model for vision analysis"})

            try:
                page_height = await page.evaluate("document.body.scrollHeight")
                num_tiles = calculate_screenshot_count(page_height, SCREENSHOT_HEIGHT)
                # Cap at 10 tiles to avoid excessive token use
                num_tiles = min(num_tiles, 10)

                if output_callback:
                    output_callback(f"Capturing {num_tiles} screenshot tile(s) for full-page analysis...")

                await _notify_ws_clients(session, f"Capturing {num_tiles} tiles...")

                # Scroll to top first
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(0.3)

                tiles_b64: list[str] = []
                for i in range(num_tiles):
                    scroll_y = i * SCREENSHOT_HEIGHT
                    await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    await asyncio.sleep(0.25)  # let paint settle
                    b64 = await session.get_screenshot_base64()
                    if b64:
                        tiles_b64.append(b64)
                        _save_screenshot(b64, f"fullpage_tile_{i+1}")

                # Scroll back to top
                await page.evaluate("window.scrollTo(0, 0)")

                if not tiles_b64:
                    return json.dumps({"error": "Failed to capture any screenshot tiles"})

                # Build multi-image message for LLM
                from langchain_core.messages import HumanMessage

                content_parts: list[dict] = [
                    {"type": "text", "text": (
                        f"{len(tiles_b64)} tiles of this page (top to bottom). "
                        "Briefly describe each tile, then give a SUMMARY with: "
                        "1) page purpose, 2) key sections with CSS selectors for "
                        "read_page(selector='...'). Be concise — max 300 words."
                    )},
                ]
                for idx, tile_b64 in enumerate(tiles_b64):
                    content_parts.append(
                        {"type": "text", "text": f"--- Tile {idx + 1}/{len(tiles_b64)} ---"}
                    )
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{tile_b64}"}}
                    )

                resp = await chat_model.ainvoke(
                    [HumanMessage(content=content_parts)],
                    max_tokens=600,
                )
                description = resp.content if hasattr(resp, "content") else str(resp)

                result["num_tiles"] = len(tiles_b64)
                result["page_height_px"] = page_height
                result["url"] = session.current_url
                result["title"] = session.current_title
                result["full_page_description"] = description
                result["hint"] = (
                    "Use the CSS selectors from the description above to do a targeted "
                    "read_page(selector='...') to extract just the section you need."
                )

            except Exception as exc:
                return json.dumps({"error": f"screenshot_full_page failed: {exc}"})

        # ── Click at coordinates ───────────────────────────────────
        elif action == "click":
            if x and y:
                await _notify_click_indicator(session, x, y)
                await page.mouse.click(x, y)
                await asyncio.sleep(0.5)
                try:
                    session.current_url = page.url
                    session.current_title = await page.title()
                except Exception:
                    session.current_url = page.url or ""
                    session.current_title = ""
                result["clicked"] = {"x": x, "y": y}
                result["url"] = session.current_url
                result["title"] = session.current_title
            else:
                return json.dumps({
                    "error": "click requires x,y coordinates. "
                    "Use click_target(target='description') for vision-based clicking, "
                    "or click_element(selector) for CSS selector clicking."
                })

        # ── Click element by CSS selector ──────────────────────────
        elif action == "click_element":
            if not selector:
                return json.dumps({"error": "selector is required for click_element"})
            try:
                elem = page.locator(selector).first
                await elem.click(timeout=5000)
                await asyncio.sleep(0.5)
                try:
                    session.current_url = page.url
                    session.current_title = await page.title()
                except Exception:
                    session.current_url = page.url or ""
                    session.current_title = ""
                result["url"] = session.current_url
                result["title"] = session.current_title
            except Exception as exc:
                return json.dumps({"error": f"click_element failed: {exc}"})

        # ── Click target by vision (ScreenOps coordinate finder) ──
        elif action == "click_target":
            if not target:
                return json.dumps({"error": "target is required for click_target. Describe the element to click, e.g. target='the blue Sign In button'"})
            if not coordinate_finder:
                return json.dumps({"error": "click_target requires a coordinate finder model. Configure ScreenOps API in Settings, or use click_element(selector) instead."})

            b64 = await session.get_screenshot_base64()
            if not b64:
                return json.dumps({"error": "Screenshot capture failed for coordinate finding"})
            _save_screenshot(b64, f"click_target_{target[:40]}")

            if output_callback:
                output_callback(f"Finding coordinates for: {target}...")
            await _notify_ws_clients(session, f"Finding: {target}...")

            try:
                from app.services.browser_manager import SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT
                coords, coord_usage = coordinate_finder(
                    screenshot_base64=b64,
                    target_description=target,
                    screen_width=SCREENSHOT_WIDTH,
                    screen_height=SCREENSHOT_HEIGHT,
                    image_width=SCREENSHOT_WIDTH,
                    image_height=SCREENSHOT_HEIGHT,
                )
                if coords and coords.get("x") is not None and coords.get("y") is not None:
                    cx, cy = int(coords["x"]), int(coords["y"])
                    cx = max(0, min(cx, SCREENSHOT_WIDTH - 1))
                    cy = max(0, min(cy, SCREENSHOT_HEIGHT - 1))
                    pre_url = page.url
                    pre_h = await snapshot_hash(page)
                    await _notify_click_indicator(session, cx, cy)
                    await page.mouse.click(cx, cy)
                    verification = await _verify_click_effect(page, pre_url, pre_h)
                    retries = 0
                    # Retry once if click had no effect
                    if not verification["verified"]:
                        retries = 1
                        b64_retry = await session.get_screenshot_base64()
                        if b64_retry:
                            coords2, _ = coordinate_finder(
                                screenshot_base64=b64_retry,
                                target_description=target,
                                screen_width=SCREENSHOT_WIDTH,
                                screen_height=SCREENSHOT_HEIGHT,
                                image_width=SCREENSHOT_WIDTH,
                                image_height=SCREENSHOT_HEIGHT,
                            )
                            if coords2 and coords2.get("x") is not None:
                                cx2 = max(0, min(int(coords2["x"]), SCREENSHOT_WIDTH - 1))
                                cy2 = max(0, min(int(coords2["y"]), SCREENSHOT_HEIGHT - 1))
                                await _notify_click_indicator(session, cx2, cy2)
                                await page.mouse.click(cx2, cy2)
                                verification = await _verify_click_effect(page, pre_url, pre_h)
                                if verification["verified"]:
                                    cx, cy = cx2, cy2
                    try:
                        session.current_url = page.url
                        session.current_title = await page.title()
                    except Exception:
                        session.current_url = page.url or ""
                        session.current_title = ""
                    result["clicked"] = {"x": cx, "y": cy}
                    result["target"] = target
                    result["verified"] = verification["verified"]
                    result["retries"] = retries
                    result["url"] = session.current_url
                    result["title"] = session.current_title
                else:
                    result["ok"] = False
                    result["error"] = f"Could not find '{target}' on the page. Try a different description or use click_element(selector)."
            except Exception as exc:
                return json.dumps({"error": f"click_target failed: {exc}"})

        elif action == "click_som":
            if not target:
                return json.dumps({"error": "target is required for click_som"})
            if not chat_model:
                return json.dumps({"error": "click_som requires a chat model"})

            b64 = await session.get_screenshot_base64()
            if not b64:
                return json.dumps({"error": "Screenshot capture failed"})

            nodes = await session.get_axtree_nodes()
            if not nodes:
                return json.dumps({"error": "No interactive elements found on page. Try click_target instead."})

            annotated_b64, visible_nodes = annotate_som(b64, nodes)
            _save_screenshot(annotated_b64, f"click_som_{target[:40]}")

            if not visible_nodes:
                return json.dumps({"error": "No visible interactive elements to annotate"})

            from app.tools.screenops.prompts import SYSTEM_PROMPT_SOM_PICKER
            from langchain_core.messages import HumanMessage, SystemMessage

            try:
                resp = await chat_model.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT_SOM_PICKER),
                    HumanMessage(content=[
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{annotated_b64}"}},
                        {"type": "text", "text": f"Which numbered element matches: '{target}'? Reply with only the number."},
                    ]),
                ])
                resp_text = resp.content if hasattr(resp, "content") else str(resp)
            except Exception as exc:
                return json.dumps({"error": f"click_som vision call failed: {exc}"})

            import re as _re
            m = _re.search(r'\b(\d+)\b', resp_text)
            if not m:
                return json.dumps({"error": f"click_som: model did not return a number. Response: {resp_text[:100]}"})

            chosen_idx = int(m.group(1))
            if chosen_idx < 1 or chosen_idx > len(visible_nodes):
                return json.dumps({"error": f"click_som: model returned out-of-range index {chosen_idx} (max {len(visible_nodes)})"})

            chosen = visible_nodes[chosen_idx - 1]
            cx, cy = int(chosen.cx), int(chosen.cy)

            pre_url = page.url
            pre_h = await snapshot_hash(page)
            await page.mouse.click(cx, cy)
            await _notify_click_indicator(session, cx, cy)

            verification = await _verify_click_effect(page, pre_url, pre_h)

            try:
                session.current_url = page.url
                session.current_title = await page.title()
            except Exception:
                session.current_url = page.url or ""
                session.current_title = ""

            result["clicked"] = {"x": cx, "y": cy}
            result["target"] = target
            result["chosen_element"] = {"index": chosen_idx, "role": chosen.role, "name": chosen.name}
            result["verified"] = verification["verified"]
            result["url"] = session.current_url
            result["title"] = session.current_title

        # ── Find coordinates by vision (no click) ─────────────────
        elif action == "find_coordinates":
            if not target:
                return json.dumps({"error": "target is required for find_coordinates. Describe the element, e.g. target='the search input field'"})
            if not coordinate_finder:
                return json.dumps({"error": "find_coordinates requires a coordinate finder model. Configure ScreenOps API in Settings."})

            b64 = await session.get_screenshot_base64()
            if not b64:
                return json.dumps({"error": "Screenshot capture failed"})
            _save_screenshot(b64, f"find_coords_{target[:40]}")

            try:
                from app.services.browser_manager import SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT
                coords, coord_usage = coordinate_finder(
                    screenshot_base64=b64,
                    target_description=target,
                    screen_width=SCREENSHOT_WIDTH,
                    screen_height=SCREENSHOT_HEIGHT,
                    image_width=SCREENSHOT_WIDTH,
                    image_height=SCREENSHOT_HEIGHT,
                )
                if coords and coords.get("x") is not None and coords.get("y") is not None:
                    result["coordinates"] = {"x": int(coords["x"]), "y": int(coords["y"])}
                    result["target"] = target
                else:
                    result["ok"] = False
                    result["error"] = f"Could not find '{target}' on the page."
            except Exception as exc:
                return json.dumps({"error": f"find_coordinates failed: {exc}"})

        # ── Type text into focused element ─────────────────────────
        elif action == "type":
            if not text:
                return json.dumps({"error": "text is required for type"})
            type_result = await session.type_text(text)
            if "error" in type_result:
                return json.dumps({"error": type_result["error"]})
            result["typed"] = len(text)

        # ── Fill a form field by selector ──────────────────────────
        elif action == "fill":
            if not selector or text is None:
                return json.dumps({"error": "selector and text are required for fill"})
            try:
                await page.fill(selector, text, timeout=5000)
                result["filled"] = selector
                result["value"] = text
            except Exception as exc:
                return json.dumps({"error": f"fill failed: {exc}"})

        # ── Read page text ─────────────────────────────────────────
        elif action == "read_page":
            try:
                if selector:
                    content = await page.locator(selector).first.inner_text(timeout=5000)
                else:
                    content = await page.inner_text("body", timeout=5000)
                if len(content) > MAX_TEXT_LENGTH:
                    content = content[:MAX_TEXT_LENGTH] + f"\n... (truncated, {len(content)} total chars)"
                result["text"] = content
                result["url"] = session.current_url
                result["title"] = session.current_title
            except Exception as exc:
                return json.dumps({"error": f"read_page failed: {exc}"})

        elif action == "read_page_enhanced":
            try:
                text = await page.inner_text("body")
                if len(text) > MAX_TEXT_LENGTH:
                    text = text[:MAX_TEXT_LENGTH] + "\n... (truncated)"
            except Exception:
                text = ""
            nodes = await session.get_axtree_nodes()
            overlays = get_overlay_roles(nodes)
            iframe_count = max(0, len(page.frames) - 1)
            interactive = [
                {"index": n.index, "role": n.role, "name": n.name,
                 "x": int(n.cx), "y": int(n.cy)}
                for n in nodes if n.is_visible
            ]
            result["text"] = text
            result["interactive_elements"] = interactive
            result["overlays_detected"] = overlays
            result["iframes_count"] = iframe_count
            result["url"] = page.url
            result["title"] = await page.title()

        # ── Scroll ─────────────────────────────────────────────────
        elif action == "scroll":
            scroll_result = await session.scroll(direction, amount)
            if "error" in scroll_result:
                return json.dumps({"error": scroll_result["error"]})
            result["scrolled"] = direction

        # ── Press key ──────────────────────────────────────────────
        elif action == "press_key":
            if not key:
                return json.dumps({"error": "key is required for press_key"})
            key_result = await session.press_key(key)
            if "error" in key_result:
                return json.dumps({"error": key_result["error"]})
            result["pressed"] = key

        # ── Hover ──────────────────────────────────────────────────
        elif action == "hover":
            try:
                if selector:
                    await page.hover(selector, timeout=5000)
                else:
                    await page.mouse.move(x, y)
                await asyncio.sleep(0.3)
                result["hovered"] = selector or f"({x}, {y})"
            except Exception as exc:
                return json.dumps({"error": f"hover failed: {exc}"})

        # ── Select option ──────────────────────────────────────────
        elif action == "select_option":
            if not selector or not text:
                return json.dumps({"error": "selector and text (value) required for select_option"})
            try:
                await page.select_option(selector, text, timeout=5000)
                result["selected"] = text
            except Exception as exc:
                return json.dumps({"error": f"select_option failed: {exc}"})

        # ── Wait ───────────────────────────────────────────────────
        elif action == "wait":
            wait_time = min(max(seconds, 0.1), 10.0)
            await asyncio.sleep(wait_time)
            result["waited"] = wait_time

        # ── Evaluate JavaScript ────────────────────────────────────
        elif action == "evaluate_js":
            if not js_expression:
                return json.dumps({"error": "js_expression is required for evaluate_js"})
            try:
                js_result = await page.evaluate(js_expression)
                result["js_result"] = str(js_result)[:MAX_TEXT_LENGTH] if js_result is not None else None
            except Exception as exc:
                return json.dumps({"error": f"evaluate_js failed: {exc}"})

        # ── Back / Forward / Refresh ───────────────────────────────
        elif action == "back":
            r = await session.go_back()
            result.update(r)
        elif action == "forward":
            r = await session.go_forward()
            result.update(r)
        elif action == "refresh":
            r = await session.refresh()
            result.update(r)

        # ── Get current URL and title ──────────────────────────────
        elif action == "get_url":
            result["url"] = session.current_url
            result["title"] = session.current_title

        # ── Analyze page content extraction options ─────────────────
        elif action == "analyze_page":
            """Analyze page and return token costs for different extraction approaches."""
            try:
                # Get full page text and height
                text_content = await page.inner_text("body", timeout=5000)
                page_height = await page.evaluate("document.body.scrollHeight")

                # Analyze extraction options
                options = analyze_extraction_options(text_content, page_height)

                # Return analysis as JSON for LLM to review and decide
                result["action"] = "page_analysis"
                result["url"] = session.current_url
                result["page_height_px"] = page_height
                result["text_chars"] = len(text_content)
                result["extraction_options"] = [
                    {
                        "approach": opt.approach,
                        "total_tokens": opt.total_tokens,
                        "num_screenshots": opt.num_screenshots,
                        "description": opt.description,
                    }
                    for opt in options
                ]
                # Guide the LLM on what to do next based on its choice
                result["next_steps"] = (
                    "Review the extraction options above and decide:\n"
                    "• If you choose READ_PAGE: call auto_browser(action='read_page') to get all text.\n"
                    "• If you choose SCREENSHOT path: call auto_browser(action='screenshot_full_page') — "
                    "this captures all page tiles and sends them to you in one go. You will see the "
                    "entire page and can identify specific sections. Then use "
                    "auto_browser(action='read_page', selector='<css-selector>') to extract just "
                    "the text/links from the section you identified."
                )
            except Exception as exc:
                return json.dumps({"error": f"analyze_page failed: {exc}"})

        else:
            return json.dumps({"error": f"Unknown action: {action}. Valid actions: navigate, analyze_page, screenshot, screenshot_full_page, click, click_element, click_target, click_som, find_coordinates, type, fill, read_page, read_page_enhanced, scroll, press_key, hover, select_option, wait, evaluate_js, back, forward, refresh, get_url"})

        # Force an immediate screenshot push to the workspace so the user
        # sees the result of every tool action in real-time, without waiting
        # for the next screenshot loop tick (up to 0.33s delay).
        await _push_screenshot_to_ws(session)

        _elapsed = _time.monotonic() - _t0
        logger.info("auto_browser_done", action=action, elapsed_s=round(_elapsed, 2))
        return json.dumps(result)

    except Exception as exc:
        _elapsed = _time.monotonic() - _t0
        logger.error("auto_browser_error", action=action, elapsed_s=round(_elapsed, 2), error=str(exc), tb=traceback.format_exc())
        return json.dumps({"error": str(exc)})


def build_auto_browser_tool(
    chat_model: Any = None,
    coordinate_finder: Optional[Any] = None,
    conversation_id: Optional[str] = None,
    output_callback: Optional[Any] = None,
) -> Optional[StructuredTool]:
    """Build the AutoBrowser StructuredTool.

    Args:
        chat_model: LangChain ChatModel for vision description calls.
        coordinate_finder: ScreenOps coordinate finder invoker (screenshot → x,y coords).
        conversation_id: Conversation ID for browser session.
        output_callback: Callback for real-time output.

    Returns None if Playwright is not installed.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        logger.warning("playwright_not_installed_auto_browser_disabled")
        return None

    async def _tool_fn(
        action: str,
        url: str = "",
        selector: str = "",
        text: str = "",
        x: int = 0,
        y: int = 0,
        key: str = "",
        direction: str = "down",
        amount: int = 300,
        js_expression: str = "",
        seconds: float = 1.0,
        describe_screenshot: bool = False,
        target: str = "",
    ) -> str:
        result = await _auto_browser(
            action=action,
            url=url,
            selector=selector,
            text=text,
            x=x,
            y=y,
            key=key,
            direction=direction,
            amount=amount,
            js_expression=js_expression,
            seconds=seconds,
            describe_screenshot=describe_screenshot,
            target=target,
            chat_model=chat_model,
            coordinate_finder=coordinate_finder,
            conversation_id=conversation_id,
            output_callback=output_callback,
        )
        # In CodeAct mode, exec() only captures stdout — not return values.
        # Print the result so it appears in the captured output.
        print(result)
        return result

    return StructuredTool.from_function(
        coroutine=_tool_fn,
        name="auto_browser",
        description=(
            "Control a real Chromium browser visible in the user's Workspace panel. "
            "Every action you take is streamed live so the user sees it happen.\n\n"
            "ACTIONS (prefer screenshot over screenshot_full_page — it's much faster):\n"
            "  navigate(url)            — Go to a URL\n"
            "  analyze_page             — Compare token costs: read_page vs screenshot vs multi-tile\n"
            "  screenshot(describe_screenshot=True) — Capture viewport + AI-describe (FAST: ~10s)\n"
            "  screenshot_full_page     — Capture ALL page tiles in ONE vision call (SLOW: 30-60s, use only when you need to see the ENTIRE page)\n"
            "  click(x, y)              — Click at exact pixel coordinates\n"
            "  click_element(selector)  — Click a CSS-selector element (FAST, preferred when selector is known)\n"
            "  click_target(target)     — Click an element by visual description using AI vision (e.g. target='the blue Sign In button')\n"
            "  click_som(target)        — Click using Set-of-Marks: annotates page with numbered boxes, vision model picks the number. More reliable than click_target on dense/JS-heavy pages.\n"
            "  find_coordinates(target) — Find x,y coordinates of an element by visual description (no click)\n"
            "  type(text)               — Type text into the focused element\n"
            "  fill(selector, text)     — Fill a form input by CSS selector\n"
            "  read_page(selector?)     — Extract text from the full page or a specific CSS selector\n"
            "  read_page_enhanced()     — Like read_page but also returns interactive elements list (role, name, position) + overlay detection. Prefer this over read_page for interactive tasks.\n"
            "  scroll(direction, amount) — Scroll up/down by pixel amount\n"
            "  press_key(key)           — Press a key: Enter, Tab, Escape, Backspace, etc.\n"
            "  hover(selector or x,y)   — Hover over an element or coordinates\n"
            "  select_option(selector, text) — Select a dropdown option\n"
            "  wait(seconds)            — Wait up to 10 seconds\n"
            "  evaluate_js(js_expression) — Run JavaScript in the page\n"
            "  back / forward / refresh — Browser navigation\n"
            "  get_url                  — Get current URL and page title\n\n"
            "CLICKING STRATEGY (choose the best approach):\n"
            "  1. click_element(selector) — FASTEST. Use when you know the CSS selector.\n"
            "  2. click_target(target)    — Uses AI vision to find & click. Use when you can describe\n"
            "     the element visually but don't know the selector. e.g. target='the Login button'\n"
            "  3. click_som(target)      — annotates screenshot, reliable on overlays and JS-heavy UIs\n"
            "  4. click(x, y)            — Use when you already have exact coordinates.\n\n"
            "SMART CONTENT EXTRACTION WORKFLOW:\n"
            "  1. navigate(url) → land on the page\n"
            "  2. analyze_page  → see token costs for read_page vs screenshot\n"
            "  3. YOU DECIDE based on costs:\n"
            "     PATH A (read_page cheaper): read_page() → get all text directly\n"
            "     PATH B (screenshot cheaper): screenshot_full_page → see entire page visually,\n"
            "       identify the section you need, then read_page(selector='#that-section') → \n"
            "       extract ONLY the targeted text/links from that section\n"
        ),
    )
