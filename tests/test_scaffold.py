"""Tests for scaffold.py."""

import fcntl
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.scaffold import scaffold_repo


@pytest.fixture
def fake_env(tmp_path):
    repo_notes = tmp_path / ".claude" / "repo_notes"
    repo_notes.mkdir(parents=True)
    refs_dir = tmp_path / "references"
    refs_dir.mkdir()
    (refs_dir / "RULES-template.md").write_text("# Rules Template\nThese are the rules.\n")
    return tmp_path, repo_notes, refs_dir


class TestScaffoldCreatesStructure:
    def test_creates_all_content_dirs(self, fake_env):
        tmp_path, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        assert (repo_notes / "org--repo" / "notes").is_dir()
        assert (repo_notes / "org--repo" / "commits").is_dir()
        assert (repo_notes / "org--repo" / "research").is_dir()
        assert (repo_notes / "org--repo" / "projects").is_dir()

    def test_copies_rules_template(self, fake_env):
        _, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        rules = repo_notes / "org--repo" / "notes" / "RULES.md"
        assert rules.exists()
        assert "Rules Template" in rules.read_text()

    def test_creates_overview_skeleton(self, fake_env):
        _, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        overview = repo_notes / "org--repo" / "notes" / "00-overview.md"
        assert overview.exists()
        assert "git_tracked_paths" in overview.read_text()


class TestRepoPathsRegistry:
    def test_registers_clone_path(self, fake_env):
        _, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        lines = (repo_notes / "org--repo" / ".repo_paths").read_text().strip().splitlines()
        assert "/tmp/fake-clone" in lines

    def test_deduplicates(self, fake_env):
        _, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        lines = (repo_notes / "org--repo" / ".repo_paths").read_text().strip().splitlines()
        assert lines.count("/tmp/fake-clone") == 1

    def test_appends_new_path(self, fake_env):
        _, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/clone-1")
            scaffold_repo("org--repo", clone_path="/tmp/clone-2")
        lines = (repo_notes / "org--repo" / ".repo_paths").read_text().strip().splitlines()
        assert "/tmp/clone-1" in lines
        assert "/tmp/clone-2" in lines


class TestIdempotency:
    def test_does_not_overwrite_existing_rules(self, fake_env):
        _, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        rules = repo_notes / "org--repo" / "notes" / "RULES.md"
        rules.write_text("# Custom rules\n")
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        assert rules.read_text() == "# Custom rules\n"
