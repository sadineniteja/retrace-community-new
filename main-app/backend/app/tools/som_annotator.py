"""
Set-of-Marks (SoM) annotator for browser automation.

Overlays numbered bounding boxes on a screenshot for all interactive
elements, enabling vision models to select elements by number rather
than describing coordinates.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.axtree import AXNode

logger = logging.getLogger("auto_browser.som")

# Visual style
_BOX_FILL = (255, 140, 0, 70)    # semi-transparent orange fill
_BOX_BORDER = (255, 60, 0, 255)  # solid red-orange border
_LABEL_BG = (255, 60, 0, 230)    # label background
_LABEL_FG = (255, 255, 255, 255) # label text


def annotate_som(
    screenshot_base64: str,
    nodes: list["AXNode"],
    max_longest_side: int = 1280,
) -> tuple[str, list["AXNode"]]:
    """Draw numbered bounding boxes on a screenshot.

    Args:
        screenshot_base64: Base64-encoded PNG or JPEG screenshot.
        nodes: List of AXNode objects with pixel coordinates.
        max_longest_side: Resize image if needed (avoids token explosion).

    Returns:
        (annotated_base64_png, visible_nodes) where visible_nodes are only
        those actually drawn (have valid coords and are on-screen).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("som_annotator: Pillow not installed")
        return screenshot_base64, []

    # Decode image
    raw = base64.b64decode(screenshot_base64)
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    W, H = img.size

    # Resize if needed
    longest = max(W, H)
    scale = 1.0
    if longest > max_longest_side:
        scale = max_longest_side / longest
        new_w, new_h = int(W * scale), int(H * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        W, H = new_w, new_h

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    visible_nodes: list["AXNode"] = []

    for node in nodes:
        if not node.has_coords or node.width < 3 or node.height < 3:
            continue

        # Scale coords to (possibly resized) image
        x1 = int(node.x * scale)
        y1 = int(node.y * scale)
        x2 = int((node.x + node.width) * scale)
        y2 = int((node.y + node.height) * scale)

        # Skip off-screen elements
        if x2 < 0 or y2 < 0 or x1 > W or y1 > H:
            continue

        # Clamp to image bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(W, x2), min(H, y2)
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue

        # Draw semi-transparent fill
        draw.rectangle([x1, y1, x2, y2], fill=_BOX_FILL)
        # Draw border
        draw.rectangle([x1, y1, x2, y2], outline=_BOX_BORDER, width=2)

        # Draw number label
        label = str(node.index)
        lx, ly = x1 + 2, y1 + 2
        lw, lh = (len(label) * 7 + 4), 14
        draw.rectangle([lx, ly, lx + lw, ly + lh], fill=_LABEL_BG)
        if font:
            draw.text((lx + 2, ly + 1), label, fill=_LABEL_FG, font=font)
        else:
            draw.text((lx + 2, ly + 1), label, fill=_LABEL_FG)

        visible_nodes.append(node)

    # Composite overlay onto original
    result = Image.alpha_composite(img, overlay).convert("RGB")

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    annotated_b64 = base64.b64encode(buf.getvalue()).decode()

    logger.debug("som_annotator: drew %d boxes on %dx%d image", len(visible_nodes), W, H)
    return annotated_b64, visible_nodes
