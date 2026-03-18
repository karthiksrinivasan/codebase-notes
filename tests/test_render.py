"""Tests for scripts.render -- Excalidraw JSON to PNG renderer."""

import json
import os
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from scripts.render import (
    load_font,
    FONT_DIR,
    FONT_FAMILY_MAP,
    render_element,
    compute_canvas_bounds,
    ExcalidrawRenderer,
    find_and_render_excalidraw,
)


class TestFontLoading:
    """Test font resolution and fallback logic."""

    def test_font_dir_exists_at_expected_path(self):
        """The fonts/ directory should exist inside scripts/."""
        expected = Path(__file__).resolve().parent.parent / "scripts" / "fonts"
        assert FONT_DIR == expected

    def test_font_family_map_keys(self):
        """Font family map must cover Excalidraw families 1, 2, 3."""
        assert set(FONT_FAMILY_MAP.keys()) == {1, 2, 3}

    def test_load_font_returns_truetype_or_fallback(self):
        """load_font should return a usable font object (TrueType or fallback bitmap)."""
        from PIL import ImageFont

        font = load_font(font_family=3, font_size=16)
        # Must have getbbox (works for both TrueType and bitmap fallback)
        assert hasattr(font, "getbbox")

    def test_load_font_fallback_on_missing_file(self):
        """When the .ttf file is missing, load_font falls back to Pillow bitmap font with a warning."""
        from PIL import ImageFont

        with patch("scripts.render.FONT_DIR", Path("/nonexistent/fonts")):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                font = load_font(font_family=3, font_size=16)
                assert len(w) >= 1
                assert "fallback" in str(w[0].message).lower() or "font" in str(w[0].message).lower()
            # Still returns a usable font
            assert hasattr(font, "getbbox")

    def test_load_font_family_2_tries_system_then_fallback(self):
        """Font family 2 (Helvetica) should try system Arial, then fall back to monospace."""
        font = load_font(font_family=2, font_size=14)
        assert hasattr(font, "getbbox")


class TestCanvasBounds:
    """Test bounding-box computation from element list."""

    def test_single_rectangle(self):
        elements = [{"type": "rectangle", "x": 10, "y": 20, "width": 100, "height": 50}]
        min_x, min_y, max_x, max_y = compute_canvas_bounds(elements)
        assert min_x <= 10
        assert min_y <= 20
        assert max_x >= 110
        assert max_y >= 70

    def test_multiple_elements(self):
        elements = [
            {"type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 50},
            {"type": "ellipse", "x": 200, "y": 200, "width": 60, "height": 40},
        ]
        min_x, min_y, max_x, max_y = compute_canvas_bounds(elements)
        assert min_x <= 0
        assert min_y <= 0
        assert max_x >= 260
        assert max_y >= 240

    def test_empty_elements_returns_defaults(self):
        min_x, min_y, max_x, max_y = compute_canvas_bounds([])
        # Should return some sensible default (e.g. 0,0,100,100)
        assert max_x > min_x
        assert max_y > min_y


class TestRenderElement:
    """Test individual element rendering onto a draw context."""

    def test_rectangle_draws_without_error(self):
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "rectangle",
            "x": 10, "y": 10, "width": 80, "height": 40,
            "strokeColor": "#000000",
            "backgroundColor": "#e3f2fd",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roundness": None,
        }
        # Should not raise
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})

    def test_ellipse_draws_without_error(self):
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "ellipse",
            "x": 10, "y": 10, "width": 80, "height": 60,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
        }
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})

    def test_diamond_draws_without_error(self):
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "diamond",
            "x": 10, "y": 10, "width": 80, "height": 80,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
        }
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})

    def test_text_draws_without_error(self):
        img = Image.new("RGB", (300, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "text",
            "x": 10, "y": 10, "width": 200, "height": 30,
            "text": "Hello World",
            "fontSize": 16,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#000000",
            "containerId": None,
        }
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})


SIMPLE_EXCALIDRAW = {
    "type": "excalidraw",
    "version": 2,
    "source": "test",
    "elements": [
        {
            "id": "rect1",
            "type": "rectangle",
            "x": 50, "y": 50, "width": 200, "height": 100,
            "strokeColor": "#000000",
            "backgroundColor": "#e3f2fd",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roughness": 0,
            "roundness": None,
            "isDeleted": False,
        },
        {
            "id": "text1",
            "type": "text",
            "x": 80, "y": 80, "width": 140, "height": 30,
            "text": "Service A",
            "fontSize": 20,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#000000",
            "containerId": "rect1",
            "isDeleted": False,
        },
        {
            "id": "rect2",
            "type": "rectangle",
            "x": 400, "y": 50, "width": 200, "height": 100,
            "strokeColor": "#000000",
            "backgroundColor": "#c8e6c9",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roughness": 0,
            "roundness": None,
            "isDeleted": False,
        },
        {
            "id": "text2",
            "type": "text",
            "x": 430, "y": 80, "width": 140, "height": 30,
            "text": "Service B",
            "fontSize": 20,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#000000",
            "containerId": "rect2",
            "isDeleted": False,
        },
        {
            "id": "arrow1",
            "type": "arrow",
            "x": 250, "y": 100,
            "width": 150, "height": 0,
            "points": [[0, 0], [150, 0]],
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roughness": 0,
            "isDeleted": False,
            "startBinding": {"elementId": "rect1", "focus": 0, "gap": 1},
            "endBinding": {"elementId": "rect2", "focus": 0, "gap": 1},
        },
    ],
    "appState": {"viewBackgroundColor": "#ffffff"},
}


class TestExcalidrawRenderer:
    """Integration tests: full JSON to PNG pipeline."""

    def test_render_json_to_image(self):
        renderer = ExcalidrawRenderer()
        img = renderer.render(SIMPLE_EXCALIDRAW)
        assert isinstance(img, Image.Image)
        assert img.width > 0
        assert img.height > 0

    def test_render_produces_reasonable_dimensions(self):
        renderer = ExcalidrawRenderer()
        img = renderer.render(SIMPLE_EXCALIDRAW)
        # Canvas should encompass all elements (50..600 x, 50..150 y) + padding
        assert img.width >= 500
        assert img.height >= 80
        # But not absurdly large
        assert img.width < 2000
        assert img.height < 1000

    def test_render_white_background(self):
        renderer = ExcalidrawRenderer()
        img = renderer.render(SIMPLE_EXCALIDRAW)
        # Top-left corner should be white (background)
        pixel = img.getpixel((0, 0))
        assert pixel == (255, 255, 255) or pixel == (255, 255, 255, 255)

    def test_render_to_file(self, tmp_path):
        renderer = ExcalidrawRenderer()
        out_path = tmp_path / "test_output.png"
        renderer.render_to_file(SIMPLE_EXCALIDRAW, out_path)
        assert out_path.exists()
        assert out_path.stat().st_size > 100  # Non-trivial PNG

    def test_render_empty_elements(self):
        data = {"type": "excalidraw", "version": 2, "elements": [], "appState": {}}
        renderer = ExcalidrawRenderer()
        img = renderer.render(data)
        assert isinstance(img, Image.Image)

    def test_render_deleted_elements_skipped(self):
        data = {
            "type": "excalidraw", "version": 2, "elements": [
                {"id": "del1", "type": "rectangle", "x": 0, "y": 0,
                 "width": 100, "height": 100, "isDeleted": True,
                 "strokeColor": "#000000", "backgroundColor": "#ff0000",
                 "fillStyle": "solid", "strokeWidth": 1},
            ],
            "appState": {},
        }
        renderer = ExcalidrawRenderer()
        img = renderer.render(data)
        # Should produce only a small default-size canvas
        assert isinstance(img, Image.Image)


class TestFindAndRender:
    """Test the CLI-facing function that finds .excalidraw files and renders stale ones."""

    def test_renders_new_excalidraw_file(self, tmp_path):
        """A .excalidraw without a corresponding .png should be rendered."""
        excalidraw_file = tmp_path / "diagram.excalidraw"
        excalidraw_file.write_text(json.dumps(SIMPLE_EXCALIDRAW))

        results = find_and_render_excalidraw(tmp_path)
        png_file = tmp_path / "diagram.png"
        assert png_file.exists()
        assert len(results["rendered"]) == 1
        assert results["rendered"][0] == str(png_file)

    def test_skips_fresh_png(self, tmp_path):
        """If .png is newer than .excalidraw, skip rendering."""
        excalidraw_file = tmp_path / "diagram.excalidraw"
        excalidraw_file.write_text(json.dumps(SIMPLE_EXCALIDRAW))
        png_file = tmp_path / "diagram.png"
        # Pre-render
        renderer = ExcalidrawRenderer()
        renderer.render_to_file(SIMPLE_EXCALIDRAW, png_file)
        # Ensure png mtime >= excalidraw mtime
        import time
        time.sleep(0.05)
        os.utime(png_file, None)  # touch to make it newer

        results = find_and_render_excalidraw(tmp_path)
        assert len(results["rendered"]) == 0
        assert len(results["skipped"]) == 1

    def test_re_renders_stale_png(self, tmp_path):
        """If .excalidraw is newer than .png, re-render."""
        excalidraw_file = tmp_path / "diagram.excalidraw"
        png_file = tmp_path / "diagram.png"
        # Create PNG first, then excalidraw (so excalidraw is newer)
        png_file.write_bytes(b"old png data")
        import time
        time.sleep(0.05)
        excalidraw_file.write_text(json.dumps(SIMPLE_EXCALIDRAW))

        results = find_and_render_excalidraw(tmp_path)
        assert len(results["rendered"]) == 1
        # PNG should now be a valid image
        img = Image.open(png_file)
        assert img.width > 0

    def test_warns_on_invalid_json(self, tmp_path):
        """Invalid JSON should warn, not error."""
        bad_file = tmp_path / "broken.excalidraw"
        bad_file.write_text("not valid json {{{")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            results = find_and_render_excalidraw(tmp_path)
            assert len(results["errors"]) == 1
            assert len(w) >= 1

    def test_finds_in_subdirectories(self, tmp_path):
        """Should recursively find .excalidraw files in subdirs."""
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        (subdir / "nested.excalidraw").write_text(json.dumps(SIMPLE_EXCALIDRAW))

        results = find_and_render_excalidraw(tmp_path)
        assert len(results["rendered"]) == 1
        assert (subdir / "nested.png").exists()
