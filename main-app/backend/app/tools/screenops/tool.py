"""
ScreenOps tool builder for the ReTrace agent.

Ported from IQWorksAtlas screenops/tool.py.  Creates the vision invoker
(using ReTrace's configured chat model via LangChain) and a configurable
coordinate finder invoker (URL + model + API key, OpenAI-compatible API).
"""

import base64
import io
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from langchain_core.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.tools.screenops.workflow import run_screen_workflow
from app.tools.screenops.prompts import (
    get_coordinate_finder_prompt,
    get_coordinate_finder_prompt_qwen25vl,
    COORDINATE_FINDER_CACHE_PADDING,
    VISION_CACHE_PADDING,
)

logger = logging.getLogger("screenops.tool")

_DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "screenops_debug.log"


def _debug_log(tag: str, **kwargs):
    """Append a timestamped line to screenops_debug.log for post-mortem analysis."""
    try:
        ts = datetime.utcnow().isoformat()
        parts = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        line = f"[{ts}] [{tag}] {parts}\n"
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Vision invoker — uses the ReTrace chat LangChain model
# ---------------------------------------------------------------------------

def _make_vision_invoker(model: Any):
    """Build model_invoker(messages, system_prompt) → (content_str, usage_dict)."""

    def invoker(messages, system_prompt, **kwargs):
        lc_messages = [SystemMessage(content=system_prompt)]
        for m in messages:
            role = m.get("role", "user") if isinstance(m, dict) else getattr(m, "type", "human")
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", m)

            if role == "assistant" or (hasattr(m, "type") and getattr(m, "type", None) == "ai"):
                lc_messages.append(AIMessage(content=content if isinstance(content, str) else str(content)))
                continue

            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            parts.append({"type": "text", "text": part.get("text", "")})
                        elif part.get("type") == "image_url":
                            url = part.get("image_url", {})
                            if isinstance(url, str):
                                url = {"url": url}
                            parts.append({"type": "image_url", "image_url": url})
                    elif isinstance(part, str):
                        parts.append({"type": "text", "text": part})
                    else:
                        parts.append(part)
                lc_messages.append(HumanMessage(content=parts))
            else:
                lc_messages.append(HumanMessage(content=content))

        resp = model.invoke(lc_messages, **kwargs)
        text = resp.content if hasattr(resp, "content") else str(resp)

        usage = {}
        if hasattr(resp, "usage_metadata") and resp.usage_metadata:
            u = resp.usage_metadata
            if isinstance(u, dict):
                usage = {
                    "prompt_tokens": u.get("input_tokens") or u.get("prompt_tokens", 0),
                    "completion_tokens": u.get("output_tokens") or u.get("completion_tokens", 0),
                    "total_tokens": u.get("total_tokens", 0),
                }
            else:
                usage = {
                    "prompt_tokens": getattr(u, "input_tokens", None) or getattr(u, "prompt_tokens", 0),
                    "completion_tokens": getattr(u, "output_tokens", None) or getattr(u, "completion_tokens", 0),
                    "total_tokens": getattr(u, "total_tokens", 0),
                }
        return text, usage

    return invoker


# ---------------------------------------------------------------------------
# Provider detection helpers
# ---------------------------------------------------------------------------

def _get_model_base_url(model: Any) -> str:
    return str(
        getattr(model, "openai_api_base", None)
        or getattr(model, "base_url", "")
        or ""
    )


def _get_model_name(model: Any) -> str:
    return str(
        getattr(model, "model_name", None)
        or getattr(model, "model", "")
        or ""
    )


def _get_model_api_key(model: Any) -> str:
    api_key_raw = (
        getattr(model, "openai_api_key", None)
        or getattr(model, "api_key", None)
    )
    if hasattr(api_key_raw, "get_secret_value"):
        return api_key_raw.get_secret_value()
    return str(api_key_raw or "")


# ---------------------------------------------------------------------------
# x.ai / Grok vision invoker — uses the Responses API (/v1/responses)
# ---------------------------------------------------------------------------

def _is_xai_model(model: Any) -> bool:
    """Return True when *model* targets the x.ai API."""
    return "x.ai" in _get_model_base_url(model)


# ---------------------------------------------------------------------------
# Google Gemini vision invoker — uses Chat Completions via OpenAI SDK
# ---------------------------------------------------------------------------

def _is_google_model(model: Any) -> bool:
    """Return True when *model* targets the Google Gemini API."""
    base_url = _get_model_base_url(model)
    model_name = _get_model_name(model)
    return (
        "generativelanguage.googleapis.com" in base_url
        or "aiplatform.googleapis.com" in base_url
        or model_name.startswith("gemini")
    )


def _make_google_vision_invoker(model: Any):
    """Build a vision invoker for Google Gemini via its OpenAI-compatible endpoint.

    Gemini's ``/v1beta/openai/`` compatibility layer requires every element
    in a multimodal content array to be a typed struct (``{"type": "text", …}``
    or ``{"type": "image_url", …}``).  Bare strings are rejected with
    ``INVALID_ARGUMENT: Value is not a struct``.

    This invoker bypasses LangChain and calls the endpoint directly through
    the OpenAI SDK so we have full control over the wire format.
    """
    import httpx
    from openai import OpenAI

    api_key = _get_model_api_key(model)
    base_url = _get_model_base_url(model) or "https://generativelanguage.googleapis.com/v1beta/openai/"
    model_name = _get_model_name(model)

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(120.0),
    )

    def invoker(messages, system_prompt, **kwargs):
        api_messages: list[dict] = [{"role": "system", "content": system_prompt}]

        for m in messages:
            role = m.get("role", "user") if isinstance(m, dict) else "user"
            content = m.get("content") if isinstance(m, dict) else m

            if role == "assistant":
                api_messages.append({
                    "role": "assistant",
                    "content": content if isinstance(content, str) else str(content),
                })
                continue

            if isinstance(content, list):
                parts: list[dict] = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            parts.append({"type": "text", "text": part.get("text", "")})
                        elif part.get("type") == "image_url":
                            url = part.get("image_url", {})
                            if isinstance(url, str):
                                url = {"url": url}
                            parts.append({"type": "image_url", "image_url": url})
                        else:
                            parts.append(part)
                    elif isinstance(part, str):
                        parts.append({"type": "text", "text": part})
                api_messages.append({"role": "user", "content": parts})
            else:
                api_messages.append({
                    "role": "user",
                    "content": content if isinstance(content, str) else str(content),
                })

        response = client.chat.completions.create(
            model=model_name,
            messages=api_messages,
        )

        text = ""
        if response.choices:
            text = response.choices[0].message.content or ""

        usage: dict = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return text, usage

    return invoker


def _make_xai_vision_invoker(model: Any):
    """Build a vision invoker for x.ai models.

    x.ai's grok-4 models require the **Responses API** (``/v1/responses``)
    with ``input_image`` / ``input_text`` content-block types rather than
    the Chat Completions API with ``image_url`` / ``text``.
    """
    import httpx
    from openai import OpenAI

    api_key = _get_model_api_key(model)
    base_url = _get_model_base_url(model) or "https://api.x.ai/v1"
    model_name = _get_model_name(model)

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(300.0),
    )

    def invoker(messages, system_prompt, **kwargs):
        input_messages: list[dict] = []
        for m in messages:
            role = m.get("role", "user") if isinstance(m, dict) else "user"
            content = m.get("content") if isinstance(m, dict) else m

            if role == "assistant":
                input_messages.append({
                    "role": "assistant",
                    "content": content if isinstance(content, str) else str(content),
                })
                continue

            if isinstance(content, list):
                parts: list[dict] = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            parts.append({
                                "type": "input_text",
                                "text": part.get("text", ""),
                            })
                        elif part.get("type") == "image_url":
                            url = part.get("image_url", {})
                            if isinstance(url, dict):
                                url = url.get("url", "")
                            parts.append({
                                "type": "input_image",
                                "image_url": url,
                                "detail": "high",
                            })
                    elif isinstance(part, str):
                        parts.append({"type": "input_text", "text": part})
                input_messages.append({"role": "user", "content": parts})
            else:
                input_messages.append({
                    "role": "user",
                    "content": content if isinstance(content, str) else str(content),
                })

        response = client.responses.create(
            model=model_name,
            instructions=system_prompt,
            input=input_messages,
        )

        text = getattr(response, "output_text", "") or ""

        usage: dict = {}
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            inp = getattr(u, "input_tokens", 0) or 0
            out = getattr(u, "output_tokens", 0) or 0
            usage = {
                "prompt_tokens": inp,
                "completion_tokens": out,
                "total_tokens": inp + out,
            }

        return text, usage

    return invoker


# ---------------------------------------------------------------------------
# Coordinate finder invoker — OpenAI-compatible API (URL + model + API key)
# ---------------------------------------------------------------------------

_DEFAULT_COORD_API_URL = "https://api.openai.com/v1"
_MAX_IMAGE_LONGEST_SIDE = 1280


def _resize_screenshot_for_coord_finder(screenshot_base64: str) -> tuple[str, int, int]:
    """Resize a screenshot so the longest side is <= _MAX_IMAGE_LONGEST_SIDE.

    Ensures the model sees exactly the dimensions we state in the prompt
    for accurate pixel coordinates.

    Returns (resized_b64, resized_w, resized_h).
    """
    from PIL import Image as PILImage

    raw = base64.b64decode(screenshot_base64)
    img = PILImage.open(io.BytesIO(raw))
    w, h = img.size

    longest = max(w, h)
    if longest <= _MAX_IMAGE_LONGEST_SIDE:
        return screenshot_base64, w, h

    scale = _MAX_IMAGE_LONGEST_SIDE / longest
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    img = img.resize((new_w, new_h), PILImage.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    resized_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return resized_b64, new_w, new_h


def _make_coordinate_finder_invoker(
    api_url: str,
    model: str,
    api_key: str,
    fallback_model: Optional[str] = None,
    extra_headers: Optional[dict[str, str]] = None,
) -> Callable[..., Tuple[dict, dict]]:
    """Build coordinate_finder_invoker using an OpenAI-compatible API (URL + model + key).

    When *fallback_model* differs from *model*, retries once on HTTP/API failure or when
    no coordinates are parsed from the response.
    """
    base_url = (api_url or _DEFAULT_COORD_API_URL).strip().rstrip("/")
    if not base_url.startswith("http"):
        base_url = "https://" + base_url
    primary = (model or "").strip() or "gpt-4o-mini"
    fb = (fallback_model or "").strip()
    models_try = [primary]
    if fb and fb != primary:
        models_try.append(fb)
    endpoint = f"{base_url}/chat/completions"

    # Detect UI-TARS by querying the actual running model from /v1/models.
    # Settings may have a stale model name; the server always knows what's loaded.
    # UI-TARS outputs 0–1000 normalized coordinates regardless of image size.
    _uitars_models: set[str] = {m for m in [primary, fb] if "ui-tars" in m.lower()}
    try:
        import urllib.request as _ur
        _mreq = _ur.Request(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with _ur.urlopen(_mreq, timeout=5) as _r:
            _mdata = json.loads(_r.read())
        for _entry in (_mdata.get("data") or []):
            _mid = str(_entry.get("id", ""))
            if "ui-tars" in _mid.lower():
                _uitars_models.add(primary)  # primary is what we send in the payload
                logger.info("coord_finder: detected UI-TARS running at %s (%s)", base_url, _mid)
                break
    except Exception as _e:
        logger.debug("coord_finder: could not query /v1/models: %s", _e)

    def invoker(screenshot_base64, target_description, screen_width, screen_height, image_width, image_height, **kwargs):
        import httpx

        resized_b64, resized_w, resized_h = _resize_screenshot_for_coord_finder(screenshot_base64)

        _debug_log("coord_finder",
                   target=target_description,
                   event="resize",
                   original_image=f"{image_width}x{image_height}",
                   resized_image=f"{resized_w}x{resized_h}",
                   screen=f"{screen_width}x{screen_height}")

        # Use Qwen2.5-VL recommended format: concise system prompt + "Click on X."
        # This format outperforms verbose JSON-instruction prompts on GUI grounding benchmarks.
        system_text = get_coordinate_finder_prompt_qwen25vl(
            screen_width=resized_w,
            screen_height=resized_h,
        )
        user_text = f"Click on the {target_description}."

        for attempt_idx, coord_model in enumerate(models_try):
            payload = {
                "model": coord_model,
                "messages": [
                    {"role": "system", "content": system_text},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{resized_b64}"},
                            },
                            {"type": "text", "text": user_text},
                        ],
                    },
                ],
                "max_tokens": 50,
                "temperature": 0.1,
                # Disable thinking for local models (sglang/Qwen) — coordinate
                # finder needs clean output, not reasoning chains.
                "chat_template_kwargs": {"enable_thinking": False},
            }

            try:
                hdrs: dict[str, str] = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                if extra_headers:
                    for k, v in extra_headers.items():
                        lk = k.lower()
                        if lk not in ("authorization", "content-type"):
                            hdrs[k] = v
                with httpx.Client(timeout=60.0) as client:
                    r = client.post(endpoint, headers=hdrs, json=payload)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                logger.warning(
                    "coord_finder_request_failed endpoint=%s model=%s attempt=%d error=%s",
                    endpoint, coord_model, attempt_idx + 1, str(e),
                )
                continue

            text = ""
            usage: dict = {}
            choice = (data.get("choices") or [None])[0]
            if choice and isinstance(choice.get("message"), dict):
                text = (choice["message"].get("content") or "").strip()
            if data.get("usage"):
                u = data["usage"]
                usage = {
                    "prompt_tokens": u.get("input_tokens", u.get("prompt_tokens", 0)),
                    "completion_tokens": u.get("output_tokens", u.get("completion_tokens", 0)),
                    "total_tokens": u.get("total_tokens", 0),
                }
                usage["total_tokens"] = usage["total_tokens"] or usage["prompt_tokens"] + usage["completion_tokens"]

            coords: dict = {}
            clean_text = text.strip()
            if clean_text.startswith("```"):
                clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                clean_text = re.sub(r"\s*```\s*$", "", clean_text)
                clean_text = clean_text.strip()

            # --- Bounding box: (x1, y1, x2, y2) — Qwen2.5-VL often returns this.
            #     Use x1 (left edge) for X — models tend to overshoot right on bbox center,
            #     so x1 is consistently closer to the actual element position.
            #     Use center for Y since vertical alignment is accurate.
            if not coords:
                m = re.search(r'\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', clean_text)
                if m:
                    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                    coords = {"x": x1, "y": (y1 + y2) // 2}

            # --- Tuple (x, y)
            if not coords:
                m = re.search(r'\(\s*(\d+)\s*,\s*(\d+)\s*\)', clean_text)
                if m:
                    coords = {"x": int(m.group(1)), "y": int(m.group(2))}

            # --- JSON {"x": N, "y": N}
            if not coords:
                json_match = re.search(r'\{[^}]+\}', clean_text)
                if json_match:
                    try:
                        coords = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
            if not coords:
                m = re.search(r'\{\s*["\']x["\']\s*:\s*(\d+)\s*,\s*["\']y["\']\s*:\s*(\d+)\s*\}', text)
                if m:
                    coords = {"x": int(m.group(1)), "y": int(m.group(2))}
            if not coords:
                # Malformed: {"x": 607, 143} — model sometimes drops "y": key
                m = re.search(r'\{\s*["\']x["\']\s*:\s*(\d+)\s*,\s*(\d+)\s*\}', text)
                if m:
                    coords = {"x": int(m.group(1)), "y": int(m.group(2))}

            if not coords:
                # Last resort: extract all integers and detect 4-number bbox or 2-number point
                nums = re.findall(r'\b(\d{2,4})\b', text)
                if len(nums) >= 4:
                    x1, y1, x2, y2 = int(nums[0]), int(nums[1]), int(nums[2]), int(nums[3])
                    cx, cy = x1, (y1 + y2) // 2  # x1 for X (more accurate), center for Y
                    if 0 < cx <= screen_width and 0 < cy <= screen_height:
                        coords = {"x": cx, "y": cy}
                elif len(nums) >= 2:
                    x_val, y_val = int(nums[0]), int(nums[1])
                    if 0 < x_val <= screen_width and 0 < y_val <= screen_height:
                        coords = {"x": x_val, "y": y_val}

            _debug_log("coord_finder",
                       target=target_description,
                       model=coord_model,
                       raw_text=text,
                       resized_image=f"{resized_w}x{resized_h}",
                       screen=f"{screen_width}x{screen_height}",
                       raw_parsed=coords)

            if coords.get("x") is not None and coords.get("y") is not None:
                cx, cy = float(coords["x"]), float(coords["y"])
                if coord_model in _uitars_models or (cx > resized_w or cy > resized_h):
                    # UI-TARS always outputs 0–1000 normalized scale.
                    # Also catches other models that exceed image bounds.
                    px = int(round(cx / 1000.0 * screen_width))
                    py = int(round(cy / 1000.0 * screen_height))
                    _debug_log("coord_finder", target=target_description, norm1000_to_screen=(cx, cy, px, py))
                    coords = {"x": px, "y": py}
                elif 0.0 < cx <= 1.0 and 0.0 < cy <= 1.0:
                    # 0.0–1.0 normalized (e.g. older prompt formats)
                    px = int(round(cx * screen_width))
                    py = int(round(cy * screen_height))
                    _debug_log("coord_finder", target=target_description, normalized_to_screen=(cx, cy, px, py))
                    coords = {"x": px, "y": py}
                else:
                    scale_x = screen_width / resized_w
                    scale_y = screen_height / resized_h
                    px = int(round(cx * scale_x))
                    py = int(round(cy * scale_y))
                    _debug_log("coord_finder",
                               target=target_description,
                               resized_to_screen=(cx, cy, resized_w, resized_h, scale_x, scale_y, px, py))
                    coords = {"x": px, "y": py}
                coords["x"] = max(0, min(coords["x"], screen_width - 1))
                coords["y"] = max(0, min(coords["y"], screen_height - 1))

                _debug_log("coord_finder", target=target_description, final_screen_coords=coords, model_used=coord_model)
                return coords, usage

            logger.warning(
                "coord_finder_no_coordinates model=%s attempt=%d target=%s",
                coord_model, attempt_idx + 1, (target_description or "")[:80],
            )

        return {}, {}

    return invoker


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_screenops_tool(
    chat_model: Any,
    screenops_api_key: str = "",
    screenops_model: Optional[str] = None,
    screenops_api_url: Optional[str] = None,
    screenops_mouse_timeout: int = 30,
    screenops_image_scale: int = 100,
    screenops_coord_fallback_model: Optional[str] = None,
    screenops_coord_extra_headers: Optional[dict[str, str]] = None,
) -> Optional[StructuredTool]:
    """Build the ScreenOps StructuredTool.

    *chat_model* — LangChain ChatModel for the vision step (required).
    *screenops_api_key* — API key for the coordinate finder (empty = keyboard-only mode).
    *screenops_model* — Model name for the coordinate finder (primary).
    *screenops_coord_fallback_model* — If set and different, used when the primary model fails or returns no coords.
    *screenops_api_url* — Base URL for the coordinate finder API (OpenAI-compatible).
    *screenops_mouse_timeout* — Seconds to wait for manual click in keyboard-only mode.
    *screenops_image_scale* — 25-100, percentage of screenshot size sent to model (reduces tokens).
    """
    if not chat_model:
        return None

    if _is_xai_model(chat_model):
        model_invoker = _make_xai_vision_invoker(chat_model)
        logger.info("Using x.ai Responses API for ScreenOps vision")
    elif _is_google_model(chat_model):
        model_invoker = _make_google_vision_invoker(chat_model)
        logger.info("Using Google Gemini API for ScreenOps vision")
    else:
        model_invoker = _make_vision_invoker(chat_model)

    keyboard_only = not bool(screenops_api_key)
    coordinate_finder_invoker = None
    if not keyboard_only:
        api_url = (screenops_api_url or _DEFAULT_COORD_API_URL).strip()
        model_name = (screenops_model or "").strip() or "gpt-4o-mini"
        fb = (screenops_coord_fallback_model or "").strip()
        coordinate_finder_invoker = _make_coordinate_finder_invoker(
            api_url,
            model_name,
            screenops_api_key,
            fallback_model=fb or None,
            extra_headers=screenops_coord_extra_headers,
        )

    if keyboard_only:
        logger.info("ScreenOps: keyboard-only mode (no coordinate finder API configured)")

    mouse_timeout = max(5, min(120, screenops_mouse_timeout))
    image_scale = max(25, min(100, screenops_image_scale))

    def run_screenops(task: str) -> str:
        out = run_screen_workflow(
            task=task,
            model_invoker=model_invoker,
            coordinate_finder_invoker=coordinate_finder_invoker,
            keyboard_only=keyboard_only,
            mouse_timeout=mouse_timeout,
            max_steps=10,
            image_scale=image_scale,
        )
        return json.dumps({
            "result": out.get("result", ""),
            "iterations": out.get("iterations"),
        })

    desc = (
        "Perform screen-based computer operations: open apps, type text, "
        "use keyboard shortcuts. Pass the user's request verbatim as the "
        "task argument. Requires a visible desktop."
    )
    if keyboard_only:
        desc += (
            " Running in keyboard-only mode — prefer keyboard shortcuts "
            "(Tab, Enter, arrow keys, Cmd/Ctrl+...) over mouse clicks."
        )

    return StructuredTool.from_function(
        name="screenops",
        description=desc,
        func=run_screenops,
    )
