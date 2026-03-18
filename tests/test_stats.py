"""Tests for stats.py."""

import json
from pathlib import Path

import pytest

from scripts.stats import _count_dir, collect_stats, format_stats, format_json


@pytest.fixture
def repo_dir(tmp_path):
    """Create a fake repo_notes directory with sample content."""
    # notes/
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "00-overview.md").write_text("# Overview\n\nThis is the overview.\n")
    auth = notes / "01-auth"
    auth.mkdir()
    (auth / "index.md").write_text("---\nlast_updated: 2026-03-18\n---\n# Auth\n\nAuth system.\n")
    (auth / "01-oauth.md").write_text("# OAuth\n\nOAuth details here.\n")
    api = notes / "02-api"
    api.mkdir()
    (api / "index.md").write_text("# API\n\nAPI layer.\n")

    # notes/research/
    research = notes / "research"
    research.mkdir()
    (research / "index.md").write_text("# Research\n")
    (research / "01-vectors.md").write_text("# Vector DBs\n\nSome research notes.\n")

    # commits/
    commits = tmp_path / "commits"
    commits.mkdir()
    author = commits / "alice"
    author.mkdir()
    (author / "backend.md").write_text("# Alice Backend\n\nRecent commits.\n")

    # projects/
    projects = tmp_path / "projects"
    projects.mkdir()
    proj = projects / "auth-redesign"
    proj.mkdir()
    (proj / "index.md").write_text("---\nproject: auth-redesign\n---\n# Auth Redesign\n\nGoals here.\n")

    return tmp_path


class TestCountDir:
    def test_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        result = _count_dir(d)
        assert result == {"sections": 0, "files": 0, "lines": 0, "words": 0}

    def test_nonexistent_dir(self, tmp_path):
        result = _count_dir(tmp_path / "nope")
        assert result == {"sections": 0, "files": 0, "lines": 0, "words": 0}

    def test_counts_sections_files_lines_words(self, repo_dir):
        notes = repo_dir / "notes"
        result = _count_dir(notes)
        # sections: 01-auth, 02-api, research (direct children dirs)
        assert result["sections"] == 3
        # files: 00-overview.md, 01-auth/index.md, 01-auth/01-oauth.md,
        #        02-api/index.md, research/index.md, research/01-vectors.md
        assert result["files"] == 6
        assert result["lines"] > 0
        assert result["words"] > 0

    def test_ignores_non_md_files(self, tmp_path):
        d = tmp_path / "mixed"
        d.mkdir()
        (d / "note.md").write_text("hello world\n")
        (d / "diagram.excalidraw").write_text('{"elements": []}')
        (d / "image.png").write_bytes(b"\x89PNG")
        result = _count_dir(d)
        assert result["files"] == 1


class TestCollectStats:
    def test_collects_all_directories(self, repo_dir):
        stats = collect_stats(repo_dir)
        assert set(stats.keys()) == {"notes", "research", "commits", "projects"}

    def test_notes_has_content(self, repo_dir):
        stats = collect_stats(repo_dir)
        assert stats["notes"]["files"] > 0

    def test_commits_has_content(self, repo_dir):
        stats = collect_stats(repo_dir)
        assert stats["commits"]["files"] == 1
        assert stats["commits"]["sections"] == 1

    def test_projects_has_content(self, repo_dir):
        stats = collect_stats(repo_dir)
        assert stats["projects"]["files"] == 1
        assert stats["projects"]["sections"] == 1


class TestFormatStats:
    def test_contains_header_and_totals(self, repo_dir):
        stats = collect_stats(repo_dir)
        output = format_stats(stats, "org--repo")
        assert "org--repo" in output
        assert "TOTAL" in output
        assert "notes" in output
        assert "research" in output
        assert "commits" in output
        assert "projects" in output

    def test_table_alignment(self, repo_dir):
        stats = collect_stats(repo_dir)
        output = format_stats(stats, "org--repo")
        lines = output.strip().split("\n")
        # Header + separator + 4 rows + separator + total = 8 lines (+ title + === + blank)
        assert len(lines) >= 8


class TestFormatJson:
    def test_valid_json(self, repo_dir):
        stats = collect_stats(repo_dir)
        output = format_json(stats, "org--repo")
        data = json.loads(output)
        assert data["repo_id"] == "org--repo"
        assert "notes" in data
        assert "research" in data
        assert "commits" in data
        assert "projects" in data

    def test_json_has_all_fields(self, repo_dir):
        stats = collect_stats(repo_dir)
        data = json.loads(format_json(stats, "org--repo"))
        for key in ("notes", "research", "commits", "projects"):
            assert set(data[key].keys()) == {"sections", "files", "lines", "words"}
