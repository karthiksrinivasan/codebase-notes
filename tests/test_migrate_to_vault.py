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

    def test_png_to_excalidraw(self):
        result = convert_relative_link_to_wikilink("diagram", "./01-auth.png", {})
        assert result == "![[auth.excalidraw]]"

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
        assert "![[system.excalidraw]]" in result


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
