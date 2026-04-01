"""
WebSocket endpoint for Brain browser live view.

Allows the Brain detail page to connect and watch the brain's browser
session in real-time. Users can also interact with the browser.

Route: /ws/brain-browser/{brain_id}
"""

import asyncio

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.brain_browser_manager import brain_browser_manager

logger = structlog.get_logger()
router = APIRouter()


@router.websocket("/ws/brain-browser/{brain_id}")
async def brain_browser_websocket(websocket: WebSocket, brain_id: str):
    """Live browser view for a brain's automation tasks."""
    await websocket.accept()

    # Get or create a browser session for this brain
    session = brain_browser_manager.get_session(brain_id)

    if not session:
        # Auto-launch a browser so the user can browse immediately
        await websocket.send_json({
            "type": "brain_status",
            "message": "launching_browser",
            "brain_id": brain_id,
        })
        try:
            session = await brain_browser_manager.get_or_create(
                brain_id=brain_id,
                task_id=None,
            )
        except Exception as exc:
            await websocket.send_json({
                "type": "brain_status",
                "message": f"browser_launch_failed: {exc}",
                "brain_id": brain_id,
            })
            # Fall back to polling for a session
            try:
                while True:
                    await asyncio.sleep(3)
                    session = brain_browser_manager.get_session(brain_id)
                    if session:
                        break
                    try:
                        raw = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
                        if raw.get("type") == "ping":
                            await websocket.send_json({"type": "pong"})
                    except asyncio.TimeoutError:
                        continue
                    except WebSocketDisconnect:
                        return
            except WebSocketDisconnect:
                return
            except Exception:
                return

    # Register and send initial state
    session.websocket_clients.add(websocket)
    await websocket.send_json({
        "type": "brain_status",
        "message": "connected",
        "brain_id": brain_id,
        "task_id": session.task_id,
        "url": session.current_url,
    })
    screenshot = await session.get_screenshot_base64()
    if screenshot:
        await websocket.send_json({
            "type": "brain_screenshot",
            "data": screenshot,
            "url": session.current_url,
            "title": session.current_title,
            "brain_id": brain_id,
        })

    # Now handle interactive messages from the user
    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "")

            # Refresh session reference in case it was recreated
            session = brain_browser_manager.get_session(brain_id)
            if not session or not session.page:
                await websocket.send_json({"type": "brain_status", "message": "no_active_session"})
                continue

            result = {}
            if msg_type == "click":
                x, y = raw.get("x", 0), raw.get("y", 0)
                try:
                    await session.page.mouse.click(int(x), int(y))
                    await asyncio.sleep(0.3)
                    session.current_url = session.page.url
                    session.current_title = await session.page.title()
                    result = {"url": session.current_url}
                except Exception as e:
                    result = {"error": str(e)}

            elif msg_type == "navigate":
                url = raw.get("url", "")
                if url:
                    result = await session.navigate(url)

            elif msg_type == "scroll":
                direction = raw.get("direction", "down")
                amount = raw.get("amount", 300)
                delta = amount if direction == "down" else -amount
                try:
                    await session.page.mouse.wheel(0, delta)
                    result = {"scrolled": direction}
                except Exception as e:
                    result = {"error": str(e)}

            elif msg_type == "type":
                text = raw.get("text", "")
                try:
                    await session.page.keyboard.type(text)
                    result = {"typed": len(text)}
                except Exception as e:
                    result = {"error": str(e)}

            elif msg_type == "key":
                key = raw.get("key", "")
                try:
                    await session.page.keyboard.press(key)
                    result = {"pressed": key}
                except Exception as e:
                    result = {"error": str(e)}

            elif msg_type == "resume":
                # User signals they've resolved a captcha/login/blockage
                if session.needs_human:
                    session.resolve_human_help()
                    await websocket.send_json({
                        "type": "brain_status",
                        "message": "Resuming — thank you!",
                        "brain_id": brain_id,
                    })
                else:
                    await websocket.send_json({
                        "type": "brain_status",
                        "message": "No pending intervention",
                        "brain_id": brain_id,
                    })
                continue

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            await websocket.send_json({"type": "action_result", "result": result})

    except WebSocketDisconnect:
        logger.info("brain_browser_ws_disconnected", brain_id=brain_id)
    except Exception as e:
        logger.error("brain_browser_ws_error", error=str(e))
    finally:
        if session:
            session.websocket_clients.discard(websocket)
