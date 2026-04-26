"""Tests for v2→v3 migration (repo_notes → Obsidian vault)."""

from pathlib import Path
from scripts.migrate import (
    strip_nn_prefix,
    convert_relative_link_to_wikilink,
    strip_nav_bars,
    build_rename_map,
    convert_links_in_content,
)


class TestStripNNPrefix:
    def test_strips_leading_digits_and_dash(self):
        assert strip_nn_prefix("01-auth") == "auth"

    def test_strips_double_digit_prefix(self):
        assert strip_nn_prefix("12-api-endpoints") == "api-endpoints"

    def test_no_prefix(self):
        assert strip_nn_prefix("auth") == "auth"

    def test_overview_special_case(self):
        assert strip_nn_prefix("00-overview") == "overview"

    def test_preserves_non_matching(self):
        assert strip_nn_prefix("index") == "index"
        assert strip_nn_prefix("RULES") == "RULES"


class TestConvertRelativeLinkToWikilink:
    def test_simple_sibling_link(self):
        result = convert_relative_link_to_wikilink("API Layer", "./02-api.md", {})
        assert result == "[[api|API Layer]]"

    def test_parent_index_link(self):
        result = convert_relative_link_to_wikilink("Parent", "../index.md", {})
        assert result == "[[index|Parent]]"

    def test_cross_folder_link(self):
        result = convert_relative_link_to_wikilink("Data", "../../03-data/index.md", {})
        assert result == "[[data/index|Data]]"

    def test_png_embed(self):
        result = convert_relative_link_to_wikilink("diagram", "./01-auth.png", {})
        assert result == "![[auth.png]]"

    def test_external_url_unchanged(self):
        result = convert_relative_link_to_wikilink("Google", "https://google.com", {})
        assert result is None

    def test_anchor_link_unchanged(self):
        result = convert_relative_link_to_wikilink("Section", "#heading", {})
        assert result is None

    def test_uses_rename_map(self):
        rename_map = {"02-api-endpoints.md": "api-endpoints.md"}
        result = convert_relative_link_to_wikilink("API", "./02-api-endpoints.md", rename_map)
        assert result == "[[api-endpoints|API]]"


class TestStripNavBars:
    def test_strips_navigation_line(self):
        content = "---\ntitle: Test\n---\n# Title\n\n> **Navigation:** Up: [[parent]]\n\nContent here."
        result = strip_nav_bars(content)
        assert "> **Navigation:**" not in result
        assert "Content here." in result

    def test_strips_subtopics_line(self):
        content = "# Title\n\n> **Sub-topics:** [[a]] | [[b]]\n\nContent."
        result = strip_nav_bars(content)
        assert "> **Sub-topics:**" not in result
        assert "Content." in result

    def test_case_insensitive(self):
        content = "> **navigation:** test\n> **sub-topics:** test\nContent."
        result = strip_nav_bars(content)
        assert "navigation" not in result.lower()

    def test_preserves_other_blockquotes(self):
        content = "> Normal quote\n> **Navigation:** nav\n> Another quote"
        result = strip_nav_bars(content)
        assert "> Normal quote" in result
        assert "> Another quote" in result


class TestConvertLinksInContent:
    def test_converts_markdown_links_to_wikilinks(self):
        content = "See [Auth System](./01-auth.md) for details."
        result = convert_links_in_content(content, {})
        assert "[[auth|Auth System]]" in result
        assert "[Auth System](./01-auth.md)" not in result

    def test_preserves_external_urls(self):
        content = "See [GitHub](https://github.com) for details."
        result = convert_links_in_content(content, {})
        assert "[GitHub](https://github.com)" in result

    def test_converts_image_links(self):
        content = "![arch](./01-system.png)"
        result = convert_links_in_content(content, {})
        assert "![[system.png]]" in result


class TestBuildRenameMap:
    def test_builds_map_for_prefixed_files(self, tmp_path):
        (tmp_path / "01-auth.md").write_text("test")
        (tmp_path / "02-api.md").write_text("test")
        (tmp_path / "index.md").write_text("test")
        result = build_rename_map(tmp_path)
        assert "01-auth.md" in result
        assert result["01-auth.md"] == "auth.md"
        assert "02-api.md" in result
        assert "index.md" not in result  # no prefix to strip


class TestMigrateToVault:
    def _make_v2_repo(self, tmp_path):
        """Create a realistic v2 repo_notes structure."""
        repo = tmp_path / "source"
        # notes/
        notes = repo / "notes"
        notes.mkdir(parents=True)
        (notes / "00-overview.md").write_text("---\ngit_tracked_paths: []\n---\n# Overview\n")
        auth = notes / "01-auth"
        auth.mkdir()
        (auth / "index.md").write_text("> **Navigation:** Up: [Overview](../00-overview.md)\n\n# Auth\n")
        (auth / "01-oauth.md").write_text("See [overview](../00-overview.md) and ![diagram](./01-oauth.png)\n")
        (auth / "01-oauth.excalidraw").write_text("{}")
        (auth / "01-oauth.png").write_text("fake png")
        # research/
        research = repo / "research"
        research.mkdir()
        (research / "index.md").write_text("# Research\n")
        topic = research / "01-ml"
        topic.mkdir()
        (topic / "01-transformers.md").write_text("# Transformers\n")
        # projects/
        projects = repo / "projects"
        projects.mkdir()
        proj = projects / "redesign"
        proj.mkdir()
        (proj / "index.md").write_text("# Redesign\n")
        # commits/
        commits = repo / "commits"
        commits.mkdir()
        author = commits / "john-doe"
        author.mkdir()
        (author / "auth.md").write_text("# Commits\n")
        # code-reviews/
        cr = repo / "code-reviews"
        cr.mkdir()
        pr = cr / "pr-42"
        pr.mkdir()
        (pr / "review.md").write_text("# Review\n")
        (pr / "context.md").write_text("# Context\n")
        return repo

    def test_migrates_all_directories(self, tmp_path, monkeypatch):
        from scripts.migrate import migrate_to_vault
        import scripts.vault
        monkeypatch.setattr(scripts.vault, "VAULTS_BASE", tmp_path / "vaults")

        source = self._make_v2_repo(tmp_path)
        from scripts.vault import VAULTS_BASE
        result = migrate_to_vault(source, "org--repo", "/tmp/clone", dry_run=False)
        vault = Path(result["vault_dir"])

        # notes migrated with prefix stripping
        assert (vault / "notes" / "overview.md").is_file()
        assert (vault / "notes" / "auth" / "index.md").is_file()
        assert (vault / "notes" / "auth" / "oauth.md").is_file()
        assert (vault / "notes" / "auth" / "oauth.excalidraw").is_file()
        assert not (vault / "notes" / "auth" / "oauth.png").exists()  # PNG skipped

        # research migrated
        assert (vault / "research" / "index.md").is_file()
        assert (vault / "research" / "ml" / "transformers.md").is_file()

        # projects migrated
        assert (vault / "projects" / "redesign" / "index.md").is_file()

        # commits migrated
        assert (vault / "commits" / "john-doe" / "auth.md").is_file()

        # code-reviews migrated
        assert (vault / "code-reviews" / "pr-42" / "review.md").is_file()
        assert (vault / "code-reviews" / "pr-42" / "context.md").is_file()

    def test_converts_links_in_migrated_files(self, tmp_path, monkeypatch):
        from scripts.migrate import migrate_to_vault
        import scripts.vault
        monkeypatch.setattr(scripts.vault, "VAULTS_BASE", tmp_path / "vaults")

        source = self._make_v2_repo(tmp_path)
        result = migrate_to_vault(source, "org--repo", "/tmp/clone")
        vault = Path(result["vault_dir"])

        oauth = (vault / "notes" / "auth" / "oauth.md").read_text()
        assert "[[overview" in oauth
        assert "![[oauth.png]]" in oauth
        assert "(./01-oauth.png)" not in oauth  # old relative path gone

    def test_strips_nav_bars_in_migrated_files(self, tmp_path, monkeypatch):
        from scripts.migrate import migrate_to_vault
        import scripts.vault
        monkeypatch.setattr(scripts.vault, "VAULTS_BASE", tmp_path / "vaults")

        source = self._make_v2_repo(tmp_path)
        result = migrate_to_vault(source, "org--repo", "/tmp/clone")
        vault = Path(result["vault_dir"])

        auth_index = (vault / "notes" / "auth" / "index.md").read_text()
        assert "> **Navigation:**" not in auth_index

    def test_dry_run_counts_all_directories(self, tmp_path, monkeypatch):
        from scripts.migrate import migrate_to_vault
        import scripts.vault
        monkeypatch.setattr(scripts.vault, "VAULTS_BASE", tmp_path / "vaults")

        source = self._make_v2_repo(tmp_path)
        result = migrate_to_vault(source, "org--repo", "/tmp/clone", dry_run=True)
        assert result["dry_run"] is True
        assert result["files_copied"] >= 8  # all .md + .excalidraw across dirs
        assert result["files_skipped"] >= 1  # the .png
