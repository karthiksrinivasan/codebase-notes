# Review-Fix Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `loop` subcommand to the code-review skill that automates review→fix→update cycles with stacked branch discovery, resume capability, and auto-approve mode.

**Architecture:** Three new script functions (`_detect_forge`, `run_forge`, `run_stack`, `run_loop_state`) handle deterministic forge detection, stack discovery, and state management. The `run_preflight` function is refactored to share `_detect_forge`. The SKILL.md orchestrator gets a `loop` subcommand section (~80 lines) that calls these scripts and delegates to existing `new`/`update`/`fix` flows.

**Tech Stack:** Python (script functions in `code_review.py`), Bash (git, gh/glab CLI), Markdown (SKILL.md updates)

---

## Plan Review Fixes

Issues found during multi-persona plan review (2 critical, 3 high, 8 medium, 4 low from Implementation Quality; 3 fails + 2 minor from Spec Compliance):

**CRITICAL — implementers MUST apply these deviations from the code below:**

1. **IQ-2/IQ-3: visited set bug** — `run_stack()` pre-seeds `visited={base_branch}` then calls discovery functions that check `if base_branch in visited: return []`. This kills all discovery. **Fix:** Do NOT pre-seed visited. Pass `visited=set()` to both `_discover_stack_pr_chain` and `_discover_stack_git_topology`. The functions add each branch to visited as they process it — no pre-seeding needed.

2. **IQ-15: glab `-F json` wrong** — The plan uses `-F json` for glab. The correct flag is `--output json` (matching existing `run_preflight` code at line 328). **Fix:** Replace ALL occurrences of `-F json` with `--output json` in glab commands.

3. **IQ-1: `_parse_hostname` fails on `ssh://` URLs** — Add explicit `ssh://` scheme handling before the `git@` check: `if url.startswith("ssh://"):` route to `urlparse`.

4. **IQ-4: Move `urllib.parse` import to top of file** — Add `from urllib.parse import urlparse` to the module-level imports.

5. **IQ-5: Use `datetime.now(timezone.utc)` for timestamps** — Change `from datetime import date` to `from datetime import date, datetime, timezone`. Use `datetime.now(timezone.utc).isoformat()` in `run_loop_state`.

6. **IQ-19: Fetch refs once, pass as parameter** — `_discover_stack_git_topology` should accept a `refs: list[tuple[str, str]]` parameter. `run_stack` fetches refs once via `git for-each-ref` and passes the list.

7. **IQ-10: Rename `--args` to `--loop-args`** — Avoids shadowing the function's `args` parameter.

8. **IQ-9: Use `capsys` fixture** — Replace manual `sys.stdout` capture in tests with pytest's `capsys`.

9. **IQ-13: Wrap `json.loads` in try/except** — In `run_loop_state` read and update-branch actions.

**Spec compliance fixes for Task 6 (SKILL.md):**

10. **Spec #7: Add "fix failed" exit condition** — After running fix, check if any changes were produced. If `git diff --stat` is empty, log "nothing to fix", exit cycle.

11. **Spec #10: Add granular progress protocol** — Include per-persona, per-cluster, per-cycle progress announcements in the SKILL.md loop section.

12. **Spec #12: Specify dry-run output format** — Include the 5-column table (Branch, Review Exists, Critical, Suggestions, Est. Cycles) and "Estimated total cycles" footer.

13. **Spec #8 minor: Add `git fetch` before rebase** — `git fetch origin <branch_N>` before `git rebase`.

14. **Spec #15 minor: Add `.gitlab-ci.yml` check** — In `_detect_forge`, if hostname is unknown, check if `.gitlab-ci.yml` exists in repo root.

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `scripts/code_review.py` | Add `_detect_forge()`, `run_forge()`, `run_stack()`, `run_loop_state()`; refactor `run_preflight()` |
| Modify | `scripts/__main__.py` | Register `review-forge`, `review-stack`, `review-loop-state` commands |
| Create | `tests/test_code_review.py` | Tests for `_detect_forge`, `parse_findings`, `VALID_TRANSITIONS`, forge URL parsing, stack cycle detection |
| Modify | `skills/code-review/SKILL.md` | Add `loop` subcommand, update subcommands table, update Step 0 forge detection |

---

### Task 1: Add `_detect_forge()` shared function with tests

**Files:**
- Modify: `scripts/code_review.py` (add function near line 60, before `_repo_root`)
- Create: `tests/test_code_review.py`

This function is the foundation — used by `run_forge`, `run_stack`, and `run_preflight`. Build it test-first.

- [ ] **Step 1: Write the test file with forge detection tests**

Create `tests/test_code_review.py`:

```python
"""Tests for code_review.py deterministic helpers."""

import pytest
from scripts.code_review import _detect_forge, VALID_TRANSITIONS, parse_findings


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run pytest tests/test_code_review.py -v
```

Expected: FAIL — `_detect_forge` not yet importable (it doesn't exist).

- [ ] **Step 3: Implement `_detect_forge()`**

In `scripts/code_review.py`, add after line 58 (after `PERSONA_SECTION_RE`), before the git helpers section:

```python
# ---------------------------------------------------------------------------
# Forge detection (shared by run_forge and run_preflight)
# ---------------------------------------------------------------------------

def _parse_hostname(url: str) -> str:
    """Extract hostname from a git remote URL (SSH or HTTPS)."""
    if not url:
        return ""
    # SSH: git@host:org/repo.git
    if url.startswith("git@") or (not url.startswith("http") and ":" in url):
        # git@gitlab.com:org/repo.git -> gitlab.com
        at_idx = url.find("@")
        colon_idx = url.find(":", at_idx + 1)
        if at_idx >= 0 and colon_idx > at_idx:
            return url[at_idx + 1 : colon_idx].lower()
    # HTTPS: https://host/org/repo.git
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname:
            return parsed.hostname.lower()
    except Exception:
        pass
    return ""


def _detect_forge(remote_url: str) -> dict:
    """Detect forge type from git remote URL. Handles SSH, HTTPS, self-hosted.

    Returns dict with: forge, cli, hostname.
    Does NOT check CLI availability — that's done by the caller.
    """
    hostname = _parse_hostname(remote_url)

    # Match hostname (suffix first for exactness, then contains for self-hosted)
    forge = "unknown"
    cli = None

    if hostname.endswith("github.com"):
        forge, cli = "github", "gh"
    elif hostname.endswith("gitlab.com"):
        forge, cli = "gitlab", "glab"
    elif "github" in hostname:
        forge, cli = "github", "gh"
    elif "gitlab" in hostname:
        forge, cli = "gitlab", "glab"

    return {"forge": forge, "cli": cli, "hostname": hostname}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run pytest tests/test_code_review.py -v
```

Expected: ALL PASS (the `parse_findings` and `VALID_TRANSITIONS` tests also pass since those functions already exist).

- [ ] **Step 5: Commit**

```bash
git add scripts/code_review.py tests/test_code_review.py
git commit -m "feat: add _detect_forge() with hostname parsing and tests"
```

---

### Task 2: Add `run_forge()` entry point and refactor `run_preflight()`

**Files:**
- Modify: `scripts/code_review.py` (add `run_forge`, refactor `run_preflight`)
- Modify: `tests/test_code_review.py` (add integration-style test)

- [ ] **Step 1: Add test for `run_forge` output structure**

Append to `tests/test_code_review.py`:

```python
class TestRunForgeOutput:
    """Test run_forge returns correct JSON structure."""

    def test_detect_forge_output_keys(self):
        """Verify _detect_forge returns expected keys."""
        result = _detect_forge("https://github.com/org/repo.git")
        assert "forge" in result
        assert "cli" in result
        assert "hostname" in result
```

- [ ] **Step 2: Implement `run_forge()`**

Add to `scripts/code_review.py` after `_detect_forge`:

```python
def _check_cli_auth(cli: str) -> dict:
    """Check if forge CLI is available and authenticated."""
    available = shutil.which(cli) is not None
    authenticated = False
    if available:
        try:
            r = subprocess.run(
                [cli, "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            authenticated = r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return {
        "cli_available": available,
        "cli_authenticated": authenticated,
        "cli_usable": available and authenticated,
    }


def run_forge(args) -> int:
    """Detect git forge from remote URL. Entry point for review-forge command."""
    remote_name = getattr(args, "remote", None) or "origin"
    r = _git("remote", "get-url", remote_name)
    if r.returncode != 0:
        print(json.dumps({"error": f"Could not get URL for remote '{remote_name}'"}))
        return 1

    remote_url = r.stdout.strip()
    result = _detect_forge(remote_url)
    result["remote_url"] = remote_url

    # Check CLI availability and auth
    if result["cli"]:
        auth_info = _check_cli_auth(result["cli"])
        result.update(auth_info)
    else:
        result.update({"cli_available": False, "cli_authenticated": False, "cli_usable": False})

    print(json.dumps(result, indent=2))
    return 0
```

- [ ] **Step 3: Refactor `run_preflight()` to use `_detect_forge()`**

In `run_preflight()`, find the forge detection block (around line 293-306) and replace:

```python
        # 6. Detect forge CLI — use shared _detect_forge()
        r_remote = _git("remote", "get-url", "origin")
        remote_url = r_remote.stdout.strip() if r_remote.returncode == 0 else ""
        forge_info = _detect_forge(remote_url)
        forge_cli = None
        if forge_info["cli"] and shutil.which(forge_info["cli"]):
            forge_cli = forge_info["cli"]
        result["forge_cli"] = forge_cli
```

This replaces the old inline `if "github" in remote_url` / `elif "gitlab" in remote_url` block.

- [ ] **Step 4: Run all tests**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run pytest tests/test_code_review.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/code_review.py tests/test_code_review.py
git commit -m "feat: add run_forge() entry point, refactor run_preflight() to use _detect_forge()"
```

---

### Task 3: Add `run_stack()` with cycle detection and tests

**Files:**
- Modify: `scripts/code_review.py` (add `run_stack`)
- Modify: `tests/test_code_review.py` (add stack discovery tests)

- [ ] **Step 1: Write stack discovery tests**

Append to `tests/test_code_review.py`:

```python
from scripts.code_review import _discover_stack_git_topology


class TestStackDiscovery:
    """Test stack discovery helpers."""

    def test_cycle_detection_prevents_infinite_loop(self):
        """_discover_stack_git_topology with visited set should not loop."""
        # We can't easily test the full function without a git repo,
        # but we can test the visited-set logic by mocking.
        # This test verifies the function signature and returns empty for non-git dirs.
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
```

- [ ] **Step 2: Implement `_discover_stack_pr_chain()` and `_discover_stack_git_topology()`**

Add to `scripts/code_review.py` after `run_forge`:

```python
# ---------------------------------------------------------------------------
# Stack discovery
# ---------------------------------------------------------------------------

MAX_STACK_DEPTH = 20


def _discover_stack_pr_chain(
    base_branch: str,
    forge: str,
    cli: str,
    visited: set,
    depth: int,
    max_depth: int,
    warnings: list,
) -> list[dict]:
    """Discover child branches via PR/MR chain. Returns ordered list."""
    if depth >= max_depth:
        warnings.append(f"Stack depth cap ({max_depth}) reached at {base_branch}")
        return []
    if base_branch in visited:
        warnings.append(f"Cycle detected: {base_branch} already visited")
        return []
    visited.add(base_branch)

    children = []
    try:
        if forge == "github":
            r = subprocess.run(
                ["gh", "pr", "list", "--base", base_branch, "--json", "number,headRefName", "--state", "open"],
                capture_output=True, text=True, timeout=15, cwd=_repo_root(),
            )
        elif forge == "gitlab":
            r = subprocess.run(
                ["glab", "mr", "list", "--target-branch", base_branch, "-F", "json"],
                capture_output=True, text=True, timeout=15, cwd=_repo_root(),
            )
        else:
            return []

        if r.returncode != 0:
            warnings.append(f"CLI command failed for {base_branch}: {r.stderr.strip()[:100]}")
            return []

        items = json.loads(r.stdout)
        for item in items:
            if forge == "github":
                child_branch = item.get("headRefName", "")
                pr_num = item.get("number")
            else:
                child_branch = item.get("source_branch", "")
                pr_num = item.get("iid")
                state = item.get("state", "").lower()
                if state not in ("opened", "open"):
                    continue

            if child_branch and child_branch not in visited:
                entry = {"branch": child_branch, "pr": pr_num, "base": base_branch}
                children.append(entry)

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        warnings.append(f"Error discovering children of {base_branch}: {e}")
        return []

    # Recurse into each child
    result = []
    for child in children:
        result.append(child)
        grandchildren = _discover_stack_pr_chain(
            child["branch"], forge, cli, visited, depth + 1, max_depth, warnings
        )
        result.extend(grandchildren)
    return result


def _discover_stack_git_topology(
    base_branch: str,
    repo_root: str,
    visited: set,
    depth: int,
    max_depth: int,
) -> list[dict]:
    """Discover child branches via git merge-base topology. Fallback when no forge CLI."""
    if depth >= max_depth or base_branch in visited:
        return []
    visited.add(base_branch)

    # Get base branch tip
    r_base = subprocess.run(
        ["git", "rev-parse", base_branch],
        capture_output=True, text=True, timeout=10, cwd=repo_root,
    )
    if r_base.returncode != 0:
        return []
    base_tip = r_base.stdout.strip()

    # Get all local branch tips in one call
    r_refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/"],
        capture_output=True, text=True, timeout=10, cwd=repo_root,
    )
    if r_refs.returncode != 0:
        return []

    candidates = []
    for line in r_refs.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        branch_name, tip = parts
        if branch_name == base_branch or branch_name in visited:
            continue
        # Check if base_tip is an ancestor of candidate
        r_anc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_tip, tip],
            capture_output=True, text=True, timeout=10, cwd=repo_root,
        )
        if r_anc.returncode == 0:
            candidates.append((branch_name, tip))

    # Filter to direct children: candidate is direct if no other candidate is ancestor of it
    direct_children = []
    for i, (name_i, tip_i) in enumerate(candidates):
        is_direct = True
        for j, (name_j, tip_j) in enumerate(candidates):
            if i == j:
                continue
            r_check = subprocess.run(
                ["git", "merge-base", "--is-ancestor", tip_j, tip_i],
                capture_output=True, text=True, timeout=10, cwd=repo_root,
            )
            if r_check.returncode == 0 and tip_j != tip_i:
                # name_j is between base and name_i — name_i is not direct
                is_direct = False
                break
        if is_direct:
            direct_children.append({"branch": name_i, "pr": None, "base": base_branch})

    # Recurse
    result = []
    for child in direct_children:
        result.append(child)
        grandchildren = _discover_stack_git_topology(
            child["branch"], repo_root, visited, depth + 1, max_depth
        )
        result.extend(grandchildren)
    return result


def run_stack(args) -> int:
    """Discover stacked branch chain from a base branch. Entry point for review-stack."""
    base_branch = args.base
    warnings: list[str] = []

    # Detect forge
    r = _git("remote", "get-url", "origin")
    remote_url = r.stdout.strip() if r.returncode == 0 else ""
    forge_info = _detect_forge(remote_url)

    # Check CLI usability
    cli_usable = False
    if forge_info["cli"]:
        auth = _check_cli_auth(forge_info["cli"])
        cli_usable = auth["cli_usable"]
        if auth["cli_available"] and not auth["cli_authenticated"]:
            warnings.append(f"{forge_info['cli']} is installed but not authenticated. Falling back to git topology.")

    stack = []
    method = "none"

    # Add base branch as first entry
    base_entry = {"branch": base_branch, "pr": None, "base": "main"}
    # Try to find the base branch's own PR
    if cli_usable and forge_info["forge"] != "unknown":
        try:
            if forge_info["forge"] == "github":
                r_pr = subprocess.run(
                    ["gh", "pr", "list", "--head", base_branch, "--json", "number,baseRefName", "--state", "open"],
                    capture_output=True, text=True, timeout=15, cwd=_repo_root(),
                )
            else:
                r_pr = subprocess.run(
                    ["glab", "mr", "list", "--source-branch", base_branch, "-F", "json"],
                    capture_output=True, text=True, timeout=15, cwd=_repo_root(),
                )
            if r_pr.returncode == 0:
                prs = json.loads(r_pr.stdout)
                if prs:
                    pr = prs[0]
                    base_entry["pr"] = pr.get("number") or pr.get("iid")
                    base_entry["base"] = pr.get("baseRefName") or pr.get("target_branch") or "main"
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

    stack.append(base_entry)

    # Discover children
    if cli_usable and forge_info["forge"] != "unknown":
        children = _discover_stack_pr_chain(
            base_branch, forge_info["forge"], forge_info["cli"],
            visited={base_branch}, depth=0, max_depth=MAX_STACK_DEPTH, warnings=warnings,
        )
        method = "pr_chain"
    else:
        # Git topology fallback
        ref_count_r = _git("for-each-ref", "--format=%(refname:short)", "refs/heads/")
        branch_count = len(ref_count_r.stdout.strip().split("\n")) if ref_count_r.returncode == 0 else 0
        if branch_count > 100:
            warnings.append(f"Repository has {branch_count} branches. Git topology fallback may be slow. Consider installing {forge_info['cli'] or 'gh/glab'}.")
        children = _discover_stack_git_topology(
            base_branch, _repo_root(), visited={base_branch}, depth=0, max_depth=MAX_STACK_DEPTH,
        )
        method = "git_topology"

    stack.extend(children)

    # Check for multiple children (disambiguation needed)
    seen_bases = {}
    for entry in stack[1:]:  # Skip the base itself
        parent = entry["base"]
        seen_bases.setdefault(parent, []).append(entry["branch"])
    for parent, kids in seen_bases.items():
        if len(kids) > 1:
            warnings.append(f"Branch {parent} has multiple children: {kids}. Orchestrator should disambiguate.")

    result = {
        "base": base_branch,
        "stack": stack,
        "method": method,
        "forge": forge_info["forge"],
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2))
    return 0
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run pytest tests/test_code_review.py -v
```

- [ ] **Step 4: Commit**

```bash
git add scripts/code_review.py tests/test_code_review.py
git commit -m "feat: add run_stack() with PR chain and git topology fallback"
```

---

### Task 4: Add `run_loop_state()` for loop state management

**Files:**
- Modify: `scripts/code_review.py` (add `run_loop_state`)
- Modify: `tests/test_code_review.py` (add loop state tests)

- [ ] **Step 1: Write loop state tests**

Append to `tests/test_code_review.py`:

```python
import tempfile
from scripts.code_review import run_loop_state


class TestLoopState:
    """Test loop state management."""

    def _make_args(self, **kwargs):
        """Create a mock args namespace."""
        from argparse import Namespace
        defaults = {
            "review_dir": "",
            "action": "read",
            "branches": None,
            "args": None,
            "branch": None,
            "status": None,
            "cycles": None,
        }
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_write_and_read_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            branches_json = json.dumps([
                {"branch": "feat/a", "status": "pending"},
                {"branch": "feat/b", "status": "pending"},
            ])
            args_json = json.dumps({"max_cycles": 3, "auto_approve": True})

            # Write
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json, args=args_json)
            rc = run_loop_state(args)
            assert rc == 0

            # Read
            import io, sys
            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            args = self._make_args(review_dir=tmpdir, action="read")
            rc = run_loop_state(args)
            sys.stdout = old_stdout
            assert rc == 0
            state = json.loads(captured.getvalue())
            assert len(state["branches"]) == 2
            assert state["branches"][0]["status"] == "pending"

    def test_update_branch_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write initial
            branches_json = json.dumps([{"branch": "feat/a", "status": "pending"}])
            args = self._make_args(review_dir=tmpdir, action="write", branches=branches_json, args="{}")
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
```

- [ ] **Step 2: Implement `run_loop_state()`**

Add to `scripts/code_review.py` after `run_stack`:

```python
# ---------------------------------------------------------------------------
# Loop state management
# ---------------------------------------------------------------------------

def run_loop_state(args) -> int:
    """Manage loop-state.json for review-fix loop. Entry point for review-loop-state."""
    review_dir = Path(args.review_dir)
    action = args.action
    state_path = review_dir / "loop-state.json"

    if action == "read":
        if not state_path.is_file():
            print(json.dumps({"error": "No loop-state.json found", "exists": False}))
            return 1
        state = json.loads(state_path.read_text(encoding="utf-8"))
        print(json.dumps(state, indent=2))
        return 0

    elif action == "write":
        branches_raw = getattr(args, "branches", None)
        args_raw = getattr(args, "args", None)
        if not branches_raw:
            print("error: --branches required for write action", file=sys.stderr)
            return 1
        branches = json.loads(branches_raw)
        loop_args = json.loads(args_raw) if args_raw else {}

        state = {
            "started": date.today().isoformat() + "T00:00:00Z",
            "branches": branches,
            "current_branch_index": 0,
            "current_cycle": 0,
            "args": loop_args,
        }
        review_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(json.dumps({"status": "written", "path": str(state_path)}))
        return 0

    elif action == "update-branch":
        branch_name = getattr(args, "branch", None)
        new_status = getattr(args, "status", None)
        cycles = getattr(args, "cycles", None)
        if not branch_name or not new_status:
            print("error: --branch and --status required for update-branch", file=sys.stderr)
            return 1
        if not state_path.is_file():
            print("error: No loop-state.json to update", file=sys.stderr)
            return 1

        state = json.loads(state_path.read_text(encoding="utf-8"))
        updated = False
        for entry in state["branches"]:
            if entry["branch"] == branch_name:
                entry["status"] = new_status
                if cycles is not None:
                    entry["cycles"] = cycles
                updated = True
                break

        if not updated:
            print(f"error: Branch {branch_name} not found in state", file=sys.stderr)
            return 1

        # Advance current_branch_index to next non-completed branch
        for i, entry in enumerate(state["branches"]):
            if entry["status"] in ("pending", "in-progress"):
                state["current_branch_index"] = i
                break
        else:
            state["current_branch_index"] = len(state["branches"])

        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(json.dumps({"status": "updated", "branch": branch_name}))
        return 0

    else:
        print(f"error: Unknown action '{action}'", file=sys.stderr)
        return 1
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run pytest tests/test_code_review.py -v
```

- [ ] **Step 4: Commit**

```bash
git add scripts/code_review.py tests/test_code_review.py
git commit -m "feat: add run_loop_state() for loop checkpoint management"
```

---

### Task 5: Register new commands in `__main__.py`

**Files:**
- Modify: `scripts/__main__.py`

- [ ] **Step 1: Add argument parsers for the 3 new commands**

In `scripts/__main__.py`, after the existing `review-frontmatter` parser registration (around line 110), add:

```python
    # review-forge
    forge_parser = subparsers.add_parser("review-forge", help="Detect git forge and CLI availability")
    forge_parser.add_argument("--remote", default="origin", help="Git remote name (default: origin)")

    # review-stack
    stack_parser = subparsers.add_parser("review-stack", help="Discover stacked branch chain from base")
    stack_parser.add_argument("--base", required=True, help="Base branch of the stack")

    # review-loop-state
    loop_state_parser = subparsers.add_parser("review-loop-state", help="Manage loop state file")
    loop_state_parser.add_argument("--review-dir", required=True, help="Code reviews directory path")
    loop_state_parser.add_argument("--action", required=True, choices=["read", "write", "update-branch"],
                                   help="Action to perform")
    loop_state_parser.add_argument("--branches", help="JSON branch list (for write action)")
    loop_state_parser.add_argument("--args", help="JSON loop arguments (for write action)")
    loop_state_parser.add_argument("--branch", help="Branch name (for update-branch action)")
    loop_state_parser.add_argument("--status", help="Branch status (for update-branch action)")
    loop_state_parser.add_argument("--cycles", type=int, help="Cycle count (for update-branch action)")
```

- [ ] **Step 2: Add to dispatch table and entry point routing**

In the `dispatch` dict, add:

```python
        "review-forge": "scripts.code_review",
        "review-stack": "scripts.code_review",
        "review-loop-state": "scripts.code_review",
```

In the dispatch routing section (the if/elif chain), add:

```python
        elif args.command == "review-forge":
            return mod.run_forge(args)
        elif args.command == "review-stack":
            return mod.run_stack(args)
        elif args.command == "review-loop-state":
            return mod.run_loop_state(args)
```

- [ ] **Step 3: Update CLI test to check new commands**

In `tests/test_cli.py`, update `test_help_shows_all_commands` to include the new commands:

Add `"review-forge", "review-stack", "review-loop-state"` to the list of expected commands.

- [ ] **Step 4: Run tests**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run pytest tests/test_cli.py tests/test_code_review.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/__main__.py tests/test_cli.py
git commit -m "feat: register review-forge, review-stack, review-loop-state in CLI"
```

---

### Task 6: Add `loop` subcommand to SKILL.md

**Files:**
- Modify: `skills/code-review/SKILL.md`

This adds the `loop` subcommand to the orchestrator. It references existing `new`/`update`/`fix` flows and calls the new scripts.

- [ ] **Step 1: Read the current SKILL.md**

Read `/Users/karthik/Documents/work/codebase-notes/skills/code-review/SKILL.md` completely (522 lines).

- [ ] **Step 2: Read the spec**

Read `/Users/karthik/Documents/work/codebase-notes/docs/superpowers/specs/2026-03-26-review-fix-loop.md` completely.

- [ ] **Step 3: Update the subcommands table**

Add `loop` to the table (currently lines 22-29):

```markdown
| `loop` | `"branch1" ...` or `--stack BASE`, `--project`, `--max-cycles`, `--auto-approve`, `--dry-run`, `--resume` | Automated review→fix→update cycle across branches |
```

- [ ] **Step 4: Add loop examples**

After the existing examples block (line 45), add:

```markdown
/codebase-notes:code-review loop "feat/auth" "feat/api"                     # review two branches
/codebase-notes:code-review loop --stack "feat/vertical-slice"              # discover and review stack
/codebase-notes:code-review loop --stack "feat/vertical-slice" --project "projects/comp-embeddings" --auto-approve
/codebase-notes:code-review loop --resume                                   # resume interrupted loop
/codebase-notes:code-review loop --stack "feat/vertical-slice" --dry-run    # preview without executing
```

- [ ] **Step 5: Update Step 0 forge detection to use `review-forge` script**

Replace the current prose-based forge detection (Step 0.5, around lines 92-97) with:

```markdown
**Forge detection:** Run `run-script review-forge` to get forge type, CLI availability, and authentication status. Use the returned `cli_usable` field to determine if PR/MR metadata is available. If `cli_usable` is false and identifier is a bare number, error clearly.
```

- [ ] **Step 6: Add the `loop` subcommand section**

Add before the Backward Compatibility section (around line 497). This is ~80 lines:

```markdown
---

## Subcommand: `loop`

Automated review→fix→update cycle. Runs until critical/suggestion findings converge or max cycles reached.

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"branch1" "branch2" ...` | Yes (unless `--stack`) | Branches to review in order |
| `--stack BASE` | No | Auto-discover stacked branches from base via `run-script review-stack --base <BASE>` |
| `--project NAME` | No | Project notes for domain context (routed to DE + SA personas only) |
| `--max-cycles N` | No | Max fix cycles per branch (default: 3) |
| `--auto-approve` | No | Skip fix-plan confirmation, auto-defer conflicts, auto-skip failed clusters |
| `--dry-run` | No | Preview branch list + existing findings without executing |
| `--resume` | No | Resume from `loop-state.json` |

### Flow

1. **Resolve branches:**
   - `--resume`: `run-script review-loop-state --review-dir <path> --action read`, skip completed branches
   - `--stack`: `run-script review-stack --base <BASE>`, get ordered list. If multiple children at any level, present disambiguation.
   - Explicit list: use as provided
   - `--dry-run`: show branch table with existing review status, exit

2. **Initialize state:** `run-script review-loop-state --review-dir <path> --action write --branches '<json>' --args '<json>'`

3. **For each branch:**

   **Progress:** Announce `### Branch N/M: <name>`

   a. **Load context:**
      - If `--project`: read project notes, route to DE + SA only
      - If stacked and parent completed: re-read parent's POST-FIX review.md for summary + unresolved findings

   b. **Review:** Check if `code-reviews/<slug>/` exists.
      - Exists → run `update` subcommand flow
      - New → run `new` subcommand flow (with `--base <parent>` if stacked)

   c. **Check findings:** `run-script review-status --review-path <path> --action list-findings`
      - Filter: severity in (critical, suggestion)
      - Zero → log "Branch clean", update state, skip to next

   d. **Fix cycle** (up to `--max-cycles`):
      Track `min_findings_seen` across cycles.

      - Run `fix` flow (pass `--auto-approve` if set: auto-approve plan, auto-defer conflicts, auto-skip failed clusters)
      - Run `update` flow
      - `run-script review-status --action list-findings` → count findings where status in (new, missed, regressed) AND severity in (critical, suggestion)
      - **Converged:** count = 0 → exit cycle
      - **Stalled:** count ≥ `min_findings_seen` → exit cycle
      - **Continue:** update `min_findings_seen = min(min_findings_seen, count)`
      - Checkpoint: `run-script review-loop-state --action update-branch --branch <name> --status in-progress --cycles <N>`

   e. **Finalize branch:**
      - Update state: `run-script review-loop-state --action update-branch --branch <name> --status <converged|stalled|hard-cap|clean>`
      - Log remaining suggestions/nits

   f. **Rebase next branch** (stacked mode only):
      ```bash
      git rebase <current_branch> <next_branch>
      ```
      If conflict: `git rebase --abort`, log warning, continue anyway.

   g. **Checkpoint after branch 1** (unless `--auto-approve`):
      "Branch 1/N complete. Continue with remaining branches? (yes/stop)"

4. **Final summary:**

   ```
   ## Loop Summary

   | Branch | Cycles | Status | Critical | Suggestions | Nits |
   |--------|--------|--------|----------|-------------|------|
   ...

   Total: N branches, M converged, K stalled
   ```
```

- [ ] **Step 7: Verify line count**

```bash
wc -l skills/code-review/SKILL.md
```

Expected: ~600 lines (522 + ~80 for loop section).

- [ ] **Step 8: Commit**

```bash
git add skills/code-review/SKILL.md
git commit -m "feat: add loop subcommand to SKILL.md for automated review-fix cycles"
```

---

### Task 7: Verify everything works together

**Files:**
- No changes — validation only

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run pytest tests/ -v
```

All tests should pass.

- [ ] **Step 2: Verify new CLI commands are accessible**

```bash
cd /Users/karthik/Documents/work/codebase-notes && uv run python -m scripts review-forge --help
cd /Users/karthik/Documents/work/codebase-notes && uv run python -m scripts review-stack --help
cd /Users/karthik/Documents/work/codebase-notes && uv run python -m scripts review-loop-state --help
```

All should print help text.

- [ ] **Step 3: Test forge detection on the arc repo**

```bash
cd /Users/karthik/Documents/work/arc && REPO_ROOT=$(git rev-parse --show-toplevel) /Users/karthik/Documents/work/codebase-notes/.venv/bin/python -m scripts review-forge
```

Expected: JSON with `forge: gitlab`, `cli: glab`, `cli_usable: true`.

- [ ] **Step 4: Test stack discovery on the arc repo**

```bash
cd /Users/karthik/Documents/work/arc && REPO_ROOT=$(git rev-parse --show-toplevel) /Users/karthik/Documents/work/codebase-notes/.venv/bin/python -m scripts review-stack --base "feat/composition-embeddings-vertical-slice"
```

Expected: JSON with ordered stack of 4-5 branches.

- [ ] **Step 5: Verify SKILL.md references all new scripts**

```bash
grep -c "review-forge\|review-stack\|review-loop-state" skills/code-review/SKILL.md
```

Expected: ≥3 matches.

- [ ] **Step 6: Check git log**

```bash
git log --oneline -8
```

Should show 6 commits from Tasks 1-6.
