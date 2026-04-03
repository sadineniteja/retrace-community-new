"""
Accessibility Tree (AXTree) extraction for browser automation.

Extracts interactive elements from Playwright pages including overlays,
iframes, and dynamic elements that raw DOM scraping misses.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("auto_browser.axtree")

# Roles considered interactive (clickable/focusable)
INTERACTIVE_ROLES = {
    "button", "link", "textbox", "combobox", "checkbox", "radio",
    "menuitem", "tab", "searchbox", "spinbutton", "switch", "option",
    "treeitem", "gridcell", "columnheader", "rowheader", "slider",
}

# Roles that indicate an overlay/modal is present
OVERLAY_ROLES = {"dialog", "alertdialog", "tooltip", "menu", "listbox", "tree"}

_MAX_NODES = 150  # Cap to avoid huge annotated images


@dataclass
class AXNode:
    index: int          # 1-based, used for SoM labels
    role: str
    name: str
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    in_iframe: bool = False
    has_coords: bool = False

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2

    @property
    def is_visible(self) -> bool:
        return self.has_coords and self.width > 3 and self.height > 3


# ---------------------------------------------------------------------------
# JS helper — batch fetch bounding rects for interactive elements
# ---------------------------------------------------------------------------

_BATCH_RECT_JS = """
() => {
    const roles = new Set([
        'button','link','textbox','combobox','checkbox','radio',
        'menuitem','tab','searchbox','spinbutton','switch','option',
        'treeitem','gridcell','slider','a','input','select','textarea'
    ]);
    const results = [];
    const seen = new Set();

    function processElement(el, iframeOffsetX, iframeOffsetY) {
        const tag = (el.tagName || '').toLowerCase();
        const role = (el.getAttribute('role') || tag || '').toLowerCase();
        const ariaLabel = el.getAttribute('aria-label') || '';
        const ariaHidden = el.getAttribute('aria-hidden');
        if (ariaHidden === 'true') return;

        const isInteractive = (
            roles.has(role) ||
            roles.has(tag) ||
            el.onclick !== null ||
            el.getAttribute('tabindex') !== null ||
            el.getAttribute('href') !== null
        );
        if (!isInteractive) return;

        const text = (
            ariaLabel ||
            el.getAttribute('placeholder') ||
            el.getAttribute('value') ||
            el.getAttribute('title') ||
            (el.innerText || '').trim().slice(0, 80)
        );
        if (!text) return;

        const key = role + '|' + text.slice(0, 40);
        if (seen.has(key)) return;
        seen.add(key);

        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) return;
        if (rect.bottom < 0 || rect.right < 0) return;

        results.push({
            role: role,
            name: text,
            x: rect.left + iframeOffsetX,
            y: rect.top + iframeOffsetY,
            width: rect.width,
            height: rect.height,
        });
    }

    // Main frame
    document.querySelectorAll('*').forEach(el => processElement(el, 0, 0));

    // Iframes (same-origin only)
    document.querySelectorAll('iframe').forEach(iframe => {
        try {
            const iRect = iframe.getBoundingClientRect();
            const idoc = iframe.contentDocument || iframe.contentWindow.document;
            idoc.querySelectorAll('*').forEach(el =>
                processElement(el, iRect.left, iRect.top)
            );
        } catch(e) { /* cross-origin iframe — skip */ }
    });

    return results;
}
"""


async def extract_interactive_nodes(page: Any) -> list[AXNode]:
    """Extract interactive elements from a Playwright page with pixel coordinates.

    Returns a list of AXNode objects, each with screen-space bounding box.
    Includes elements in same-origin iframes. Capped at _MAX_NODES.
    """
    try:
        # Wait for network to settle (best-effort)
        try:
            await page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass

        raw: list[dict] = await page.evaluate(_BATCH_RECT_JS)
    except Exception as e:
        logger.warning("axtree: JS evaluation failed: %s", e)
        return []

    nodes: list[AXNode] = []
    for i, item in enumerate(raw[:_MAX_NODES], start=1):
        node = AXNode(
            index=i,
            role=item.get("role", ""),
            name=item.get("name", ""),
            x=float(item.get("x", 0)),
            y=float(item.get("y", 0)),
            width=float(item.get("width", 0)),
            height=float(item.get("height", 0)),
            has_coords=True,
        )
        nodes.append(node)

    logger.debug("axtree: extracted %d interactive nodes", len(nodes))
    return nodes


def get_overlay_roles(nodes: list[AXNode]) -> list[str]:
    """Return list of overlay/modal roles found in the node list."""
    return list({n.role for n in nodes if n.role in OVERLAY_ROLES})


async def snapshot_hash(page: Any) -> str:
    """Return a quick hash of the page's AX snapshot for change detection."""
    try:
        snap = await page.accessibility.snapshot()
        return hashlib.md5(str(snap).encode()).hexdigest()
    except Exception:
        return ""
