"""Tests for code_review.py deterministic helpers."""

import json
import subprocess
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from scripts.code_review import (
    _detect_forge, _parse_hostname, _check_cli_auth,
    _discover_stack_pr_chain, _discover_stack_git_topology,
    run_stack, MAX_STACK_DEPTH,
    run_loop_state,
    VALID_TRANSITIONS, parse_findings,
)


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


class TestRunForgeOutput:
    """Test run_forge returns correct JSON structure."""

    def test_detect_forge_output_keys(self):
        """Verify _detect_forge returns expected keys."""
        result = _detect_forge("https://github.com/org/repo.git")
        assert "forge" in result
        assert "cli" in result
        assert "hostname" in result

    def test_check_cli_auth_structure(self):
        """Verify _check_cli_auth returns expected keys."""
        result = _check_cli_auth("nonexistent-cli-tool-xyz")
        assert "cli_available" in result
        assert "cli_authenticated" in result
        assert "cli_usable" in result
        assert result["cli_available"] is False
        assert result["cli_usable"] is False


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


# ---------------------------------------------------------------------------
# Stack discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverStackGitTopology:
    """Test _discover_stack_git_topology()."""

    def test_cycle_detection_prevents_infinite_loop(self):
        """_discover_stack_git_topology with visited set should not loop."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _discover_stack_git_topology("fake-branch", tmpdir, set(), 0, 20)
            assert result == []  # No git repo, no children

    def test_depth_cap_respected(self):
        """Depth cap of 0 should return empty immediately."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _discover_stack_git_topology("fake", tmpdir, set(), 0, 0)
            assert result == []

    def test_already_visited_returns_empty(self):
        """If base_branch is already in visited, return empty."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            visited = {"my-branch"}
            result = _discover_stack_git_topology("my-branch", tmpdir, visited, 0, 20)
            assert result == []

    def test_refs_parameter_avoids_refetch(self):
        """When refs are passed, git for-each-ref should NOT be called (IQ-19)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo so rev-parse works
            subprocess.run(["git", "init", tmpdir], capture_output=True)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "init"],
                capture_output=True, cwd=tmpdir,
            )
            # Pass empty refs list -- function should not try to fetch refs itself
            result = _discover_stack_git_topology(
                "main", tmpdir, set(), 0, 20, refs=[]
            )
            # No candidates in empty refs, so result is empty
            assert result == []

    def test_accepts_refs_parameter(self):
        """Signature accepts refs parameter (IQ-19)."""
        import tempfile, inspect
        sig = inspect.signature(_discover_stack_git_topology)
        assert "refs" in sig.parameters


class TestDiscoverStackPrChain:
    """Test _discover_stack_pr_chain()."""

    def test_cycle_detection(self):
        """If base_branch is already visited, return empty."""
        visited = {"feature-a"}
        warnings = []
        result = _discover_stack_pr_chain(
            "feature-a", "github", "gh", visited, 0, 20, warnings,
        )
        assert result == []
        assert any("Cycle detected" in w for w in warnings)

    def test_depth_cap(self):
        """Exceeding max_depth returns empty with warning."""
        warnings = []
        result = _discover_stack_pr_chain(
            "feature-a", "github", "gh", set(), 20, 20, warnings,
        )
        assert result == []
        assert any("depth cap" in w.lower() for w in warnings)

    def test_unknown_forge_returns_empty(self):
        """Unknown forge returns empty without calling CLI."""
        warnings = []
        result = _discover_stack_pr_chain(
            "main", "bitbucket", "bb", set(), 0, 20, warnings,
        )
        assert result == []

    @patch("scripts.code_review.subprocess.run")
    @patch("scripts.code_review._repo_root", return_value="/fake")
    def test_github_pr_chain_discovery(self, mock_root, mock_run):
        """Test GitHub PR chain discovery with mocked gh output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"number": 42, "headRefName": "feature-b"},
                {"number": 43, "headRefName": "feature-c"},
            ]),
            stderr="",
        )
        warnings = []
        result = _discover_stack_pr_chain(
            "feature-a", "github", "gh", set(), 0, 20, warnings,
        )
        # feature-b and feature-c are children of feature-a
        branches = [r["branch"] for r in result]
        assert "feature-b" in branches
        assert "feature-c" in branches

    @patch("scripts.code_review.subprocess.run")
    @patch("scripts.code_review._repo_root", return_value="/fake")
    def test_gitlab_uses_output_json_not_F(self, mock_root, mock_run):
        """Verify glab commands use --output json, not -F json (IQ-15)."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="[]", stderr=""
        )
        warnings = []
        _discover_stack_pr_chain(
            "main", "gitlab", "glab", set(), 0, 20, warnings,
        )
        call_args = mock_run.call_args[0][0]
        assert "--output" in call_args
        assert "json" in call_args
        assert "-F" not in call_args

    @patch("scripts.code_review.subprocess.run")
    @patch("scripts.code_review._repo_root", return_value="/fake")
    def test_cli_failure_returns_empty_with_warning(self, mock_root, mock_run):
        """CLI failure should return empty and add a warning."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="auth required"
        )
        warnings = []
        result = _discover_stack_pr_chain(
            "main", "github", "gh", set(), 0, 20, warnings,
        )
        assert result == []
        assert any("CLI command failed" in w for w in warnings)


class TestRunStack:
    """Test run_stack() entry point."""

    @patch("scripts.code_review._check_cli_auth")
    @patch("scripts.code_review._detect_forge")
    @patch("scripts.code_review._git")
    def test_run_stack_no_forge_git_topology(self, mock_git, mock_forge, mock_auth, capsys):
        """When forge is unknown, falls back to git topology."""
        mock_forge.return_value = {"forge": "unknown", "cli": None, "hostname": ""}
        # _git calls: remote get-url, for-each-ref (branch count), for-each-ref (refs)
        mock_git.return_value = MagicMock(returncode=1, stdout="", stderr="")

        args = MagicMock()
        args.base = "feature-x"

        ret = run_stack(args)
        assert ret == 0
        output = json.loads(capsys.readouterr().out)
        assert output["method"] == "git_topology"
        assert output["base"] == "feature-x"
        assert len(output["stack"]) >= 1  # at least the base entry

    @patch("scripts.code_review._check_cli_auth")
    @patch("scripts.code_review._detect_forge")
    @patch("scripts.code_review._git")
    @patch("scripts.code_review.subprocess.run")
    @patch("scripts.code_review._repo_root", return_value="/fake")
    def test_run_stack_visited_not_preseeded(self, mock_root, mock_subproc, mock_git, mock_forge, mock_auth, capsys):
        """IQ-2/IQ-3: visited must NOT be pre-seeded with base_branch."""
        mock_forge.return_value = {"forge": "github", "cli": "gh", "hostname": "github.com"}
        mock_auth.return_value = {"cli_available": True, "cli_authenticated": True, "cli_usable": True}
        # _git for remote get-url
        mock_git.return_value = MagicMock(returncode=0, stdout="https://github.com/org/repo.git\n", stderr="")

        # subprocess.run for gh pr list (base PR lookup + children discovery)
        # First call: find base PR, second call: discover children of feature-a
        mock_subproc.side_effect = [
            # Base PR lookup
            MagicMock(returncode=0, stdout=json.dumps([{"number": 10, "baseRefName": "main"}]), stderr=""),
            # Children discovery for feature-a -- returns one child
            MagicMock(returncode=0, stdout=json.dumps([{"number": 11, "headRefName": "feature-b"}]), stderr=""),
            # Children discovery for feature-b -- returns empty
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]

        args = MagicMock()
        args.base = "feature-a"

        ret = run_stack(args)
        assert ret == 0
        output = json.loads(capsys.readouterr().out)
        # Should have found the child (feature-b) -- proves visited wasn't pre-seeded
        branches = [e["branch"] for e in output["stack"]]
        assert "feature-a" in branches
        assert "feature-b" in branches
        assert output["method"] == "pr_chain"

    @patch("scripts.code_review._check_cli_auth")
    @patch("scripts.code_review._detect_forge")
    @patch("scripts.code_review._git")
    @patch("scripts.code_review.subprocess.run")
    @patch("scripts.code_review._repo_root", return_value="/fake")
    def test_run_stack_multiple_children_warning(self, mock_root, mock_subproc, mock_git, mock_forge, mock_auth, capsys):
        """Multiple children of same base produce disambiguation warning."""
        mock_forge.return_value = {"forge": "github", "cli": "gh", "hostname": "github.com"}
        mock_auth.return_value = {"cli_available": True, "cli_authenticated": True, "cli_usable": True}
        mock_git.return_value = MagicMock(returncode=0, stdout="https://github.com/org/repo.git\n", stderr="")

        mock_subproc.side_effect = [
            # Base PR lookup
            MagicMock(returncode=0, stdout="[]", stderr=""),
            # Children: two children of main
            MagicMock(returncode=0, stdout=json.dumps([
                {"number": 11, "headRefName": "feature-b"},
                {"number": 12, "headRefName": "feature-c"},
            ]), stderr=""),
            # Children of feature-b
            MagicMock(returncode=0, stdout="[]", stderr=""),
            # Children of feature-c
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]

        args = MagicMock()
        args.base = "main"

        ret = run_stack(args)
        assert ret == 0
        output = json.loads(capsys.readouterr().out)
        assert any("multiple children" in w.lower() for w in output["warnings"])

    def test_max_stack_depth_constant(self):
        """MAX_STACK_DEPTH should be 20."""
        assert MAX_STACK_DEPTH == 20


# ---------------------------------------------------------------------------
# Loop state management tests
# ---------------------------------------------------------------------------


class TestLoopState:
    """Test loop state management (IQ-9: uses capsys)."""

    def _make_args(self, **kwargs):
        """Create a mock args namespace."""
        defaults = {
            "review_dir": "",
            "action": "read",
            "branches": None,
            "loop_args": None,
            "branch": None,
            "status": None,
            "cycles": None,
        }
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_write_and_read_state(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            branches_json = json.dumps([
                {"branch": "feat/a", "status": "pending"},
                {"branch": "feat/b", "status": "pending"},
            ])
            args_json = json.dumps({"max_cycles": 3, "auto_approve": True})

            # Write
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json, loop_args=args_json)
            rc = run_loop_state(args)
            assert rc == 0

            # Clear write output, then read
            capsys.readouterr()
            args = self._make_args(review_dir=tmpdir, action="read")
            rc = run_loop_state(args)
            assert rc == 0
            state = json.loads(capsys.readouterr().out)
            assert len(state["branches"]) == 2
            assert state["branches"][0]["status"] == "pending"

    def test_write_uses_utc_timestamp(self):
        """IQ-5: Timestamps must use datetime.now(timezone.utc), not date.today()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            branches_json = json.dumps([{"branch": "feat/a", "status": "pending"}])
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json)
            run_loop_state(args)

            state_path = Path(tmpdir) / "loop-state.json"
            state = json.loads(state_path.read_text())
            # Should NOT end with T00:00:00Z (the old date.today() pattern)
            assert not state["started"].endswith("T00:00:00Z")
            # Should contain a T separator and timezone info
            assert "T" in state["started"]

    def test_update_branch_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write initial
            branches_json = json.dumps([{"branch": "feat/a", "status": "pending"}])
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json, loop_args="{}")
            run_loop_state(args)

            # Update
            args = self._make_args(review_dir=tmpdir, action="update-branch", branch="feat/a", status="converged", cycles=2)
            rc = run_loop_state(args)
            assert rc == 0

            # Verify
            state_path = Path(tmpdir) / "loop-state.json"
            state = json.loads(state_path.read_text())
            assert state["branches"][0]["status"] == "converged"
            assert state["branches"][0]["cycles"] == 2

    def test_read_missing_state_returns_error(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = self._make_args(review_dir=tmpdir, action="read")
            rc = run_loop_state(args)
            assert rc == 1
            output = json.loads(capsys.readouterr().out)
            assert output["exists"] is False

    def test_read_corrupt_json_returns_error(self, capsys):
        """IQ-13: json.loads in read action must be wrapped in try/except."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "loop-state.json"
            state_path.write_text("{invalid json", encoding="utf-8")
            args = self._make_args(review_dir=tmpdir, action="read")
            rc = run_loop_state(args)
            assert rc == 1
            output = json.loads(capsys.readouterr().out)
            assert "Invalid JSON" in output["error"]

    def test_update_branch_corrupt_json_returns_error(self):
        """IQ-13: json.loads in update-branch action must be wrapped in try/except."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "loop-state.json"
            state_path.write_text("not valid json!", encoding="utf-8")
            args = self._make_args(review_dir=tmpdir, action="update-branch", branch="feat/a", status="converged")
            rc = run_loop_state(args)
            assert rc == 1

    def test_update_nonexistent_branch_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            branches_json = json.dumps([{"branch": "feat/a", "status": "pending"}])
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json)
            run_loop_state(args)

            args = self._make_args(review_dir=tmpdir, action="update-branch", branch="feat/nonexistent", status="converged")
            rc = run_loop_state(args)
            assert rc == 1

    def test_write_without_branches_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = self._make_args(review_dir=tmpdir, action="write")
            rc = run_loop_state(args)
            assert rc == 1

    def test_unknown_action_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = self._make_args(review_dir=tmpdir, action="delete")
            rc = run_loop_state(args)
            assert rc == 1

    def test_advances_branch_index_on_update(self):
        """After completing a branch, index should advance to next pending."""
        with tempfile.TemporaryDirectory() as tmpdir:
            branches_json = json.dumps([
                {"branch": "feat/a", "status": "pending"},
                {"branch": "feat/b", "status": "pending"},
            ])
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json)
            run_loop_state(args)

            # Complete first branch
            args = self._make_args(review_dir=tmpdir, action="update-branch", branch="feat/a", status="converged", cycles=1)
            run_loop_state(args)

            state_path = Path(tmpdir) / "loop-state.json"
            state = json.loads(state_path.read_text())
            assert state["current_branch_index"] == 1  # advanced to feat/b

    def test_write_without_loop_args(self):
        """Write should work when --loop-args is not provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            branches_json = json.dumps([{"branch": "feat/a", "status": "pending"}])
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json)
            rc = run_loop_state(args)
            assert rc == 0
            state_path = Path(tmpdir) / "loop-state.json"
            state = json.loads(state_path.read_text())
            assert state["args"] == {}
