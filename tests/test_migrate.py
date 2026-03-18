"""Tests for migrate.py — v1 to v2 notes migration."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestDetectV1Notes:
    """Test detection of v1 notes at known locations."""

    def test_detect_docs_notes(self, tmp_path):
        """Should detect v1 notes at docs/notes/ with 00-overview.md."""
        from scripts.migrate import detect_v1_notes

        notes_dir = tmp_path / "docs" / "notes"
        notes_dir.mkdir(parents=True)
        (notes_dir / "00-overview.md").write_text("# Overview")

        result = detect_v1_notes(tmp_path)
        assert result == notes_dir

    def test_detect_notes_dir(self, tmp_path):
        """Should detect v1 notes at notes/ with 00-overview.md."""
        from scripts.migrate import detect_v1_notes

        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        (notes_dir / "00-overview.md").write_text("# Overview")

        result = detect_v1_notes(tmp_path)
        assert result == notes_dir

    def test_detect_docs_knowledge(self, tmp_path):
        """Should detect v1 notes at docs/knowledge/ with 00-overview.md."""
        from scripts.migrate import detect_v1_notes

        notes_dir = tmp_path / "docs" / "knowledge"
        notes_dir.mkdir(parents=True)
        (notes_dir / "00-overview.md").write_text("# Overview")

        result = detect_v1_notes(tmp_path)
        assert result == notes_dir

    def test_detect_returns_none_when_no_notes(self, tmp_path):
        """Should return None if no v1 notes directories found."""
        from scripts.migrate import detect_v1_notes

        result = detect_v1_notes(tmp_path)
        assert result is None

    def test_detect_requires_overview_file(self, tmp_path):
        """Should not detect directory without 00-overview.md."""
        from scripts.migrate import detect_v1_notes

        notes_dir = tmp_path / "docs" / "notes"
        notes_dir.mkdir(parents=True)
        (notes_dir / "some-other-file.md").write_text("# Something")

        result = detect_v1_notes(tmp_path)
        assert result is None

    def test_detect_priority_order(self, tmp_path):
        """If multiple locations exist, should return first found (docs/notes preferred)."""
        from scripts.migrate import detect_v1_notes

        for d in ["docs/notes", "notes"]:
            p = tmp_path / d
            p.mkdir(parents=True, exist_ok=True)
            (p / "00-overview.md").write_text("# Overview")

        result = detect_v1_notes(tmp_path)
        assert result == tmp_path / "docs" / "notes"


class TestCopyFiles:
    """Test copying v1 notes to centralized location preserving structure."""

    def _create_v1_structure(self, tmp_path):
        """Helper: create a realistic v1 notes structure."""
        repo_root = tmp_path / "repo"
        notes_dir = repo_root / "docs" / "notes"

        # Create directory structure
        (notes_dir).mkdir(parents=True)
        (notes_dir / "01-api").mkdir()
        (notes_dir / "01-api" / "01-endpoints").mkdir()
        (notes_dir / "02-models").mkdir()

        # Create files
        (notes_dir / "00-overview.md").write_text(
            "---\nlast_updated: 2026-01-01\n---\n# Overview\n\n"
            "> **Navigation:** [API](./01-api/index.md) | [Models](./02-models/index.md)\n"
        )
        (notes_dir / "RULES.md").write_text("# Rules\n")
        (notes_dir / "01-api" / "index.md").write_text(
            "---\ngit_tracked_paths:\n  - path: src/api/\n    commit: abc1234\n---\n"
            "# API\n\n> **Navigation:** Up: [Overview](../00-overview.md)\n"
            "> **Sub-topics:** [Endpoints](./01-endpoints/index.md)\n\n"
            "See [models](../02-models/index.md) for data types.\n"
        )
        (notes_dir / "01-api" / "01-endpoints" / "index.md").write_text(
            "# Endpoints\n\n> **Navigation:** Up: [API](../index.md)\n"
        )
        (notes_dir / "01-api" / "01-endpoints" / "api-arch.excalidraw").write_text('{"elements": []}')
        (notes_dir / "01-api" / "01-endpoints" / "api-arch.png").write_bytes(b"\x89PNG fake")
        (notes_dir / "02-models" / "index.md").write_text(
            "# Models\n\n> **Navigation:** Up: [Overview](../00-overview.md)\n"
        )

        return repo_root, notes_dir

    def test_copy_preserves_directory_structure(self, tmp_path):
        """All directories should be recreated in the destination."""
        from scripts.migrate import copy_v1_notes

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        dest = tmp_path / "dest" / "notes"

        copy_v1_notes(notes_dir, dest)

        assert (dest / "01-api").is_dir()
        assert (dest / "01-api" / "01-endpoints").is_dir()
        assert (dest / "02-models").is_dir()

    def test_copy_includes_md_files(self, tmp_path):
        """All .md files should be copied."""
        from scripts.migrate import copy_v1_notes

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        dest = tmp_path / "dest" / "notes"

        copy_v1_notes(notes_dir, dest)

        assert (dest / "00-overview.md").is_file()
        assert (dest / "RULES.md").is_file()
        assert (dest / "01-api" / "index.md").is_file()
        assert (dest / "01-api" / "01-endpoints" / "index.md").is_file()
        assert (dest / "02-models" / "index.md").is_file()

    def test_copy_includes_excalidraw_and_png(self, tmp_path):
        """Excalidraw and PNG files should be copied."""
        from scripts.migrate import copy_v1_notes

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        dest = tmp_path / "dest" / "notes"

        copy_v1_notes(notes_dir, dest)

        assert (dest / "01-api" / "01-endpoints" / "api-arch.excalidraw").is_file()
        assert (dest / "01-api" / "01-endpoints" / "api-arch.png").is_file()

    def test_copy_preserves_frontmatter(self, tmp_path):
        """Frontmatter in copied files should be preserved exactly."""
        from scripts.migrate import copy_v1_notes

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        dest = tmp_path / "dest" / "notes"

        copy_v1_notes(notes_dir, dest)

        content = (dest / "01-api" / "index.md").read_text()
        assert "git_tracked_paths:" in content
        assert "commit: abc1234" in content

    def test_copy_skips_non_matching_extensions(self, tmp_path):
        """Files with unsupported extensions should not be copied."""
        from scripts.migrate import copy_v1_notes

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        (notes_dir / "random.txt").write_text("should not be copied")
        (notes_dir / "data.json").write_text("{}")
        dest = tmp_path / "dest" / "notes"

        copy_v1_notes(notes_dir, dest)

        assert not (dest / "random.txt").exists()
        assert not (dest / "data.json").exists()

    def test_does_not_delete_source(self, tmp_path):
        """Migration should NOT delete the original v1 directory."""
        from scripts.migrate import copy_v1_notes

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        dest = tmp_path / "dest" / "notes"

        copy_v1_notes(notes_dir, dest)

        assert notes_dir.exists()
        assert (notes_dir / "00-overview.md").is_file()

    def test_copy_returns_file_list(self, tmp_path):
        """Should return a list of all files that were copied."""
        from scripts.migrate import copy_v1_notes

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        dest = tmp_path / "dest" / "notes"

        copied = copy_v1_notes(notes_dir, dest)

        assert len(copied) >= 7  # 5 .md + 1 .excalidraw + 1 .png
        assert all(isinstance(f, Path) for f in copied)


class TestUpdateLinks:
    """Test updating internal relative links after migration."""

    def test_relative_links_within_notes_unchanged(self):
        """Links between notes (e.g., ../02-models/index.md) should stay the same."""
        from scripts.migrate import update_links_in_content

        content = (
            "# API\n\n"
            "See [models](../02-models/index.md) for data types.\n"
            "Check [endpoints](./01-endpoints/index.md).\n"
        )
        updated, broken = update_links_in_content(content, repo_root=Path("/repo"), old_notes_rel="docs/notes")
        assert "../02-models/index.md" in updated
        assert "./01-endpoints/index.md" in updated
        assert len(broken) == 0

    def test_repo_relative_links_get_updated(self):
        """Links pointing to repo-relative paths (e.g., ../../src/api/) should be flagged."""
        from scripts.migrate import update_links_in_content

        content = (
            "# API\n\n"
            "Implementation at [api source](../../src/api/routes.py).\n"
        )
        updated, broken = update_links_in_content(content, repo_root=Path("/repo"), old_notes_rel="docs/notes")
        # This link goes outside notes dir — should be reported as broken
        assert len(broken) == 1
        assert "../../src/api/routes.py" in broken[0]

    def test_absolute_links_reported_as_broken(self):
        """Absolute file paths in links should be reported."""
        from scripts.migrate import update_links_in_content

        content = "See [config](/home/user/repo/config.yaml) for details.\n"
        updated, broken = update_links_in_content(content, repo_root=Path("/repo"), old_notes_rel="docs/notes")
        assert len(broken) == 1

    def test_external_urls_unchanged(self):
        """HTTP(S) links should not be modified or reported."""
        from scripts.migrate import update_links_in_content

        content = "See [docs](https://example.com/docs) and [api](http://localhost:8080).\n"
        updated, broken = update_links_in_content(content, repo_root=Path("/repo"), old_notes_rel="docs/notes")
        assert "https://example.com/docs" in updated
        assert "http://localhost:8080" in updated
        assert len(broken) == 0

    def test_image_references_unchanged(self):
        """Image references to .png files within notes should be preserved."""
        from scripts.migrate import update_links_in_content

        content = "![Architecture](./api-arch.png)\n"
        updated, broken = update_links_in_content(content, repo_root=Path("/repo"), old_notes_rel="docs/notes")
        assert "![Architecture](./api-arch.png)" in updated
        assert len(broken) == 0

    def test_frontmatter_preserved_during_link_update(self):
        """YAML frontmatter should pass through untouched."""
        from scripts.migrate import update_links_in_content

        content = (
            "---\n"
            "git_tracked_paths:\n"
            "  - path: src/api/\n"
            "    commit: abc1234\n"
            "last_updated: 2026-01-01\n"
            "---\n"
            "# Title\n\n"
            "Link to [models](../02-models/index.md).\n"
        )
        updated, broken = update_links_in_content(content, repo_root=Path("/repo"), old_notes_rel="docs/notes")
        assert "git_tracked_paths:" in updated
        assert "commit: abc1234" in updated
        assert "last_updated: 2026-01-01" in updated

    def test_multiple_links_on_one_line(self):
        """Should handle multiple links on a single line."""
        from scripts.migrate import update_links_in_content

        content = "See [API](./01-api/index.md) and [Models](./02-models/index.md) and [source](../../src/main.py).\n"
        updated, broken = update_links_in_content(content, repo_root=Path("/repo"), old_notes_rel="docs/notes")
        assert "./01-api/index.md" in updated
        assert "./02-models/index.md" in updated
        assert len(broken) == 1  # ../../src/main.py escapes notes dir


class TestMigrateFullFlow:
    """Test the complete migrate command end-to-end."""

    def _create_v1_structure(self, tmp_path):
        """Helper: create a realistic v1 notes structure with varied content."""
        repo_root = tmp_path / "repo"
        notes_dir = repo_root / "docs" / "notes"

        (notes_dir).mkdir(parents=True)
        (notes_dir / "01-api").mkdir()

        (notes_dir / "00-overview.md").write_text(
            "---\nlast_updated: 2026-01-01\n---\n"
            "# Overview\n\nSee [API](./01-api/index.md)\n"
        )
        (notes_dir / "RULES.md").write_text("# Rules\n")
        (notes_dir / "01-api" / "index.md").write_text(
            "---\ngit_tracked_paths:\n  - path: src/api/\n    commit: abc1234\n---\n"
            "# API\n\n"
            "See [source](../../src/api/main.py) for implementation.\n"
            "See [models](../02-models/index.md).\n"
            "![arch](./api-arch.png)\n"
        )
        (notes_dir / "01-api" / "api-arch.excalidraw").write_text('{"elements": []}')
        (notes_dir / "01-api" / "api-arch.png").write_bytes(b"\x89PNG fake")

        return repo_root, notes_dir

    def test_migrate_copies_all_files(self, tmp_path):
        """Full migration should copy all eligible files."""
        from scripts.migrate import migrate

        repo_root, notes_dir = self._create_v1_structure(tmp_path)
        dest_base = tmp_path / "repo_notes" / "org--repo"
        dest_notes = dest_base / "notes"

        with patch("scripts.migrate.REPO_NOTES_BASE", tmp_path / "repo_notes"):
            result = migrate(
                from_path=notes_dir,
                repo_id="org--repo",
                repo_root=repo_root,
            )

        assert dest_notes.exists()
        assert (dest_notes / "00-overview.md").is_file()
        assert (dest_notes / "01-api" / "index.md").is_file()
        assert (dest_notes / "01-api" / "api-arch.excalidraw").is_file()
        assert (dest_notes / "01-api" / "api-arch.png").is_file()

    def test_migrate_reports_broken_links(self, tmp_path):
        """Migration result should include list of links that couldn't be updated."""
        from scripts.migrate import migrate

        repo_root, notes_dir = self._create_v1_structure(tmp_path)

        with patch("scripts.migrate.REPO_NOTES_BASE", tmp_path / "repo_notes"):
            result = migrate(
                from_path=notes_dir,
                repo_id="org--repo",
                repo_root=repo_root,
            )

        assert len(result["broken_links"]) > 0
        # The ../../src/api/main.py link should be reported
        broken_urls = [bl["url"] for bl in result["broken_links"]]
        assert "../../src/api/main.py" in broken_urls

    def test_migrate_preserves_frontmatter(self, tmp_path):
        """Frontmatter should be fully preserved in migrated files."""
        from scripts.migrate import migrate

        repo_root, notes_dir = self._create_v1_structure(tmp_path)

        with patch("scripts.migrate.REPO_NOTES_BASE", tmp_path / "repo_notes"):
            migrate(from_path=notes_dir, repo_id="org--repo", repo_root=repo_root)

        dest_notes = tmp_path / "repo_notes" / "org--repo" / "notes"
        content = (dest_notes / "01-api" / "index.md").read_text()
        assert "git_tracked_paths:" in content
        assert "commit: abc1234" in content

    def test_migrate_does_not_delete_source(self, tmp_path):
        """Original v1 directory must remain untouched."""
        from scripts.migrate import migrate

        repo_root, notes_dir = self._create_v1_structure(tmp_path)

        with patch("scripts.migrate.REPO_NOTES_BASE", tmp_path / "repo_notes"):
            migrate(from_path=notes_dir, repo_id="org--repo", repo_root=repo_root)

        assert notes_dir.exists()
        assert (notes_dir / "00-overview.md").is_file()
        assert (notes_dir / "01-api" / "index.md").is_file()

    def test_migrate_returns_summary(self, tmp_path):
        """Result dict should contain files_copied count and broken_links list."""
        from scripts.migrate import migrate

        repo_root, notes_dir = self._create_v1_structure(tmp_path)

        with patch("scripts.migrate.REPO_NOTES_BASE", tmp_path / "repo_notes"):
            result = migrate(from_path=notes_dir, repo_id="org--repo", repo_root=repo_root)

        assert "files_copied" in result
        assert result["files_copied"] >= 5
        assert "broken_links" in result
        assert "dest_path" in result

    def test_migrate_with_explicit_from_path(self, tmp_path):
        """Should work with an explicit --from path that's not auto-detected."""
        from scripts.migrate import migrate

        repo_root = tmp_path / "repo"
        custom_dir = repo_root / "custom" / "location"
        custom_dir.mkdir(parents=True)
        (custom_dir / "00-overview.md").write_text("# Overview\n")
        (custom_dir / "01-topic.md").write_text("# Topic\n")

        with patch("scripts.migrate.REPO_NOTES_BASE", tmp_path / "repo_notes"):
            result = migrate(
                from_path=custom_dir,
                repo_id="org--repo",
                repo_root=repo_root,
            )

        dest_notes = tmp_path / "repo_notes" / "org--repo" / "notes"
        assert (dest_notes / "00-overview.md").is_file()
        assert (dest_notes / "01-topic.md").is_file()

    def test_migrate_updates_links_in_md_files(self, tmp_path):
        """Markdown files should have their links processed (broken ones flagged)."""
        from scripts.migrate import migrate

        repo_root, notes_dir = self._create_v1_structure(tmp_path)

        with patch("scripts.migrate.REPO_NOTES_BASE", tmp_path / "repo_notes"):
            result = migrate(from_path=notes_dir, repo_id="org--repo", repo_root=repo_root)

        # Broken links should include file context
        for bl in result["broken_links"]:
            assert "file" in bl
            assert "url" in bl
