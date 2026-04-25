"""Tests for staleness checking."""

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.staleness import (
    parse_frontmatter,
    check_note_staleness,
    check_all_notes,
    check_all_repos,
    load_cache,
    save_cache,
    is_cache_valid,
    StalenessStatus,
    NoteReport,
    format_report,
)


class TestParseFrontmatter:
    def test_parse_valid_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "git_tracked_paths:\n"
            "  - path: src/api/\n"
            "    commit: abc1234\n"
            "  - path: src/models/\n"
            "    commit: def5678\n"
            "last_updated: 2026-03-16\n"
            "---\n"
            "# My Note\n"
            "Content here.\n"
        )
        fm = parse_frontmatter(note)
        assert fm is not None
        assert len(fm["git_tracked_paths"]) == 2
        assert fm["git_tracked_paths"][0]["path"] == "src/api/"
        assert fm["git_tracked_paths"][0]["commit"] == "abc1234"

    def test_parse_no_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("# Just a heading\nNo frontmatter here.\n")
        fm = parse_frontmatter(note)
        assert fm is None

    def test_parse_frontmatter_no_tracked_paths(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nlast_updated: 2026-03-16\n---\n# Note\n")
        fm = parse_frontmatter(note)
        assert fm is not None
        assert "git_tracked_paths" not in fm

    def test_parse_empty_file(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("")
        fm = parse_frontmatter(note)
        assert fm is None

    def test_parse_frontmatter_only_opening_dashes(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: broken\n# No closing dashes\n")
        fm = parse_frontmatter(note)
        assert fm is None


class TestCheckNoteStaleness:
    def test_fresh_note(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\ngit_tracked_paths:\n  - path: src/api/\n    commit: abc1234\n---\n# Fresh note\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            report = check_note_staleness(note, tmp_path)
        assert report.status == StalenessStatus.FRESH
        assert report.changed_files == []
        assert report.commit == "abc1234"

    def test_stale_note(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\ngit_tracked_paths:\n  - path: src/models/\n    commit: def5678\n---\n# Stale note\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="src/models/user.py\nsrc/models/auth.py\n")
            report = check_note_staleness(note, tmp_path)
        assert report.status == StalenessStatus.STALE
        assert len(report.changed_files) == 2
        assert "src/models/user.py" in report.changed_files

    def test_no_tracking_note(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("# No frontmatter\nJust content.\n")
        report = check_note_staleness(note, tmp_path)
        assert report.status == StalenessStatus.NO_TRACKING

    def test_multiple_tracked_paths(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\ngit_tracked_paths:\n  - path: src/api/\n    commit: abc1234\n  - path: src/models/\n    commit: def5678\n---\n# Multi\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="src/models/user.py\n"),
            ]
            report = check_note_staleness(note, tmp_path)
        assert report.status == StalenessStatus.STALE
        assert report.changed_files == ["src/models/user.py"]

    def test_git_timeout_handled(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\ngit_tracked_paths:\n  - path: src/\n    commit: aaa1111\n---\n# Timeout note\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
            report = check_note_staleness(note, tmp_path)
        assert report.status == StalenessStatus.FRESH


class TestCheckAllNotes:
    def test_multiple_notes(self, tmp_path):
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        (notes_dir / "01-fresh.md").write_text(
            "---\ngit_tracked_paths:\n  - path: src/a/\n    commit: aaa\n---\n# Fresh\n"
        )
        (notes_dir / "02-stale.md").write_text(
            "---\ngit_tracked_paths:\n  - path: src/b/\n    commit: bbb\n---\n# Stale\n"
        )
        (notes_dir / "03-notrack.md").write_text("# No tracking\n")

        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="src/b/x.py\n"),
            ]
            reports = check_all_notes(notes_dir, tmp_path)

        assert len(reports) == 3
        assert reports[0].status == StalenessStatus.FRESH
        assert reports[1].status == StalenessStatus.STALE
        assert reports[2].status == StalenessStatus.NO_TRACKING

    def test_empty_dir(self, tmp_path):
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        reports = check_all_notes(notes_dir, tmp_path)
        assert reports == []

    def test_nonexistent_dir(self, tmp_path):
        reports = check_all_notes(tmp_path / "nonexistent", tmp_path)
        assert reports == []


class TestCaching:
    def test_save_and_load_cache(self, tmp_path):
        reports = [
            NoteReport(note_path="/notes/01-api.md", status=StalenessStatus.FRESH, message="0 files changed"),
            NoteReport(note_path="/notes/02-models.md", status=StalenessStatus.STALE,
                       changed_files=["src/models/user.py"], commit="abc1234",
                       message="1 files changed since abc1234"),
        ]
        save_cache(tmp_path, reports)
        loaded = load_cache(tmp_path)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["status"] == "FRESH"
        assert loaded[1]["changed_files"] == ["src/models/user.py"]

    def test_cache_valid_within_ttl(self, tmp_path):
        reports = [NoteReport(note_path="x.md", status=StalenessStatus.FRESH, message="ok")]
        save_cache(tmp_path, reports)
        assert is_cache_valid(tmp_path, ttl=600) is True

    def test_cache_expired(self, tmp_path):
        cache_file = tmp_path / ".staleness_cache"
        data = {"timestamp": time.time() - 700, "reports": []}
        cache_file.write_text(json.dumps(data))
        assert is_cache_valid(tmp_path, ttl=600) is False

    def test_cache_missing(self, tmp_path):
        assert is_cache_valid(tmp_path) is False
        assert load_cache(tmp_path) is None

    def test_cache_corrupt(self, tmp_path):
        cache_file = tmp_path / ".staleness_cache"
        cache_file.write_text("not json{{{")
        assert is_cache_valid(tmp_path) is False
        assert load_cache(tmp_path) is None


class TestAllRepos:
    def test_find_valid_clone(self, tmp_path):
        clone = tmp_path / "my-clone"
        clone.mkdir()
        (clone / ".git").mkdir()
        repo_paths_file = tmp_path / ".repo_paths"
        repo_paths_file.write_text(f"{clone}\n")

        with patch("scripts.repo_id.get_repo_id", return_value="org--repo"):
            from scripts.staleness import _find_valid_clone
            result = _find_valid_clone(repo_paths_file, "org--repo")
        assert result == clone

    def test_find_valid_clone_prunes_invalid(self, tmp_path):
        clone = tmp_path / "valid-clone"
        clone.mkdir()
        (clone / ".git").mkdir()
        repo_paths_file = tmp_path / ".repo_paths"
        repo_paths_file.write_text(f"/nonexistent/path\n{clone}\n")

        with patch("scripts.repo_id.get_repo_id", return_value="org--repo"):
            from scripts.staleness import _find_valid_clone
            result = _find_valid_clone(repo_paths_file, "org--repo")
        assert result == clone
        lines = repo_paths_file.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_find_valid_clone_no_file(self, tmp_path):
        from scripts.staleness import _find_valid_clone
        result = _find_valid_clone(tmp_path / ".repo_paths", "org--repo")
        assert result is None

    def test_check_all_repos_skips_dotfiles(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "notes").mkdir()
        with patch("scripts.staleness._find_valid_clone", return_value=None):
            results = check_all_repos(tmp_path)
        assert ".hidden" not in results

    def test_check_all_repos_with_valid_repo(self, tmp_path):
        repo_dir = tmp_path / "org--repo"
        repo_dir.mkdir()
        notes_dir = repo_dir / "notes"
        notes_dir.mkdir()
        (notes_dir / "01-api.md").write_text("# No tracking\n")
        (repo_dir / ".repo_paths").write_text("/some/clone\n")
        clone = tmp_path / "clone"
        clone.mkdir()

        with patch("scripts.staleness._find_valid_clone", return_value=clone):
            results = check_all_repos(tmp_path)
        assert "org--repo" in results
        assert len(results["org--repo"]) == 1
        assert results["org--repo"][0].status == StalenessStatus.NO_TRACKING


class TestMarkdownReport:
    def test_generates_markdown_with_frontmatter(self):
        from scripts.staleness import generate_staleness_report, NoteReport, StalenessStatus
        reports = [
            NoteReport("notes/auth/index.md", StalenessStatus.STALE, ["src/auth.py"], "abc1234", "1 file changed"),
            NoteReport("notes/api/index.md", StalenessStatus.FRESH, [], "def5678", "0 files changed"),
        ]
        output = generate_staleness_report(reports)
        assert output.startswith("---")
        assert "staleness_check" in output
        assert "STALE" in output
        assert "FRESH" in output
        assert "auth/index.md" in output

    def test_markdown_report_dataview_compatible(self):
        from scripts.staleness import generate_staleness_report, NoteReport, StalenessStatus
        reports = [
            NoteReport("notes/overview.md", StalenessStatus.NO_TRACKING, [], None, "no tracking"),
        ]
        output = generate_staleness_report(reports)
        assert "| Note |" in output
        assert "NO_TRACKING" in output

    def test_write_staleness_report_creates_file(self, tmp_path):
        from scripts.staleness import write_staleness_report, NoteReport, StalenessStatus
        reports = [
            NoteReport("notes/test.md", StalenessStatus.FRESH, [], "abc", "ok"),
        ]
        result = write_staleness_report(tmp_path, reports)
        assert result.exists()
        assert result == tmp_path / "meta" / "staleness-report.md"
        content = result.read_text()
        assert "FRESH" in content

    def test_changed_files_truncated_at_5(self):
        from scripts.staleness import generate_staleness_report, NoteReport, StalenessStatus
        reports = [
            NoteReport("notes/big.md", StalenessStatus.STALE,
                       ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py", "g.py"],
                       "abc", "7 files"),
        ]
        output = generate_staleness_report(reports)
        assert "+2 more" in output


class TestFindValidCloneFromList:
    def test_returns_none_for_empty_list(self):
        from scripts.staleness import _find_valid_clone_from_list
        result = _find_valid_clone_from_list([], "some-repo")
        assert result is None

    def test_returns_none_for_nonexistent_paths(self):
        from scripts.staleness import _find_valid_clone_from_list
        result = _find_valid_clone_from_list(["/nonexistent/path"], "some-repo")
        assert result is None


class TestFormatReport:
    def test_format_mixed_report(self):
        reports = [
            NoteReport(note_path="/notes/01-api.md", status=StalenessStatus.FRESH, message="0 files changed"),
            NoteReport(note_path="/notes/02-models/index.md", status=StalenessStatus.STALE,
                       changed_files=["src/models/user.py", "src/models/auth.py"],
                       commit="abc1234", message="2 files changed since abc1234"),
            NoteReport(note_path="/notes/03-config.md", status=StalenessStatus.NO_TRACKING,
                       message="no git_tracked_paths in frontmatter"),
        ]
        output = format_report(reports)
        assert "FRESH: 01-api.md" in output
        assert "STALE: index.md (2 files changed since abc1234)" in output
        assert "  - src/models/user.py" in output
        assert "NO_TRACKING: 03-config.md" in output
