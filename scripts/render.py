"""Self-contained Excalidraw JSON to PNG renderer using Pillow.

Handles: rectangles, ellipses, diamonds, lines, arrows, text (bound + free).
Styling: fill colors, stroke colors, font sizes, arrow bindings.
Font bundling: DejaVu Sans Mono in scripts/fonts/, family mapping.
"""

import json
import math
import warnings
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Font handling
# ---------------------------------------------------------------------------

FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Excalidraw fontFamily -> font file preference
FONT_FAMILY_MAP: dict[int, list[str]] = {
    1: ["DejaVuSansMono.ttf"],                          # Virgil -> monospace
    2: ["Arial.ttf", "Helvetica.ttf", "DejaVuSansMono.ttf"],  # system -> fallback
    3: ["DejaVuSansMono.ttf"],                          # Cascadia -> monospace
}

# System font search paths (macOS + Linux)
_SYSTEM_FONT_DIRS = [
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path("/usr/share/fonts"),
    Path("/usr/share/fonts/truetype"),
    Path.home() / ".fonts",
]


def _find_font_file(candidates: list[str]) -> Optional[Path]:
    """Search bundled fonts dir, then system dirs for the first matching font file."""
    for name in candidates:
        # Check bundled dir first
        bundled = FONT_DIR / name
        if bundled.is_file():
            return bundled
        # Check system dirs
        for sys_dir in _SYSTEM_FONT_DIRS:
            sys_path = sys_dir / name
            if sys_path.is_file():
                return sys_path
    return None


def load_font(font_family: int = 3, font_size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font for the given Excalidraw font family and size.

    Falls back to Pillow's built-in bitmap font if no .ttf is found, with a warning.
    """
    candidates = FONT_FAMILY_MAP.get(font_family, FONT_FAMILY_MAP[3])
    font_path = _find_font_file(candidates)

    if font_path is not None:
        try:
            return ImageFont.truetype(str(font_path), font_size)
        except (OSError, IOError):
            warnings.warn(
                f"Font file {font_path} is corrupt or unreadable; falling back to bitmap font.",
                RuntimeWarning,
                stacklevel=2,
            )
            return ImageFont.load_default()

    warnings.warn(
        f"No font file found for family {font_family} (searched {candidates}); "
        "falling back to Pillow bitmap font.",
        RuntimeWarning,
        stacklevel=2,
    )
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _parse_color(color: str | None) -> str | None:
    """Normalize Excalidraw color strings. Return None for 'transparent'."""
    if not color or color == "transparent":
        return None
    return color


def _fill_and_stroke(elem: dict[str, Any]) -> tuple[str | None, str | None, int]:
    """Extract fill color, stroke color, and stroke width from an element."""
    fill = _parse_color(elem.get("backgroundColor"))
    stroke = _parse_color(elem.get("strokeColor", "#000000"))
    width = max(1, elem.get("strokeWidth", 1))
    # Only fill if fillStyle is 'solid' (skip hachure, cross-hatch for simplicity)
    if elem.get("fillStyle") not in ("solid",):
        fill = None
    return fill, stroke, width


# ---------------------------------------------------------------------------
# Canvas bounds
# ---------------------------------------------------------------------------

def compute_canvas_bounds(
    elements: list[dict[str, Any]], padding: int = 20
) -> tuple[float, float, float, float]:
    """Compute (min_x, min_y, max_x, max_y) encompassing all elements, with padding."""
    if not elements:
        return (0, 0, 100, 100)

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for elem in elements:
        if elem.get("isDeleted"):
            continue
        ex = elem.get("x", 0)
        ey = elem.get("y", 0)
        ew = elem.get("width", 0)
        eh = elem.get("height", 0)

        # For lines/arrows, width/height may be 0; use points instead
        if elem.get("type") in ("line", "arrow") and elem.get("points"):
            for px, py in elem["points"]:
                min_x = min(min_x, ex + px)
                min_y = min(min_y, ey + py)
                max_x = max(max_x, ex + px)
                max_y = max(max_y, ey + py)
        else:
            min_x = min(min_x, ex)
            min_y = min(min_y, ey)
            max_x = max(max_x, ex + ew)
            max_y = max(max_y, ey + eh)

    if min_x == float("inf"):
        return (0, 0, 100, 100)

    return (min_x - padding, min_y - padding, max_x + padding, max_y + padding)


# ---------------------------------------------------------------------------
# Element renderers
# ---------------------------------------------------------------------------

def _draw_rectangle(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float
) -> None:
    fill, stroke, width = _fill_and_stroke(elem)
    x, y = elem["x"] - ox, elem["y"] - oy
    w, h = elem["width"], elem["height"]
    coords = [x, y, x + w, y + h]
    draw.rectangle(coords, fill=fill, outline=stroke, width=width)


def _draw_ellipse(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float
) -> None:
    fill, stroke, width = _fill_and_stroke(elem)
    x, y = elem["x"] - ox, elem["y"] - oy
    w, h = elem["width"], elem["height"]
    draw.ellipse([x, y, x + w, y + h], fill=fill, outline=stroke, width=width)


def _draw_diamond(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float
) -> None:
    fill, stroke, width = _fill_and_stroke(elem)
    x, y = elem["x"] - ox, elem["y"] - oy
    w, h = elem["width"], elem["height"]
    cx, cy = x + w / 2, y + h / 2
    points = [(cx, y), (x + w, cy), (cx, y + h), (x, cy)]
    draw.polygon(points, fill=fill, outline=stroke)
    if width > 1 and stroke:
        draw.line(points + [points[0]], fill=stroke, width=width)


def _draw_line_or_arrow(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float,
    elements_by_id: dict[str, dict],
) -> None:
    _, stroke, width = _fill_and_stroke(elem)
    stroke = stroke or "#000000"
    bx, by = elem["x"] - ox, elem["y"] - oy
    points = elem.get("points", [])
    if len(points) < 2:
        return
    xy = [(bx + px, by + py) for px, py in points]
    draw.line(xy, fill=stroke, width=width)

    # Arrowhead for type == "arrow"
    if elem.get("type") == "arrow" and len(xy) >= 2:
        _draw_arrowhead(draw, xy[-2], xy[-1], stroke, width)


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    p1: tuple[float, float],
    p2: tuple[float, float],
    color: str,
    width: int,
) -> None:
    """Draw a simple arrowhead at p2 pointing from p1 to p2."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return
    # Normalize
    udx, udy = dx / length, dy / length
    arrow_len = max(10, width * 4)
    # Two wing points
    angle = math.pi / 6  # 30 degrees
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    lx = p2[0] - arrow_len * (udx * cos_a - udy * sin_a)
    ly = p2[1] - arrow_len * (udy * cos_a + udx * sin_a)
    rx = p2[0] - arrow_len * (udx * cos_a + udy * sin_a)
    ry = p2[1] - arrow_len * (udy * cos_a - udx * sin_a)
    draw.polygon([(p2[0], p2[1]), (lx, ly), (rx, ry)], fill=color)


def _draw_text(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float,
    elements_by_id: dict[str, dict],
) -> None:
    """Draw a text element. If it has a containerId, center within that container."""
    text = elem.get("text", "")
    if not text:
        return
    font_family = elem.get("fontFamily", 3)
    font_size = elem.get("fontSize", 16)
    font = load_font(font_family, font_size)
    color = _parse_color(elem.get("strokeColor")) or "#000000"

    container_id = elem.get("containerId")
    if container_id and container_id in elements_by_id:
        container = elements_by_id[container_id]
        cx = container["x"] - ox
        cy = container["y"] - oy
        cw = container["width"]
        ch = container["height"]
        # Measure text
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # Center in container
        tx = cx + (cw - tw) / 2
        ty = cy + (ch - th) / 2
    else:
        tx = elem["x"] - ox
        ty = elem["y"] - oy

    # Handle multiline
    lines = text.split("\n")
    line_height = font_size * 1.2
    for i, line in enumerate(lines):
        if elem.get("textAlign") == "center" and not container_id:
            bbox = font.getbbox(line)
            lw = bbox[2] - bbox[0]
            elem_w = elem.get("width", lw)
            lx = tx + (elem_w - lw) / 2
        else:
            lx = tx
        draw.text((lx, ty + i * line_height), line, fill=color, font=font)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def render_element(
    draw: ImageDraw.ImageDraw,
    elem: dict[str, Any],
    offset_x: float,
    offset_y: float,
    elements_by_id: dict[str, dict],
) -> None:
    """Render a single Excalidraw element onto the draw context."""
    if elem.get("isDeleted"):
        return
    etype = elem.get("type", "")
    if etype == "rectangle":
        _draw_rectangle(draw, elem, offset_x, offset_y)
    elif etype == "ellipse":
        _draw_ellipse(draw, elem, offset_x, offset_y)
    elif etype == "diamond":
        _draw_diamond(draw, elem, offset_x, offset_y)
    elif etype in ("line", "arrow"):
        _draw_line_or_arrow(draw, elem, offset_x, offset_y, elements_by_id)
    elif etype == "text":
        _draw_text(draw, elem, offset_x, offset_y, elements_by_id)
    # Silently ignore unknown types (frame, freedraw, image, etc.)


# ---------------------------------------------------------------------------
# ExcalidrawRenderer -- main entry point
# ---------------------------------------------------------------------------

class ExcalidrawRenderer:
    """Renders Excalidraw JSON data to a Pillow Image."""

    def render(self, data: dict[str, Any]) -> Image.Image:
        """Render Excalidraw JSON dict to a Pillow Image.

        Args:
            data: Parsed Excalidraw JSON with 'elements' and optional 'appState'.

        Returns:
            PIL Image with the rendered diagram.
        """
        elements = [e for e in data.get("elements", []) if not e.get("isDeleted")]
        app_state = data.get("appState", {})
        bg_color = app_state.get("viewBackgroundColor", "#ffffff")

        min_x, min_y, max_x, max_y = compute_canvas_bounds(elements)
        width = max(1, int(max_x - min_x))
        height = max(1, int(max_y - min_y))

        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Index elements by ID for text container lookups
        elements_by_id: dict[str, dict] = {}
        for elem in data.get("elements", []):
            eid = elem.get("id")
            if eid:
                elements_by_id[eid] = elem

        # Render shapes first, then text on top
        for elem in elements:
            if elem.get("type") != "text":
                render_element(draw, elem, min_x, min_y, elements_by_id)
        for elem in elements:
            if elem.get("type") == "text":
                render_element(draw, elem, min_x, min_y, elements_by_id)

        return img

    def render_to_file(self, data: dict[str, Any], output_path: Path) -> None:
        """Render Excalidraw JSON and save as PNG.

        Args:
            data: Parsed Excalidraw JSON.
            output_path: Path to write the PNG file.
        """
        img = self.render(data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "PNG")


# ---------------------------------------------------------------------------
# CLI entry point: find and render stale .excalidraw files
# ---------------------------------------------------------------------------

def find_and_render_excalidraw(
    notes_dir: Path,
) -> dict[str, list[str]]:
    """Find all .excalidraw files under notes_dir and render stale ones to PNG.

    Returns dict with keys: 'rendered', 'skipped', 'errors'.
    """
    results: dict[str, list[str]] = {"rendered": [], "skipped": [], "errors": []}

    excalidraw_files = sorted(notes_dir.rglob("*.excalidraw"))
    renderer = ExcalidrawRenderer()

    for exc_path in excalidraw_files:
        png_path = exc_path.with_suffix(".png")
        try:
            # Check staleness
            if png_path.exists():
                exc_mtime = exc_path.stat().st_mtime
                png_mtime = png_path.stat().st_mtime
                if png_mtime >= exc_mtime:
                    results["skipped"].append(str(png_path))
                    continue

            # Parse and render
            raw = exc_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            renderer.render_to_file(data, png_path)
            results["rendered"].append(str(png_path))

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            warnings.warn(
                f"Failed to render {exc_path}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            results["errors"].append(str(exc_path))
        except Exception as exc:
            warnings.warn(
                f"Unexpected error rendering {exc_path}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            results["errors"].append(str(exc_path))

    return results


def run(args: Any = None) -> int:
    """CLI handler for the 'render' command."""
    from scripts.repo_id import resolve_repo_id, get_notes_dir

    from pathlib import Path

    repo_id = getattr(args, "repo_id", None) if args else None
    rid = repo_id or resolve_repo_id()
    notes_dir = Path.home() / ".claude" / "repo_notes" / rid / "notes"

    if not notes_dir.exists():
        print(f"Notes directory not found: {notes_dir}")
        return 1

    results = find_and_render_excalidraw(notes_dir)

    if results["rendered"]:
        print(f"Rendered {len(results['rendered'])} diagram(s):")
        for p in results["rendered"]:
            print(f"  {p}")
    if results["skipped"]:
        print(f"Skipped {len(results['skipped'])} fresh diagram(s)")
    if results["errors"]:
        print(f"WARNING: {len(results['errors'])} diagram(s) failed to render:")
        for p in results["errors"]:
            print(f"  {p}")

    return 0
