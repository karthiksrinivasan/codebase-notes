"""Tests for repo_id resolution."""

import hashlib
from unittest.mock import patch, MagicMock
import subprocess

from scripts.repo_id import resolve_repo_id


def _mock_git_remote(url: str):
    result = MagicMock()
    result.stdout = url + "\n"
    result.returncode = 0
    return result


class TestSSHUrls:
    def test_github_ssh(self):
        with patch("subprocess.run", return_value=_mock_git_remote("git@github.com:anthropics/claude-code.git")):
            assert resolve_repo_id() == "anthropics--claude-code"

    def test_github_ssh_no_dotgit(self):
        with patch("subprocess.run", return_value=_mock_git_remote("git@github.com:anthropics/claude-code")):
            assert resolve_repo_id() == "anthropics--claude-code"

    def test_gitlab_nested_groups(self):
        with patch("subprocess.run", return_value=_mock_git_remote("git@gitlab.com:org/sub/repo.git")):
            assert resolve_repo_id() == "org--sub--repo"

    def test_deeply_nested(self):
        with patch("subprocess.run", return_value=_mock_git_remote("git@gitlab.com:org/group/subgroup/repo.git")):
            assert resolve_repo_id() == "org--group--subgroup--repo"


class TestHTTPSUrls:
    def test_github_https(self):
        with patch("subprocess.run", return_value=_mock_git_remote("https://github.com/org/repo.git")):
            assert resolve_repo_id() == "org--repo"

    def test_no_dotgit(self):
        with patch("subprocess.run", return_value=_mock_git_remote("https://github.com/org/repo")):
            assert resolve_repo_id() == "org--repo"

    def test_trailing_slash(self):
        with patch("subprocess.run", return_value=_mock_git_remote("https://github.com/org/repo/")):
            assert resolve_repo_id() == "org--repo"


class TestLocalFallback:
    def test_no_remote(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")), \
             patch("os.getcwd", return_value="/Users/dev/my-project"):
            result = resolve_repo_id()
            path_hash = hashlib.sha256("/Users/dev/my-project".encode()).hexdigest()[:8]
            assert result == f"local--my-project--{path_hash}"

    def test_cwd_override(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")):
            result = resolve_repo_id(cwd="/tmp/test-repo")
            path_hash = hashlib.sha256("/tmp/test-repo".encode()).hexdigest()[:8]
            assert result == f"local--test-repo--{path_hash}"


class TestEdgeCases:
    def test_strips_whitespace(self):
        with patch("subprocess.run", return_value=_mock_git_remote("  git@github.com:org/repo.git  ")):
            assert resolve_repo_id() == "org--repo"

    def test_ssh_with_port(self):
        with patch("subprocess.run", return_value=_mock_git_remote("ssh://git@github.com:22/org/repo.git")):
            assert resolve_repo_id() == "org--repo"
