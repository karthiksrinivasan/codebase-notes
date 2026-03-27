"""Tests for code_review.py deterministic helpers."""

import pytest
from scripts.code_review import _detect_forge, _parse_hostname, VALID_TRANSITIONS, parse_findings


class TestParseHostname:
    """Test _parse_hostname() URL parsing (IQ-7)."""

    def test_ssh_url(self):
        assert _parse_hostname("git@github.com:org/repo.git") == "github.com"

    def test_https_url(self):
        assert _parse_hostname("https://github.com/org/repo.git") == "github.com"

    def test_ssh_scheme_url(self):
        """ssh:// scheme should be parsed via urlparse (IQ-1)."""
        assert _parse_hostname("ssh://git@gitlab.com/org/repo.git") == "gitlab.com"

    def test_ssh_scheme_with_port(self):
        assert _parse_hostname("ssh://git@gitlab.com:2222/org/repo.git") == "gitlab.com"

    def test_empty_url(self):
        assert _parse_hostname("") == ""

    def test_https_with_port(self):
        assert _parse_hostname("https://github.mycompany.com:8443/org/repo.git") == "github.mycompany.com"

    def test_ssh_self_hosted(self):
        assert _parse_hostname("git@gitlab.internal.corp:org/repo.git") == "gitlab.internal.corp"


class TestDetectForge:
    """Test _detect_forge() URL parsing."""

    def test_github_https(self):
        result = _detect_forge("https://github.com/org/repo.git")
        assert result["forge"] == "github"
        assert result["cli"] == "gh"
        assert result["hostname"] == "github.com"

    def test_github_ssh(self):
        result = _detect_forge("git@github.com:org/repo.git")
        assert result["forge"] == "github"
        assert result["cli"] == "gh"
        assert result["hostname"] == "github.com"

    def test_gitlab_https(self):
        result = _detect_forge("https://gitlab.com/org/repo.git")
        assert result["forge"] == "gitlab"
        assert result["cli"] == "glab"
        assert result["hostname"] == "gitlab.com"

    def test_gitlab_ssh(self):
        result = _detect_forge("git@gitlab.com:radical-ai/arc.git")
        assert result["forge"] == "gitlab"
        assert result["cli"] == "glab"
        assert result["hostname"] == "gitlab.com"

    def test_self_hosted_github(self):
        result = _detect_forge("https://github.mycompany.com/org/repo.git")
        assert result["forge"] == "github"
        assert result["cli"] == "gh"

    def test_self_hosted_gitlab(self):
        result = _detect_forge("https://gitlab.internal.corp/org/repo.git")
        assert result["forge"] == "gitlab"
        assert result["cli"] == "glab"

    def test_unknown_host(self):
        result = _detect_forge("https://bitbucket.org/org/repo.git")
        assert result["forge"] == "unknown"
        assert result["cli"] is None

    def test_ssh_no_scheme(self):
        result = _detect_forge("git@gitlab.radical-ai.com:radical-ai/arc.git")
        assert result["forge"] == "gitlab"

    def test_empty_url(self):
        result = _detect_forge("")
        assert result["forge"] == "unknown"

    def test_github_in_path_not_hostname(self):
        """github in path should NOT trigger github detection."""
        result = _detect_forge("https://bitbucket.org/org/github-migration.git")
        assert result["forge"] == "unknown"

    def test_ssh_scheme_gitlab(self):
        """ssh:// scheme URLs should work (IQ-1)."""
        result = _detect_forge("ssh://git@gitlab.com/org/repo.git")
        assert result["forge"] == "gitlab"
        assert result["cli"] == "glab"
        assert result["hostname"] == "gitlab.com"

    def test_unknown_host_with_gitlab_ci(self, tmp_path, monkeypatch):
        """Unknown host with .gitlab-ci.yml should detect as gitlab (Spec #15)."""
        # Create a .gitlab-ci.yml in the fake repo root
        (tmp_path / ".gitlab-ci.yml").write_text("stages: [build]")
        monkeypatch.setenv("REPO_ROOT", str(tmp_path))
        result = _detect_forge("https://git.mycompany.com/org/repo.git")
        assert result["forge"] == "gitlab"
        assert result["cli"] == "glab"

    def test_unknown_host_without_gitlab_ci(self, tmp_path, monkeypatch):
        """Unknown host without .gitlab-ci.yml stays unknown."""
        monkeypatch.setenv("REPO_ROOT", str(tmp_path))
        result = _detect_forge("https://git.mycompany.com/org/repo.git")
        assert result["forge"] == "unknown"
        assert result["cli"] is None


class TestValidTransitions:
    """Verify state transition matrix completeness."""

    def test_all_statuses_have_transitions(self):
        expected_statuses = {"new", "persists", "resolved", "missed", "regressed", "fixed", "deferred"}
        assert set(VALID_TRANSITIONS.keys()) == expected_statuses

    def test_new_transitions(self):
        assert VALID_TRANSITIONS["new"] == {"persists", "resolved"}

    def test_fixed_can_regress(self):
        assert "regressed" in VALID_TRANSITIONS["fixed"]

    def test_deferred_can_persist(self):
        assert "persists" in VALID_TRANSITIONS["deferred"]


class TestParseFindings:
    """Test finding parser against various formats."""

    def test_standard_finding(self):
        text = """## 1. Senior Systems Architect

### Findings

#### SA-1 (critical) — Missing error handling
**File:** src/config.py:45
**Status:** new
Description here.
"""
        findings = parse_findings(text)
        assert len(findings) == 1
        assert findings[0]["id"] == "SA-1"
        assert findings[0]["severity"] == "critical"
        assert findings[0]["status"] == "new"
        assert findings[0]["persona"] == "Senior Systems Architect"

    def test_multiple_findings(self):
        text = """## 1. Senior Systems Architect

### Findings

#### SA-1 (critical) — First
**File:** a.py:1
**Status:** new
Desc.

#### SA-2 (suggestion) — Second
**File:** b.py:2
**Status:** persists
Desc.

### Verdict
pass
"""
        findings = parse_findings(text)
        assert len(findings) == 2
        assert findings[0]["id"] == "SA-1"
        assert findings[1]["id"] == "SA-2"
        assert findings[1]["status"] == "persists"

    def test_finding_with_fix_line(self):
        text = """## 1. Senior Systems Architect

### Findings

#### SA-1 (critical) — Fixed issue
**File:** a.py:1
**Status:** fixed
**Fix:** Added error handling
Desc.
"""
        findings = parse_findings(text)
        assert findings[0]["fix"] == "Added error handling"
