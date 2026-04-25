"""Tests for vault resolution and management."""

import json
from pathlib import Path

from scripts.vault import repo_id_to_slug, resolve_vault, get_vault_dir, list_vaults, VAULTS_BASE


class TestRepoIdToSlug:
    def test_remote_repo_id(self):
        assert repo_id_to_slug("anthropics--claude-code") == "anthropics-claude-code"

    def test_nested_groups(self):
        assert repo_id_to_slug("gitlab--org--team--repo") == "gitlab-org-team-repo"

    def test_local_repo_id(self):
        assert repo_id_to_slug("local--myrepo--abc12345") == "local-myrepo-abc12345"

    def test_single_component(self):
        assert repo_id_to_slug("simple-repo") == "simple-repo"


class TestGetVaultDir:
    def test_returns_path_under_vaults_base(self):
        result = get_vault_dir("anthropics--claude-code")
        assert result == VAULTS_BASE / "anthropics-claude-code"


class TestResolveVault:
    def test_finds_existing_vault(self, tmp_path):
        vault_dir = tmp_path / "anthropics-claude-code"
        vault_dir.mkdir()
        config = {
            "repo_id": "anthropics--claude-code",
            "repo_slug": "anthropics-claude-code",
            "repo_root": "/tmp/repo",
            "clone_paths": ["/tmp/repo"],
            "created": "2026-04-25",
            "version": 3,
        }
        (vault_dir / ".vault-config.json").write_text(json.dumps(config))
        result = resolve_vault("anthropics--claude-code", vaults_base=tmp_path)
        assert result == vault_dir

    def test_returns_none_for_missing_vault(self, tmp_path):
        result = resolve_vault("nonexistent--repo", vaults_base=tmp_path)
        assert result is None

    def test_returns_none_for_missing_config(self, tmp_path):
        vault_dir = tmp_path / "some-repo"
        vault_dir.mkdir()
        result = resolve_vault("some--repo", vaults_base=tmp_path)
        assert result is None


class TestListVaults:
    def test_lists_vaults_with_configs(self, tmp_path):
        for name in ["repo-a", "repo-b"]:
            d = tmp_path / name
            d.mkdir()
            config = {"repo_id": name, "repo_slug": name, "version": 3}
            (d / ".vault-config.json").write_text(json.dumps(config))
        (tmp_path / "not-a-vault").mkdir()

        result = list_vaults(vaults_base=tmp_path)
        assert len(result) == 2
        slugs = {v["repo_slug"] for v in result}
        assert slugs == {"repo-a", "repo-b"}

    def test_empty_vaults_dir(self, tmp_path):
        result = list_vaults(vaults_base=tmp_path)
        assert result == []

    def test_nonexistent_vaults_dir(self, tmp_path):
        result = list_vaults(vaults_base=tmp_path / "nope")
        assert result == []
