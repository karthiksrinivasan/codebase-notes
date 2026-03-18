"""Tests for navigation link rebuilding."""

import re
from pathlib import Path

import pytest

from scripts.nav_links import (
    build_notes_tree,
    compute_nav_links,
    NAV_PATTERN,
    SUBTOPICS_PATTERN,
    insert_or_replace_nav,
    rebuild_all_nav_links,
    format_nav_line,
    format_subtopics_line,
)


class TestNavPatterns:
    def test_nav_pattern_matches_standard(self):
        line = '> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)'
        assert NAV_PATTERN.match(line)

    def test_nav_pattern_case_insensitive(self):
        line = '> **navigation:** Up: [Parent](../index.md)'
        assert NAV_PATTERN.match(line)

    def test_nav_pattern_with_extra_whitespace(self):
        line = '>  **Navigation:**  Up: [Parent](../index.md)'
        assert NAV_PATTERN.match(line)

    def test_nav_pattern_no_match_on_random_line(self):
        line = 'Some random text about navigation'
        assert NAV_PATTERN.match(line) is None

    def test_subtopics_pattern_matches(self):
        line = '> **Sub-topics:** [API](./01-api/index.md) | [Models](./02-models/index.md)'
        assert SUBTOPICS_PATTERN.match(line)

    def test_subtopics_pattern_case_insensitive(self):
        line = '> **sub-topics:** [API](./01-api/index.md)'
        assert SUBTOPICS_PATTERN.match(line)


class TestBuildNotesTree:
    def test_flat_structure(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("---\n---\n# Overview\n")
        (notes / "RULES.md").write_text("# Rules\n")

        tree = build_notes_tree(notes)
        paths = [str(e["path"].name) for e in tree]
        assert "00-overview.md" in paths
        assert "RULES.md" not in paths

    def test_nested_structure(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("# Overview\n")

        sub = notes / "01-api"
        sub.mkdir()
        (sub / "index.md").write_text("# API\n")
        (sub / "01-endpoints.md").write_text("# Endpoints\n")
        (sub / "02-middleware.md").write_text("# Middleware\n")

        tree = build_notes_tree(notes)
        root_names = [e["path"].name for e in tree]
        assert "00-overview.md" in root_names

    def test_sorted_by_name(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "02-second.md").write_text("# Second\n")
        (notes / "01-first.md").write_text("# First\n")
        (notes / "03-third.md").write_text("# Third\n")

        tree = build_notes_tree(notes)
        names = [e["path"].name for e in tree]
        assert names == ["01-first.md", "02-second.md", "03-third.md"]


class TestComputeNavLinks:
    def _make_structure(self, tmp_path):
        """Create a standard test notes structure."""
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("---\n---\n# Overview\n")

        api = notes / "01-api"
        api.mkdir()
        (api / "index.md").write_text("---\n---\n# API\n")
        (api / "01-endpoints.md").write_text("---\n---\n# Endpoints\n")
        (api / "02-middleware.md").write_text("---\n---\n# Middleware\n")

        models = notes / "02-models"
        models.mkdir()
        (models / "index.md").write_text("---\n---\n# Models\n")
        (models / "01-schemas.md").write_text("---\n---\n# Schemas\n")

        return notes

    def test_overview_has_no_up(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "00-overview.md", notes)
        assert links["up"] is None

    def test_overview_has_next_but_no_prev(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "00-overview.md", notes)
        assert links["prev"] is None
        assert links["next"] is not None
        assert "01-api/index.md" in links["next"]

    def test_index_up_points_to_overview(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "index.md", notes)
        assert links["up"] is not None
        assert "00-overview.md" in links["up"]

    def test_index_has_subtopics(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "index.md", notes)
        assert links["is_index"] is True
        assert len(links["subtopics"]) == 2
        labels = [s[0] for s in links["subtopics"]]
        assert "Endpoints" in labels
        assert "Middleware" in labels

    def test_child_up_points_to_index(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "01-endpoints.md", notes)
        assert links["up"] is not None
        assert "index.md" in links["up"]

    def test_child_prev_next(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "01-endpoints.md", notes)
        assert links["prev"] is None
        assert links["next"] is not None
        assert "02-middleware.md" in links["next"]


class TestInsertOrReplaceNav:
    def test_inserts_after_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: test\n---\n# Title\nContent\n")
        result = insert_or_replace_nav(note, "> **Navigation:** Up: [Parent](../)", "")
        assert result is True
        text = note.read_text()
        assert "> **Navigation:**" in text
        lines = text.split("\n")
        fm_end = next(i for i, l in enumerate(lines[1:], 1) if l.strip() == "---")
        assert "> **Navigation:**" in lines[fm_end + 1]

    def test_replaces_existing_nav(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: test\n---\n> **Navigation:** old\n# Title\n")
        result = insert_or_replace_nav(note, "> **Navigation:** new", "")
        assert result is True
        text = note.read_text()
        assert "> **Navigation:** new" in text
        assert "> **Navigation:** old" not in text

    def test_no_change_returns_false(self, tmp_path):
        note = tmp_path / "note.md"
        content = "---\ntitle: test\n---\n> **Navigation:** same\n# Title\n"
        note.write_text(content)
        result = insert_or_replace_nav(note, "> **Navigation:** same", "")
        assert result is False


class TestRebuildAllNavLinks:
    def test_rebuilds_entire_structure(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("---\n---\n# Overview\n")

        api = notes / "01-api"
        api.mkdir()
        (api / "index.md").write_text("---\n---\n# API\n")
        (api / "01-endpoints.md").write_text("---\n---\n# Endpoints\n")

        modified = rebuild_all_nav_links(notes)
        assert len(modified) > 0

        # Check overview got a next link
        overview_text = (notes / "00-overview.md").read_text()
        assert "> **Navigation:**" in overview_text
