"""Tests for context_index.py."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.context_index import (
    _extract_title,
    _extract_tracked_paths,
    _extract_overview_description,
    _load_staleness_map,
    _generate_index,
    _filter_stdin,
    _wrap_json_envelope,
)


@pytest.fixture
def repo_dir(tmp_path):
    """Create a fake repo_notes directory with sample content."""
    # notes/
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "00-overview.md").write_text(
        "---\nlast_updated: 2026-03-18\n---\n# Overview\n\n"
        "## What is this?\n\nA sample codebase for testing.\n"
    )
    auth = notes / "01-auth"
    auth.mkdir()
    (auth / "index.md").write_text(
        "---\ngit_tracked_paths:\n  - path: src/auth\n  - path: src/middleware\n---\n"
        "# Authentication\n\nAuth system notes.\n"
    )
    (auth / "01-oauth.md").write_text("# OAuth Flow\n\nOAuth details here.\n")
    # A RULES.md that should be excluded
    (notes / "RULES.md").write_text("# Rules\n\nDo not include me.\n")

    # research/
    research = tmp_path / "research"
    research.mkdir()
    (research / "01-vectors.md").write_text("# Vector DBs\n\nSome research notes.\n")

    # projects/
    projects = tmp_path / "projects"
    projects.mkdir()
    proj = projects / "auth-redesign"
    proj.mkdir()
    (proj / "index.md").write_text("# Auth Redesign\n\nGoals here.\n")

    # commits/
    commits = tmp_path / "commits"
    commits.mkdir()
    author = commits / "alice"
    author.mkdir()
    (author / "backend.md").write_text("# Alice Backend\n\nRecent commits.\n")

    return tmp_path


class TestExtractTitle:
    def test_heading_extracted(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("# My Great Title\n\nSome content.\n")
        assert _extract_title(md) == "My Great Title"

    def test_fallback_to_stem(self, tmp_path):
        md = tmp_path / "no-heading.md"
        md.write_text("Just a paragraph with no heading.\n")
        assert _extract_title(md) == "no-heading"

    def test_frontmatter_before_heading(self, tmp_path):
        md = tmp_path / "with-fm.md"
        md.write_text("---\ntitle: ignored\n---\n# Real Title\n\nBody.\n")
        assert _extract_title(md) == "Real Title"

    def test_missing_file(self, tmp_path):
        md = tmp_path / "missing.md"
        assert _extract_title(md) == "missing"


class TestExtractTrackedPaths:
    def test_extracts_paths_from_frontmatter(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("placeholder")
        fm = {"git_tracked_paths": [{"path": "src/auth"}, {"path": "src/api"}]}
        with patch("scripts.staleness.parse_frontmatter", return_value=fm):
            result = _extract_tracked_paths(md)
        assert result == "src/auth, src/api"

    def test_no_frontmatter(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("placeholder")
        with patch("scripts.staleness.parse_frontmatter", return_value=None):
            result = _extract_tracked_paths(md)
        assert result == ""

    def test_empty_paths(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("placeholder")
        fm = {"git_tracked_paths": []}
        with patch("scripts.staleness.parse_frontmatter", return_value=fm):
            result = _extract_tracked_paths(md)
        assert result == ""

    def test_missing_path_key(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("placeholder")
        fm = {"git_tracked_paths": [{"other": "value"}, {"path": "src/ok"}]}
        with patch("scripts.staleness.parse_frontmatter", return_value=fm):
            result = _extract_tracked_paths(md)
        assert result == "src/ok"


class TestExtractOverviewDescription:
    def test_what_is_this_section(self, tmp_path):
        overview = tmp_path / "00-overview.md"
        overview.write_text(
            "# Overview\n\n## What is this?\n\nA great codebase.\n\nMore details.\n"
        )
        assert _extract_overview_description(overview) == "A great codebase."

    def test_fallback_to_first_paragraph(self, tmp_path):
        overview = tmp_path / "00-overview.md"
        overview.write_text("# Overview\n\nFallback paragraph here.\n")
        assert _extract_overview_description(overview) == "Fallback paragraph here."

    def test_missing_file(self, tmp_path):
        overview = tmp_path / "nonexistent.md"
        assert _extract_overview_description(overview) == ""

    def test_with_frontmatter(self, tmp_path):
        overview = tmp_path / "00-overview.md"
        overview.write_text(
            "---\nlast_updated: 2026-01-01\n---\n# Overview\n\n"
            "## What is this?\n\nDescription after frontmatter.\n"
        )
        assert _extract_overview_description(overview) == "Description after frontmatter."


class TestLoadStalenessMap:
    def test_loads_from_cache(self, tmp_path):
        cached = [
            {"note_path": "01-auth/index.md", "status": "STALE"},
            {"note_path": "00-overview.md", "status": "CURRENT"},
        ]
        with patch("scripts.staleness.load_cache", return_value=cached):
            result = _load_staleness_map(tmp_path)
        assert result == {
            "01-auth/index.md": "STALE",
            "00-overview.md": "CURRENT",
        }

    def test_missing_cache_returns_empty(self, tmp_path):
        with patch("scripts.staleness.load_cache", return_value=None):
            result = _load_staleness_map(tmp_path)
        assert result == {}

    def test_skips_entries_without_note_path(self, tmp_path):
        cached = [
            {"status": "STALE"},
            {"note_path": "ok.md", "status": "CURRENT"},
        ]
        with patch("scripts.staleness.load_cache", return_value=cached):
            result = _load_staleness_map(tmp_path)
        assert result == {"ok.md": "CURRENT"}


class TestGenerateIndex:
    def _generate(self, repo_dir):
        """Helper to generate index with mocked dependencies."""
        with patch("scripts.staleness.load_cache", return_value=None), \
             patch("scripts.staleness.parse_frontmatter", return_value=None):
            return _generate_index("org--repo", repo_dir)

    def test_all_sections_appear(self, repo_dir):
        output = self._generate(repo_dir)
        assert "## notes/" in output
        assert "## research/" in output
        assert "## projects/" in output
        assert "## commits/" in output

    def test_rules_md_excluded(self, repo_dir):
        output = self._generate(repo_dir)
        assert "RULES.md" not in output

    def test_empty_directories_omitted(self, tmp_path):
        # Only create an empty notes/ dir
        (tmp_path / "notes").mkdir()
        with patch("scripts.staleness.load_cache", return_value=None), \
             patch("scripts.staleness.parse_frontmatter", return_value=None):
            output = _generate_index("org--repo", tmp_path)
        assert "## notes/" not in output
        assert "## research/" not in output

    def test_header_contains_repo_id(self, repo_dir):
        output = self._generate(repo_dir)
        assert "# Codebase Notes: org--repo" in output

    def test_overview_description_included(self, repo_dir):
        output = self._generate(repo_dir)
        assert "A sample codebase for testing." in output

    def test_notes_table_has_tracked_paths_column(self, repo_dir):
        output = self._generate(repo_dir)
        assert "| Tracked Paths |" in output

    def test_commits_table_has_author_and_area(self, repo_dir):
        output = self._generate(repo_dir)
        assert "alice" in output
        assert "backend" in output

    def test_footer_present(self, repo_dir):
        output = self._generate(repo_dir)
        assert "Notes root:" in output
        assert "STALE" in output  # The advice line mentions STALE


class TestFilterStdin:
    def test_notes_path_returns_true(self):
        data = {
            "tool_input": {
                "file_path": str(Path.home() / ".claude" / "repo_notes" / "org--repo" / "notes" / "file.md")
            }
        }
        with patch("sys.stdin", StringIO(json.dumps(data))):
            assert _filter_stdin() is True

    def test_non_notes_path_returns_false(self):
        data = {"tool_input": {"file_path": "/tmp/random/file.md"}}
        with patch("sys.stdin", StringIO(json.dumps(data))):
            assert _filter_stdin() is False

    def test_invalid_json_returns_false(self):
        with patch("sys.stdin", StringIO("not json at all")):
            assert _filter_stdin() is False

    def test_empty_file_path_returns_false(self):
        data = {"tool_input": {"file_path": ""}}
        with patch("sys.stdin", StringIO(json.dumps(data))):
            assert _filter_stdin() is False

    def test_missing_tool_input_returns_false(self):
        data = {"other_key": "value"}
        with patch("sys.stdin", StringIO(json.dumps(data))):
            assert _filter_stdin() is False


class TestWrapJsonEnvelope:
    def test_correct_json_structure(self):
        result = json.loads(_wrap_json_envelope("hello world"))
        assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert result["hookSpecificOutput"]["additionalContext"] == "hello world"

    def test_special_characters(self):
        content = 'line1\nline2\n"quoted"\ttab'
        result = json.loads(_wrap_json_envelope(content))
        assert result["hookSpecificOutput"]["additionalContext"] == content

    def test_empty_content(self):
        result = json.loads(_wrap_json_envelope(""))
        assert result["hookSpecificOutput"]["additionalContext"] == ""
