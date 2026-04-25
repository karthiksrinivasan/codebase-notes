"""Tests for scaffold.py — Obsidian vault scaffolding."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.scaffold import scaffold_vault, REFERENCES_DIR


@pytest.fixture
def refs_dir(tmp_path):
    """Create a temporary references directory with RULES-template.md."""
    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "RULES-template.md").write_text("# Rules Template\nThese are the rules.\n")
    return refs


class TestScaffoldCreatesDirectories:
    def test_creates_all_content_dirs(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        for d in ["notes", "research", "projects", "commits", "code-reviews",
                   "meta", "wiki", "_templates", ".obsidian", ".obsidian/snippets"]:
            assert (vault / d).is_dir(), f"Missing directory: {d}"


class TestVaultConfig:
    def test_creates_vault_config(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        config = json.loads((vault / ".vault-config.json").read_text())
        assert config["repo_id"] == "org--repo"
        assert config["repo_slug"] == "org-repo"
        assert "/tmp/clone" in config["clone_paths"]
        assert config["version"] == 3

    def test_adds_clone_path_to_existing_config(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone-1", references_dir=refs_dir)
        scaffold_vault(vault, "org--repo", "/tmp/clone-2", references_dir=refs_dir)
        config = json.loads((vault / ".vault-config.json").read_text())
        assert "/tmp/clone-1" in config["clone_paths"]
        assert "/tmp/clone-2" in config["clone_paths"]

    def test_deduplicates_clone_paths(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        config = json.loads((vault / ".vault-config.json").read_text())
        assert config["clone_paths"].count("/tmp/clone") == 1


class TestOverview:
    def test_creates_overview_md(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        overview = vault / "notes" / "overview.md"
        assert overview.exists()
        content = overview.read_text()
        assert "dataview" in content
        assert "git_tracked_paths" in content

    def test_does_not_overwrite_existing_overview(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        overview = vault / "notes" / "overview.md"
        overview.write_text("# Custom overview\n")
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        assert overview.read_text() == "# Custom overview\n"


class TestWikiFiles:
    def test_creates_hot_md(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        assert (vault / "wiki" / "hot.md").exists()

    def test_creates_log_md(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        assert (vault / "wiki" / "log.md").exists()


class TestObsidianConfig:
    def test_creates_app_json(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        app = json.loads((vault / ".obsidian" / "app.json").read_text())
        assert app["strictLineBreaks"] is True
        assert app["showFrontmatter"] is True
        assert app["livePreview"] is True
        assert app["readableLineLength"] is True

    def test_creates_core_plugins_json(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        plugins = json.loads((vault / ".obsidian" / "core-plugins.json").read_text())
        assert isinstance(plugins, list)
        assert "file-explorer" in plugins
        assert "global-search" in plugins
        assert "graph" in plugins
        assert "backlink" in plugins

    def test_creates_community_plugins_json(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        plugins = json.loads((vault / ".obsidian" / "community-plugins.json").read_text())
        assert "dataview" in plugins
        assert "obsidian-excalidraw-plugin" in plugins
        assert "templater-obsidian" in plugins

    def test_creates_graph_json(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        graph = json.loads((vault / ".obsidian" / "graph.json").read_text())
        assert "colorGroups" in graph

    def test_obsidian_configs_always_overwrite(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        # Overwrite app.json with garbage
        (vault / ".obsidian" / "app.json").write_text("{}")
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        app = json.loads((vault / ".obsidian" / "app.json").read_text())
        assert app["strictLineBreaks"] is True


class TestDashboard:
    def test_creates_dashboard_md(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        dashboard = vault / "meta" / "dashboard.md"
        assert dashboard.exists()
        assert "dataview" in dashboard.read_text()


class TestRules:
    def test_copies_rules_from_references(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        rules = vault / "RULES.md"
        assert rules.exists()
        assert "Rules Template" in rules.read_text()

    def test_does_not_overwrite_existing_rules(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        (vault / "RULES.md").write_text("# Custom rules\n")
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        assert (vault / "RULES.md").read_text() == "# Custom rules\n"

    def test_skips_rules_if_template_missing(self, tmp_path):
        refs = tmp_path / "empty-refs"
        refs.mkdir()
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs)
        assert not (vault / "RULES.md").exists()


class TestTemplates:
    def test_creates_note_template(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        note = vault / "_templates" / "note.md"
        assert note.exists()
        content = note.read_text()
        assert "{{date}}" in content
        assert "{{title}}" in content

    def test_creates_research_paper_template(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        paper = vault / "_templates" / "research-paper.md"
        assert paper.exists()
        content = paper.read_text()
        assert "{{date}}" in content
        assert "{{title}}" in content

    def test_does_not_overwrite_existing_templates(self, tmp_path, refs_dir):
        vault = tmp_path / "my-vault"
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        note = vault / "_templates" / "note.md"
        note.write_text("# My custom template\n")
        scaffold_vault(vault, "org--repo", "/tmp/clone", references_dir=refs_dir)
        assert note.read_text() == "# My custom template\n"
