# Codebase Notes v2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the codebase-notes skill with centralized repo-keyed storage, Python CLI scripts for deterministic operations, commit history tracking, and cron-based auto-updates.

**Architecture:** Self-contained skill with no external dependencies. Python scripts (via uv) handle all deterministic ops (repo ID resolution, scaffolding, staleness checking, navigation rebuilding, rendering, commit history, cron). Claude handles content writing, summarization, diagram JSON creation, and exploration decisions. Notes stored at `~/.claude/repo_notes/<org>--<repo>/`.

**Tech Stack:** Python 3.11+, uv, PyYAML, Pillow, argparse, fcntl, launchd/crontab

**Spec:** `docs/superpowers/specs/2026-03-18-codebase-notes-v2-design.md`

**Dependency Graph:**
```
Task 1 (setup) → Task 2 (repo_id) → Task 3 (scaffold)
                                   ↘
Task 1 → Task 4 (staleness) ——→ Task 8 (cron)
Task 1 → Task 5 (nav_links)
Task 1 → Task 6 (render)
Task 1 → Task 7 (commits)
Task 2 → Task 9 (migrate)
Tasks 1-9 → Task 10 (RULES.md)
Tasks 1-9 → Task 11 (SKILL.md)
Tasks 1-11 → Task 12 (integration)
```

**Parallelizable groups (after Task 1-2 complete):**
- Group A: Tasks 3, 4, 5, 6, 7 (independent scripts)
- Group B: Tasks 8, 9 (depend on staleness/repo_id)
- Group C: Tasks 10, 11 (content rewrites, after all scripts exist)
- Group D: Task 12 (integration, after everything)

---

## Task 1: Project Setup + CLI Dispatcher

### Files
- Create: `scripts/pyproject.toml`
- Create: `scripts/__init__.py`
- Create: `scripts/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_cli.py`

- [ ] **1.1: Create `scripts/pyproject.toml`**

```toml
[project]
name = "codebase-notes-scripts"
version = "0.1.0"
description = "CLI scripts for codebase-notes skill"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0,<7.0",
    "Pillow>=10.0,<12.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["../tests"]
```

- [ ] **1.2: Create `scripts/__init__.py`**

```python
"""Codebase notes CLI scripts."""
```

- [ ] **1.3: Create `scripts/__main__.py` with argparse dispatcher**

```python
"""CLI dispatcher for codebase-notes scripts."""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="scripts",
        description="CLI tools for codebase-notes skill",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # repo-id
    subparsers.add_parser("repo-id", help="Print the repo ID for the current git repo")

    # scaffold
    subparsers.add_parser("scaffold", help="Create notes directory structure for current repo")

    # stale
    stale_parser = subparsers.add_parser("stale", help="Check all notes for staleness")
    stale_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")
    stale_parser.add_argument("--all-repos", action="store_true", help="Check all repos")
    stale_parser.add_argument("--no-cache", action="store_true", help="Skip staleness cache")

    # nav
    nav_parser = subparsers.add_parser("nav", help="Rebuild all navigation links")
    nav_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")

    # render
    render_parser = subparsers.add_parser("render", help="Render .excalidraw to .png")
    render_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")

    # commits
    commits_parser = subparsers.add_parser("commits", help="Generate commit history notes")
    commits_parser.add_argument("--author", required=True, help="Author name or email")
    commits_parser.add_argument("--since", default="4w", help="Time range (default: 4w)")
    commits_parser.add_argument("--path", default="", help="Path filter")
    commits_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")

    # auto-update
    auto_parser = subparsers.add_parser("auto-update", help="Run staleness check + Claude update")
    auto_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")
    auto_parser.add_argument("--all-repos", action="store_true", help="Update all repos")

    # cron
    cron_parser = subparsers.add_parser("cron", help="Manage cron auto-updates")
    cron_group = cron_parser.add_mutually_exclusive_group(required=True)
    cron_group.add_argument("--install", action="store_true", help="Install cron entry")
    cron_group.add_argument("--uninstall", action="store_true", help="Remove cron entry")
    cron_parser.add_argument("--interval", default="6h", help="Cron interval (default: 6h)")

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Migrate v1 notes to v2")
    migrate_parser.add_argument("--from", dest="from_path", required=True, help="Source notes path")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # Dispatch to subcommand modules.
    # Each module must expose a run(args) -> int entry point.
    # Modules are imported lazily so missing ones fail gracefully.
    dispatch = {
        "repo-id": "scripts.repo_id",
        "scaffold": "scripts.scaffold",
        "stale": "scripts.staleness",
        "nav": "scripts.nav_links",
        "render": "scripts.render",
        "commits": "scripts.commits",
        "auto-update": "scripts.cron",
        "cron": "scripts.cron",
        "migrate": "scripts.migrate",
    }

    module_name = dispatch.get(args.command)
    if module_name is None:
        print(f"{args.command}: unknown command", file=sys.stderr)
        return 1

    try:
        import importlib
        mod = importlib.import_module(module_name)
        # cron module has two entry points
        if args.command == "cron":
            return mod.run_cron(args)
        elif args.command == "auto-update":
            return mod.run_auto_update(args)
        else:
            return mod.run(args)
    except ImportError:
        print(f"{args.command}: not yet implemented", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **1.4: Create `tests/__init__.py` and `tests/test_cli.py`**

```python
# tests/__init__.py — empty

# tests/test_cli.py
"""Tests for CLI dispatcher."""

import subprocess
import sys


def test_help_shows_all_commands():
    result = subprocess.run(
        [sys.executable, "-m", "scripts", "--help"],
        capture_output=True, text=True,
        cwd="scripts",
    )
    assert result.returncode == 0
    for cmd in ["repo-id", "scaffold", "stale", "nav", "render", "commits", "auto-update", "cron", "migrate"]:
        assert cmd in result.stdout, f"Missing subcommand: {cmd}"


def test_no_command_prints_help():
    result = subprocess.run(
        [sys.executable, "-m", "scripts"],
        capture_output=True, text=True,
        cwd="scripts",
    )
    assert result.returncode == 1
```

- [ ] **1.5: Run `uv sync` to bootstrap**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv sync
```

- [ ] **1.6: Run tests**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cli.py -v
```

- [ ] **1.7: Commit**

```bash
git add scripts/pyproject.toml scripts/__init__.py scripts/__main__.py tests/__init__.py tests/test_cli.py
git commit -m "Add project setup and CLI dispatcher with all subcommands"
```

---

## Task 2: repo_id.py + Tests

### Files
- Create: `scripts/repo_id.py`
- Create: `tests/test_repo_id.py`

- [ ] **2.1: Write failing tests**

Create `tests/test_repo_id.py`:

```python
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
```

- [ ] **2.2: Run tests — should fail**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_repo_id.py -v
```

- [ ] **2.3: Implement `scripts/repo_id.py`**

```python
"""Resolve the repo ID from git remote URL or local path fallback."""

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path


def _sanitize_dirname(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def _parse_remote_url(url: str) -> str:
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    url = url.rstrip("/")

    # SSH with protocol: ssh://git@host:port/org/repo
    m = re.match(r"ssh://[^@]+@[^:/]+(?::\d+)?/(.+)", url)
    if m:
        return m.group(1).replace("/", "--")

    # SSH shorthand: git@host:org/repo
    m = re.match(r"[^@]+@[^:]+:(.+)", url)
    if m:
        return m.group(1).replace("/", "--")

    # HTTPS: https://host/org/repo
    m = re.match(r"https?://[^/]+/(.+)", url)
    if m:
        return m.group(1).replace("/", "--")

    raise ValueError(f"Cannot parse git remote URL: {url}")


def resolve_repo_id(cwd: str | None = None) -> str:
    if cwd is None:
        cwd = os.getcwd()
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True, cwd=cwd,
        )
        return _parse_remote_url(result.stdout.strip())
    except subprocess.CalledProcessError:
        dirname = _sanitize_dirname(os.path.basename(cwd))
        path_hash = hashlib.sha256(cwd.encode()).hexdigest()[:8]
        return f"local--{dirname}--{path_hash}"


def get_repo_id(cwd: str | None = None) -> str:
    """Alias for resolve_repo_id — used by other modules."""
    return resolve_repo_id(cwd=cwd)


def get_notes_dir(cwd: str | None = None) -> Path:
    """Return the centralized notes directory for the repo at cwd."""
    repo_id = resolve_repo_id(cwd=cwd)
    return Path.home() / ".claude" / "repo_notes" / repo_id / "notes"


def get_repo_dir(cwd: str | None = None) -> Path:
    """Return the centralized repo directory for the repo at cwd."""
    repo_id = resolve_repo_id(cwd=cwd)
    return Path.home() / ".claude" / "repo_notes" / repo_id


def run(args) -> int:
    try:
        print(resolve_repo_id())
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

- [ ] **2.4: Run tests — should pass**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_repo_id.py -v
```

- [ ] **2.5: Integration test against real repo**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts repo-id
```

- [ ] **2.6: Commit**

```bash
git add scripts/repo_id.py tests/test_repo_id.py
git commit -m "Add repo_id.py: resolve git remote URLs to repo IDs"
```

---

## Task 3: scaffold.py + Tests

### Files
- Create: `scripts/scaffold.py`
- Create: `tests/test_scaffold.py`

- [ ] **3.1: Write failing tests**

Create `tests/test_scaffold.py`:

```python
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
    def test_creates_notes_and_commits_dirs(self, fake_env):
        tmp_path, repo_notes, refs_dir = fake_env
        with patch("scripts.scaffold.REPO_NOTES_BASE", repo_notes), \
             patch("scripts.scaffold.REFERENCES_DIR", refs_dir):
            scaffold_repo("org--repo", clone_path="/tmp/fake-clone")
        assert (repo_notes / "org--repo" / "notes").is_dir()
        assert (repo_notes / "org--repo" / "commits").is_dir()

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
```

- [ ] **3.2: Run tests — should fail**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_scaffold.py -v
```

- [ ] **3.3: Implement `scripts/scaffold.py`**

```python
"""Scaffold notes directory structure for a repo."""

import fcntl
import os
import shutil
import sys
from datetime import date
from pathlib import Path

from scripts.repo_id import resolve_repo_id

REPO_NOTES_BASE = Path.home() / ".claude" / "repo_notes"
REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"

OVERVIEW_SKELETON = """\
---
git_tracked_paths: []
last_updated: {today}
---
# Codebase Overview

> **Navigation:** This is the root note.

## Topics

_No topics yet. Run exploration to populate._

## Key Files

| File | Purpose |
|------|---------|
| | |
"""


def _register_clone_path(repo_dir: Path, clone_path: str) -> None:
    repo_paths_file = repo_dir / ".repo_paths"
    lock_file = repo_dir / ".repo_paths.lock"
    lock_file.touch(exist_ok=True)
    fd = os.open(str(lock_file), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        existing: set[str] = set()
        if repo_paths_file.exists():
            existing = set(l.strip() for l in repo_paths_file.read_text().splitlines() if l.strip())
        if clone_path not in existing:
            existing.add(clone_path)
            repo_paths_file.write_text("\n".join(sorted(existing)) + "\n")
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def scaffold_repo(repo_id: str, clone_path: str) -> None:
    repo_dir = REPO_NOTES_BASE / repo_id
    notes_dir = repo_dir / "notes"
    commits_dir = repo_dir / "commits"

    notes_dir.mkdir(parents=True, exist_ok=True)
    commits_dir.mkdir(parents=True, exist_ok=True)

    rules_dest = notes_dir / "RULES.md"
    rules_src = REFERENCES_DIR / "RULES-template.md"
    if not rules_dest.exists() and rules_src.exists():
        shutil.copy2(rules_src, rules_dest)

    overview = notes_dir / "00-overview.md"
    if not overview.exists():
        overview.write_text(OVERVIEW_SKELETON.format(today=date.today().isoformat()))

    _register_clone_path(repo_dir, clone_path)


def run(args) -> int:
    try:
        clone_path = os.getcwd()
        repo_id = resolve_repo_id(cwd=clone_path)
        scaffold_repo(repo_id, clone_path)
        print(f"Scaffolded: {REPO_NOTES_BASE / repo_id}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

- [ ] **3.4: Run tests — should pass**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_scaffold.py -v
```

- [ ] **3.5: Run all tests**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/ -v
```

- [ ] **3.6: Commit**

```bash
git add scripts/scaffold.py tests/test_scaffold.py
git commit -m "Add scaffold.py: create centralized notes directory structure"
```

---

## Task 4: staleness.py + Tests

### Files
- `/Users/karthik/Documents/work/codebase-notes/scripts/staleness.py` — Core staleness checking module
- `/Users/karthik/Documents/work/codebase-notes/tests/test_staleness.py` — Tests for staleness module

### Prerequisites
- Task 1 (pyproject.toml, `__init__.py`, `__main__.py`) must be complete so `pyyaml` is available and the scripts package exists
- Task 2 (repo_id.py) must be complete for `--all-repos` mode to resolve repo IDs

### Steps

- [ ] **Step 1: Write failing test for YAML frontmatter parsing**

Create `/Users/karthik/Documents/work/codebase-notes/tests/test_staleness.py`:

```python
"""Tests for staleness checking."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.staleness import (
    parse_frontmatter,
    check_note_staleness,
    check_all_notes,
    check_all_repos,
    load_cache,
    save_cache,
    is_cache_valid,
    StalenessStatus,
    NoteReport,
)


class TestParseFrontmatter:
    """Test YAML frontmatter extraction from markdown files."""

    def test_parse_valid_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "git_tracked_paths:\n"
            "  - path: src/api/\n"
            "    commit: abc1234\n"
            "  - path: src/models/\n"
            "    commit: def5678\n"
            "last_updated: 2026-03-16\n"
            "---\n"
            "# My Note\n"
            "Content here.\n"
        )
        fm = parse_frontmatter(note)
        assert fm is not None
        assert len(fm["git_tracked_paths"]) == 2
        assert fm["git_tracked_paths"][0]["path"] == "src/api/"
        assert fm["git_tracked_paths"][0]["commit"] == "abc1234"
        assert fm["git_tracked_paths"][1]["path"] == "src/models/"
        assert fm["git_tracked_paths"][1]["commit"] == "def5678"

    def test_parse_no_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("# Just a heading\nNo frontmatter here.\n")
        fm = parse_frontmatter(note)
        assert fm is None

    def test_parse_frontmatter_no_tracked_paths(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "last_updated: 2026-03-16\n"
            "---\n"
            "# Note without tracking\n"
        )
        fm = parse_frontmatter(note)
        assert fm is not None
        assert "git_tracked_paths" not in fm

    def test_parse_empty_file(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("")
        fm = parse_frontmatter(note)
        assert fm is None

    def test_parse_frontmatter_only_opening_dashes(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: broken\n# No closing dashes\n")
        fm = parse_frontmatter(note)
        assert fm is None
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py -v
```

Expected: Fails with `ModuleNotFoundError: No module named 'scripts.staleness'`

- [ ] **Step 2: Implement `parse_frontmatter` and `StalenessStatus`/`NoteReport` data structures**

Create `/Users/karthik/Documents/work/codebase-notes/scripts/staleness.py`:

```python
"""Staleness checking for codebase notes.

Parses YAML frontmatter from .md files, runs git diff to detect changes
since the tracked commit, and outputs a structured staleness report.
Supports caching and --all-repos mode.
"""

import json
import subprocess
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class StalenessStatus(Enum):
    """Status of a note's freshness."""
    FRESH = "FRESH"
    STALE = "STALE"
    NO_TRACKING = "NO_TRACKING"


@dataclass
class NoteReport:
    """Staleness report for a single note."""
    note_path: str
    status: StalenessStatus
    changed_files: list[str] = field(default_factory=list)
    commit: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "note_path": self.note_path,
            "status": self.status.value,
            "changed_files": self.changed_files,
            "commit": self.commit,
            "message": self.message,
        }


def parse_frontmatter(filepath: Path) -> Optional[dict]:
    """Parse YAML frontmatter from a markdown file.

    Frontmatter must be delimited by --- on its own line at the start
    of the file, and closed by another --- line.

    Returns the parsed YAML dict, or None if no valid frontmatter found.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if not text.startswith("---"):
        return None

    # Find closing ---
    lines = text.split("\n")
    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        return None

    frontmatter_text = "\n".join(lines[1:closing_idx])
    try:
        return yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None


def check_note_staleness(
    note_path: Path,
    repo_root: Path,
) -> NoteReport:
    """Check staleness of a single note by running git diff for each tracked path.

    Args:
        note_path: Path to the .md note file.
        repo_root: Path to the git repository root (for running git commands).

    Returns:
        NoteReport with status and any changed files.
    """
    fm = parse_frontmatter(note_path)
    if fm is None or "git_tracked_paths" not in fm:
        return NoteReport(
            note_path=str(note_path),
            status=StalenessStatus.NO_TRACKING,
            message="no git_tracked_paths in frontmatter",
        )

    all_changed: list[str] = []
    last_commit = None

    for entry in fm["git_tracked_paths"]:
        path = entry.get("path", "")
        commit = entry.get("commit", "")
        if not path or not commit:
            continue
        last_commit = commit

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", commit, "HEAD", "--", path],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                changed = result.stdout.strip().split("\n")
                all_changed.extend(changed)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if all_changed:
        return NoteReport(
            note_path=str(note_path),
            status=StalenessStatus.STALE,
            changed_files=all_changed,
            commit=last_commit,
            message=f"{len(all_changed)} files changed since {last_commit}",
        )

    return NoteReport(
        note_path=str(note_path),
        status=StalenessStatus.FRESH,
        commit=last_commit,
        message="0 files changed",
    )


def check_all_notes(
    notes_dir: Path,
    repo_root: Path,
) -> list[NoteReport]:
    """Check staleness of all .md files in a notes directory.

    Args:
        notes_dir: Path to the notes/ directory.
        repo_root: Path to the git repository root.

    Returns:
        List of NoteReport for each .md file found.
    """
    reports: list[NoteReport] = []
    if not notes_dir.is_dir():
        return reports

    for md_file in sorted(notes_dir.rglob("*.md")):
        reports.append(check_note_staleness(md_file, repo_root))

    return reports


# --- Caching ---

CACHE_TTL_SECONDS = 600  # 10 minutes


def _cache_path(repo_notes_dir: Path) -> Path:
    """Return the .staleness_cache path for a repo notes directory."""
    return repo_notes_dir / ".staleness_cache"


def save_cache(repo_notes_dir: Path, reports: list[NoteReport]) -> None:
    """Write staleness reports to cache file with a timestamp."""
    cache_file = _cache_path(repo_notes_dir)
    data = {
        "timestamp": time.time(),
        "reports": [r.to_dict() for r in reports],
    }
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_cache(repo_notes_dir: Path) -> Optional[list[dict]]:
    """Load cached staleness reports if the cache file exists.

    Returns the raw list of report dicts, or None if no cache file.
    """
    cache_file = _cache_path(repo_notes_dir)
    if not cache_file.is_file():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data.get("reports")
    except (json.JSONDecodeError, OSError):
        return None


def is_cache_valid(repo_notes_dir: Path, ttl: int = CACHE_TTL_SECONDS) -> bool:
    """Check if the cache exists and is younger than ttl seconds."""
    cache_file = _cache_path(repo_notes_dir)
    if not cache_file.is_file():
        return False
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        ts = data.get("timestamp", 0)
        return (time.time() - ts) < ttl
    except (json.JSONDecodeError, OSError):
        return False


def check_all_repos(
    repo_notes_root: Path,
) -> dict[str, list[NoteReport]]:
    """Check staleness for all repos in ~/.claude/repo_notes/.

    For each repo directory, validates .repo_paths to find a valid git clone,
    then runs staleness checks from that clone.

    Args:
        repo_notes_root: Path to ~/.claude/repo_notes/

    Returns:
        Dict mapping repo_id to list of NoteReports. Repos with no valid
        clone path are included with an empty list and a warning is printed.
    """
    from scripts.repo_id import get_repo_id

    results: dict[str, list[NoteReport]] = {}
    if not repo_notes_root.is_dir():
        return results

    for repo_dir in sorted(repo_notes_root.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue

        repo_id = repo_dir.name
        repo_paths_file = repo_dir / ".repo_paths"

        valid_clone = _find_valid_clone(repo_paths_file, repo_id)
        if valid_clone is None:
            print(f"WARNING: {repo_id} — no valid clone path found, skipping")
            results[repo_id] = []
            continue

        notes_dir = repo_dir / "notes"
        reports = check_all_notes(notes_dir, valid_clone)
        results[repo_id] = reports

    return results


def _find_valid_clone(
    repo_paths_file: Path,
    expected_repo_id: str,
) -> Optional[Path]:
    """Find the first valid clone path from a .repo_paths file.

    A path is valid if:
    - The directory exists
    - It is a git repo (has .git/)
    - git remote get-url origin resolves to the expected repo_id

    Invalid paths are pruned from the file.
    """
    if not repo_paths_file.is_file():
        return None

    from scripts.repo_id import get_repo_id

    lines = repo_paths_file.read_text(encoding="utf-8").strip().split("\n")
    valid_paths: list[str] = []
    first_valid: Optional[Path] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        clone_path = Path(line)
        if not clone_path.is_dir():
            continue
        if not (clone_path / ".git").exists():
            continue

        try:
            resolved_id = get_repo_id(clone_path)
        except Exception:
            continue

        if resolved_id != expected_repo_id:
            continue

        valid_paths.append(line)
        if first_valid is None:
            first_valid = clone_path

    # Prune invalid paths by rewriting the file
    if valid_paths != [l.strip() for l in lines if l.strip()]:
        repo_paths_file.write_text(
            "\n".join(valid_paths) + "\n", encoding="utf-8"
        )

    return first_valid


def format_report(reports: list[NoteReport]) -> str:
    """Format a list of NoteReports as a human-readable string."""
    lines: list[str] = []
    for r in reports:
        note_name = Path(r.note_path).name
        if r.status == StalenessStatus.FRESH:
            lines.append(f"FRESH: {note_name} ({r.message})")
        elif r.status == StalenessStatus.STALE:
            lines.append(f"STALE: {note_name} ({r.message})")
            for f in r.changed_files:
                lines.append(f"  - {f}")
        elif r.status == StalenessStatus.NO_TRACKING:
            lines.append(f"NO_TRACKING: {note_name} ({r.message})")
    return "\n".join(lines)
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py::TestParseFrontmatter -v
```

Expected: All 5 frontmatter tests pass.

- [ ] **Step 3: Write failing tests for `check_note_staleness`**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_staleness.py`:

```python
class TestCheckNoteStaleness:
    """Test staleness checking for a single note."""

    def test_fresh_note(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "git_tracked_paths:\n"
            "  - path: src/api/\n"
            "    commit: abc1234\n"
            "---\n"
            "# Fresh note\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
            )
            report = check_note_staleness(note, tmp_path)

        assert report.status == StalenessStatus.FRESH
        assert report.changed_files == []
        assert report.commit == "abc1234"
        mock_run.assert_called_once_with(
            ["git", "diff", "--name-only", "abc1234", "HEAD", "--", "src/api/"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_stale_note(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "git_tracked_paths:\n"
            "  - path: src/models/\n"
            "    commit: def5678\n"
            "---\n"
            "# Stale note\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="src/models/user.py\nsrc/models/auth.py\n",
            )
            report = check_note_staleness(note, tmp_path)

        assert report.status == StalenessStatus.STALE
        assert len(report.changed_files) == 2
        assert "src/models/user.py" in report.changed_files
        assert "src/models/auth.py" in report.changed_files
        assert report.commit == "def5678"

    def test_no_tracking_note(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("# No frontmatter\nJust content.\n")
        report = check_note_staleness(note, tmp_path)
        assert report.status == StalenessStatus.NO_TRACKING

    def test_multiple_tracked_paths(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "git_tracked_paths:\n"
            "  - path: src/api/\n"
            "    commit: abc1234\n"
            "  - path: src/models/\n"
            "    commit: def5678\n"
            "---\n"
            "# Multi-path note\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            # First path: no changes. Second path: 1 change.
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="src/models/user.py\n"),
            ]
            report = check_note_staleness(note, tmp_path)

        assert report.status == StalenessStatus.STALE
        assert report.changed_files == ["src/models/user.py"]
        assert mock_run.call_count == 2

    def test_git_timeout_handled(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "git_tracked_paths:\n"
            "  - path: src/\n"
            "    commit: aaa1111\n"
            "---\n"
            "# Timeout note\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
            report = check_note_staleness(note, tmp_path)

        # Timeout is swallowed; note shows as fresh (no changed files detected)
        assert report.status == StalenessStatus.FRESH
```

Add the missing import at the top of the file:

```python
import subprocess
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py::TestCheckNoteStaleness -v
```

Expected: All 5 tests pass.

- [ ] **Step 4: Write failing tests for `check_all_notes`**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_staleness.py`:

```python
class TestCheckAllNotes:
    """Test checking all notes in a directory."""

    def test_multiple_notes(self, tmp_path):
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()

        fresh = notes_dir / "01-fresh.md"
        fresh.write_text(
            "---\ngit_tracked_paths:\n  - path: src/a/\n    commit: aaa\n---\n# Fresh\n"
        )
        stale = notes_dir / "02-stale.md"
        stale.write_text(
            "---\ngit_tracked_paths:\n  - path: src/b/\n    commit: bbb\n---\n# Stale\n"
        )
        notrack = notes_dir / "03-notrack.md"
        notrack.write_text("# No tracking\n")

        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),           # fresh
                MagicMock(returncode=0, stdout="src/b/x.py\n"),  # stale
            ]
            reports = check_all_notes(notes_dir, tmp_path)

        assert len(reports) == 3
        assert reports[0].status == StalenessStatus.FRESH
        assert reports[1].status == StalenessStatus.STALE
        assert reports[2].status == StalenessStatus.NO_TRACKING

    def test_nested_notes(self, tmp_path):
        notes_dir = tmp_path / "notes"
        sub = notes_dir / "01-topic"
        sub.mkdir(parents=True)
        (sub / "index.md").write_text(
            "---\ngit_tracked_paths:\n  - path: src/\n    commit: ccc\n---\n# Index\n"
        )
        with patch("scripts.staleness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            reports = check_all_notes(notes_dir, tmp_path)

        assert len(reports) == 1
        assert reports[0].status == StalenessStatus.FRESH

    def test_empty_dir(self, tmp_path):
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        reports = check_all_notes(notes_dir, tmp_path)
        assert reports == []

    def test_nonexistent_dir(self, tmp_path):
        reports = check_all_notes(tmp_path / "nonexistent", tmp_path)
        assert reports == []
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py::TestCheckAllNotes -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Write failing tests for caching**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_staleness.py`:

```python
class TestCaching:
    """Test staleness cache read/write/validation."""

    def test_save_and_load_cache(self, tmp_path):
        reports = [
            NoteReport(
                note_path="/notes/01-api.md",
                status=StalenessStatus.FRESH,
                message="0 files changed",
            ),
            NoteReport(
                note_path="/notes/02-models.md",
                status=StalenessStatus.STALE,
                changed_files=["src/models/user.py"],
                commit="abc1234",
                message="1 files changed since abc1234",
            ),
        ]
        save_cache(tmp_path, reports)

        loaded = load_cache(tmp_path)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["status"] == "FRESH"
        assert loaded[1]["status"] == "STALE"
        assert loaded[1]["changed_files"] == ["src/models/user.py"]

    def test_cache_valid_within_ttl(self, tmp_path):
        reports = [
            NoteReport(note_path="x.md", status=StalenessStatus.FRESH, message="ok")
        ]
        save_cache(tmp_path, reports)
        assert is_cache_valid(tmp_path, ttl=600) is True

    def test_cache_expired(self, tmp_path):
        cache_file = tmp_path / ".staleness_cache"
        data = {
            "timestamp": time.time() - 700,  # 700 seconds ago
            "reports": [],
        }
        cache_file.write_text(json.dumps(data))
        assert is_cache_valid(tmp_path, ttl=600) is False

    def test_cache_missing(self, tmp_path):
        assert is_cache_valid(tmp_path) is False
        assert load_cache(tmp_path) is None

    def test_cache_corrupt(self, tmp_path):
        cache_file = tmp_path / ".staleness_cache"
        cache_file.write_text("not json{{{")
        assert is_cache_valid(tmp_path) is False
        assert load_cache(tmp_path) is None
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py::TestCaching -v
```

Expected: All 5 tests pass.

- [ ] **Step 6: Write failing tests for `check_all_repos` and `_find_valid_clone`**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_staleness.py`:

```python
class TestAllRepos:
    """Test --all-repos mode."""

    def test_find_valid_clone(self, tmp_path):
        # Create a fake clone directory with .git
        clone = tmp_path / "my-clone"
        clone.mkdir()
        (clone / ".git").mkdir()

        repo_paths_file = tmp_path / ".repo_paths"
        repo_paths_file.write_text(f"{clone}\n")

        with patch("scripts.staleness.get_repo_id", return_value="org--repo") as mock_id:
            from scripts.staleness import _find_valid_clone
            result = _find_valid_clone(repo_paths_file, "org--repo")

        assert result == clone

    def test_find_valid_clone_prunes_invalid(self, tmp_path):
        # One valid, one missing directory
        clone = tmp_path / "valid-clone"
        clone.mkdir()
        (clone / ".git").mkdir()

        repo_paths_file = tmp_path / ".repo_paths"
        repo_paths_file.write_text(f"/nonexistent/path\n{clone}\n")

        with patch("scripts.staleness.get_repo_id", return_value="org--repo"):
            from scripts.staleness import _find_valid_clone
            result = _find_valid_clone(repo_paths_file, "org--repo")

        assert result == clone
        # File should be pruned to only valid path
        lines = repo_paths_file.read_text().strip().split("\n")
        assert len(lines) == 1
        assert str(clone) in lines[0]

    def test_find_valid_clone_wrong_repo_id(self, tmp_path):
        clone = tmp_path / "wrong-repo"
        clone.mkdir()
        (clone / ".git").mkdir()

        repo_paths_file = tmp_path / ".repo_paths"
        repo_paths_file.write_text(f"{clone}\n")

        with patch("scripts.staleness.get_repo_id", return_value="other--repo"):
            from scripts.staleness import _find_valid_clone
            result = _find_valid_clone(repo_paths_file, "org--repo")

        assert result is None

    def test_find_valid_clone_no_file(self, tmp_path):
        from scripts.staleness import _find_valid_clone
        result = _find_valid_clone(tmp_path / ".repo_paths", "org--repo")
        assert result is None

    def test_check_all_repos_skips_dotfiles(self, tmp_path):
        # Create a dotfile directory that should be skipped
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "notes").mkdir()

        with patch("scripts.staleness._find_valid_clone", return_value=None):
            results = check_all_repos(tmp_path)

        assert ".hidden" not in results

    def test_check_all_repos_with_valid_repo(self, tmp_path):
        # Set up a repo directory structure
        repo_dir = tmp_path / "org--repo"
        repo_dir.mkdir()
        notes_dir = repo_dir / "notes"
        notes_dir.mkdir()
        (notes_dir / "01-api.md").write_text("# No tracking\n")
        (repo_dir / ".repo_paths").write_text("/some/clone\n")

        clone = tmp_path / "clone"
        clone.mkdir()

        with patch("scripts.staleness._find_valid_clone", return_value=clone):
            results = check_all_repos(tmp_path)

        assert "org--repo" in results
        assert len(results["org--repo"]) == 1
        assert results["org--repo"][0].status == StalenessStatus.NO_TRACKING
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py::TestAllRepos -v
```

Expected: All 6 tests pass.

- [ ] **Step 7: Write failing test for `format_report`**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_staleness.py`:

```python
class TestFormatReport:
    """Test human-readable report formatting."""

    def test_format_mixed_report(self):
        reports = [
            NoteReport(
                note_path="/notes/01-api.md",
                status=StalenessStatus.FRESH,
                message="0 files changed",
            ),
            NoteReport(
                note_path="/notes/02-models/index.md",
                status=StalenessStatus.STALE,
                changed_files=["src/models/user.py", "src/models/auth.py"],
                commit="abc1234",
                message="2 files changed since abc1234",
            ),
            NoteReport(
                note_path="/notes/03-config.md",
                status=StalenessStatus.NO_TRACKING,
                message="no git_tracked_paths in frontmatter",
            ),
        ]
        output = format_report(reports)
        assert "FRESH: 01-api.md" in output
        assert "STALE: index.md (2 files changed since abc1234)" in output
        assert "  - src/models/user.py" in output
        assert "  - src/models/auth.py" in output
        assert "NO_TRACKING: 03-config.md" in output
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py::TestFormatReport -v
```

Expected: Passes.

- [ ] **Step 8: Run full test suite and commit**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_staleness.py -v
```

Expected: All 25 tests pass. Commit with message: `feat: add staleness.py with frontmatter parsing, git diff checking, caching, and all-repos mode`

---

## Task 5: nav_links.py + Tests

### Files
- `/Users/karthik/Documents/work/codebase-notes/scripts/nav_links.py` — Navigation link rebuilding module
- `/Users/karthik/Documents/work/codebase-notes/tests/test_nav_links.py` — Tests for nav_links module

### Prerequisites
- Task 1 (pyproject.toml, `__init__.py`, `__main__.py`) must be complete so the scripts package exists

### Steps

- [ ] **Step 1: Write failing tests for `compute_nav_links`**

Create `/Users/karthik/Documents/work/codebase-notes/tests/test_nav_links.py`:

```python
"""Tests for navigation link rebuilding."""

import re
from pathlib import Path

import pytest

from scripts.nav_links import (
    build_notes_tree,
    compute_nav_links,
    NAV_PATTERN,
    SUBTOPICS_PATTERN,
    insert_or_replace_nav,
    rebuild_all_nav_links,
)


class TestNavPatterns:
    """Test regex patterns for matching nav lines."""

    def test_nav_pattern_matches_standard(self):
        line = '> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)'
        assert NAV_PATTERN.match(line)

    def test_nav_pattern_case_insensitive(self):
        line = '> **navigation:** Up: [Parent](../index.md)'
        assert NAV_PATTERN.match(line)

    def test_nav_pattern_with_extra_whitespace(self):
        line = '>  **Navigation:**  Up: [Parent](../index.md)'
        assert NAV_PATTERN.match(line)

    def test_nav_pattern_no_match_on_random_line(self):
        line = 'Some random text about navigation'
        assert NAV_PATTERN.match(line) is None

    def test_subtopics_pattern_matches(self):
        line = '> **Sub-topics:** [API](./01-api/index.md) | [Models](./02-models/index.md)'
        assert SUBTOPICS_PATTERN.match(line)

    def test_subtopics_pattern_case_insensitive(self):
        line = '> **sub-topics:** [API](./01-api/index.md)'
        assert SUBTOPICS_PATTERN.match(line)


class TestBuildNotesTree:
    """Test building the tree structure from the notes directory."""

    def test_flat_structure(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("---\n---\n# Overview\n")
        (notes / "RULES.md").write_text("# Rules\n")

        tree = build_notes_tree(notes)
        # RULES.md is excluded from tree; only numbered notes and index.md
        paths = [str(e["path"].name) for e in tree]
        assert "00-overview.md" in paths
        assert "RULES.md" not in paths

    def test_nested_structure(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("# Overview\n")

        sub = notes / "01-api"
        sub.mkdir()
        (sub / "index.md").write_text("# API\n")
        (sub / "01-endpoints.md").write_text("# Endpoints\n")
        (sub / "02-middleware.md").write_text("# Middleware\n")

        tree = build_notes_tree(notes)
        # Root level: 00-overview.md + 01-api/ (represented by index.md)
        root_names = [e["path"].name for e in tree]
        assert "00-overview.md" in root_names

    def test_sorted_by_name(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "02-second.md").write_text("# Second\n")
        (notes / "01-first.md").write_text("# First\n")
        (notes / "03-third.md").write_text("# Third\n")

        tree = build_notes_tree(notes)
        names = [e["path"].name for e in tree]
        assert names == ["01-first.md", "02-second.md", "03-third.md"]
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_nav_links.py -v
```

Expected: Fails with `ModuleNotFoundError: No module named 'scripts.nav_links'`

- [ ] **Step 2: Implement the core nav_links module**

Create `/Users/karthik/Documents/work/codebase-notes/scripts/nav_links.py`:

```python
"""Deterministic navigation link rebuilding for codebase notes.

Walks the notes directory tree, computes correct Up/Prev/Next/Sub-topics
links for each .md file based on its position, and inserts or replaces
navigation lines. Idempotent — running twice produces the same result.
"""

import re
from pathlib import Path
from typing import Optional

# Patterns match lines starting with > **Navigation:** or > **Sub-topics:**
# Case-insensitive, whitespace-tolerant
NAV_PATTERN = re.compile(
    r"^>\s*\*\*navigation:\*\*",
    re.IGNORECASE,
)
SUBTOPICS_PATTERN = re.compile(
    r"^>\s*\*\*sub-topics:\*\*",
    re.IGNORECASE,
)

# Files to exclude from navigation tree
EXCLUDED_FILES = {"RULES.md", "rules.md"}


def build_notes_tree(notes_dir: Path) -> list[dict]:
    """Build a sorted list of note entries at the top level of a directory.

    Each entry is a dict with:
        - path: Path to the .md file
        - children: list of child entries (for directories with index.md)
        - is_index: True if this is an index.md

    Only includes numbered notes (NN-*) and index.md files.
    Directories are represented by their index.md.
    RULES.md and other non-numbered files are excluded.
    """
    return _build_level(notes_dir)


def _build_level(directory: Path) -> list[dict]:
    """Recursively build the tree for a single directory level."""
    entries: list[dict] = []

    if not directory.is_dir():
        return entries

    items = sorted(directory.iterdir())

    for item in items:
        if item.name in EXCLUDED_FILES:
            continue

        if item.is_file() and item.suffix == ".md":
            # Skip index.md at this level — it's handled by parent dir entry
            if item.name == "index.md":
                continue
            entries.append({
                "path": item,
                "children": [],
                "is_index": False,
            })

        elif item.is_dir():
            index_file = item / "index.md"
            if index_file.is_file():
                children = _build_level(item)
                entries.append({
                    "path": index_file,
                    "children": children,
                    "is_index": True,
                })
            else:
                # Directory without index.md — include any .md files inside as flat entries
                # (unusual, but handle gracefully)
                for child_md in sorted(item.glob("*.md")):
                    if child_md.name not in EXCLUDED_FILES:
                        entries.append({
                            "path": child_md,
                            "children": [],
                            "is_index": False,
                        })

    return entries


def compute_nav_links(
    note_path: Path,
    notes_dir: Path,
) -> dict:
    """Compute navigation links for a given note file.

    Returns a dict with keys:
        - up: relative path string to parent, or None
        - prev: relative path string to previous sibling, or None
        - next: relative path string to next sibling, or None
        - subtopics: list of (label, relative_path) tuples for children (index.md only)
        - is_index: whether this note is an index.md
    """
    # Determine which level this note lives at
    parent_dir = note_path.parent
    is_index = note_path.name == "index.md"

    if is_index:
        # The "siblings" are other entries in the grandparent directory
        sibling_dir = parent_dir.parent
    else:
        sibling_dir = parent_dir

    # Build sibling list at this level
    siblings = _build_level(sibling_dir)

    # Find ourselves in the sibling list
    my_idx = None
    for i, entry in enumerate(siblings):
        if entry["path"].resolve() == note_path.resolve():
            my_idx = i
            break

    # Compute up link
    up: Optional[str] = None
    if is_index:
        # index.md → up is the parent directory's index.md or 00-overview.md
        grandparent = parent_dir.parent
        if grandparent == notes_dir:
            # Top-level folder → up is 00-overview.md
            overview = notes_dir / "00-overview.md"
            if overview.is_file():
                up = _relative_link(note_path, overview)
        else:
            gp_index = grandparent / "index.md"
            if gp_index.is_file():
                up = _relative_link(note_path, gp_index)
    elif parent_dir == notes_dir:
        # Top-level file (not 00-overview itself)
        if note_path.name != "00-overview.md":
            overview = notes_dir / "00-overview.md"
            if overview.is_file():
                up = _relative_link(note_path, overview)
    else:
        # File inside a topic folder → up is the folder's index.md
        folder_index = parent_dir / "index.md"
        if folder_index.is_file() and folder_index.resolve() != note_path.resolve():
            up = _relative_link(note_path, folder_index)

    # Compute prev/next
    prev_link: Optional[str] = None
    next_link: Optional[str] = None
    if my_idx is not None:
        if my_idx > 0:
            prev_link = _relative_link(note_path, siblings[my_idx - 1]["path"])
        if my_idx < len(siblings) - 1:
            next_link = _relative_link(note_path, siblings[my_idx + 1]["path"])

    # Compute subtopics (for index.md only)
    subtopics: list[tuple[str, str]] = []
    if is_index:
        children = _build_level(parent_dir)
        for child in children:
            label = _label_from_path(child["path"])
            rel = _relative_link(note_path, child["path"])
            subtopics.append((label, rel))

    return {
        "up": up,
        "prev": prev_link,
        "next": next_link,
        "subtopics": subtopics,
        "is_index": is_index,
    }


def _relative_link(from_file: Path, to_file: Path) -> str:
    """Compute relative path from one file to another, as a link string."""
    try:
        rel = to_file.resolve().relative_to(from_file.resolve().parent)
        return "./" + str(rel)
    except ValueError:
        # Files in different directory branches — use os.path.relpath
        import os
        return os.path.relpath(to_file.resolve(), from_file.resolve().parent)


def _label_from_path(file_path: Path) -> str:
    """Generate a human-readable label from a note path.

    '01-api/index.md' → 'API'
    '01-endpoints.md' → 'Endpoints'
    '00-overview.md' → 'Overview'
    """
    if file_path.name == "index.md":
        # Use the parent directory name
        name = file_path.parent.name
    else:
        name = file_path.stem

    # Strip numeric prefix: 01-api → api
    stripped = re.sub(r"^\d+-", "", name)
    # Title-case and replace hyphens
    return stripped.replace("-", " ").title()


def format_nav_line(links: dict) -> str:
    """Format navigation links as a blockquote line.

    Returns the > **Navigation:** line.
    """
    parts: list[str] = []
    if links["up"]:
        parts.append(f"Up: [Parent]({links['up']})")
    if links["prev"]:
        parts.append(f"Prev: [Previous]({links['prev']})")
    if links["next"]:
        parts.append(f"Next: [Next]({links['next']})")

    if not parts:
        return ""

    return "> **Navigation:** " + " | ".join(parts)


def format_subtopics_line(subtopics: list[tuple[str, str]]) -> str:
    """Format sub-topics as a blockquote line.

    Returns the > **Sub-topics:** line, or empty string if no subtopics.
    """
    if not subtopics:
        return ""
    parts = [f"[{label}]({path})" for label, path in subtopics]
    return "> **Sub-topics:** " + " | ".join(parts)


def _find_frontmatter_end(lines: list[str]) -> int:
    """Find the line index of the closing --- of YAML frontmatter.

    Returns the index of the closing --- line, or -1 if no frontmatter.
    """
    if not lines or lines[0].strip() != "---":
        return -1

    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return i

    return -1


def insert_or_replace_nav(
    file_path: Path,
    nav_line: str,
    subtopics_line: str,
) -> bool:
    """Insert or replace navigation/sub-topics lines in a markdown file.

    - Matches lines starting with > **Navigation:** or > **Sub-topics:**
    - If found: replaces in-place
    - If not found: inserts after frontmatter (after closing ---)
    - If no frontmatter: inserts at the very top

    Returns True if the file was modified, False if no changes needed.
    """
    text = file_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Track indices of existing nav/subtopics lines
    nav_idx: Optional[int] = None
    sub_idx: Optional[int] = None

    for i, line in enumerate(lines):
        if NAV_PATTERN.match(line):
            nav_idx = i
        elif SUBTOPICS_PATTERN.match(line):
            sub_idx = i

    new_lines = list(lines)
    modified = False

    # Determine which lines to place
    lines_to_insert: list[str] = []
    if nav_line:
        lines_to_insert.append(nav_line)
    if subtopics_line:
        lines_to_insert.append(subtopics_line)

    if not lines_to_insert:
        # Nothing to insert — remove existing nav/subtopics lines if present
        indices_to_remove = sorted(
            [i for i in [nav_idx, sub_idx] if i is not None],
            reverse=True,
        )
        for idx in indices_to_remove:
            new_lines.pop(idx)
            modified = True
        if modified:
            file_path.write_text("\n".join(new_lines), encoding="utf-8")
        return modified

    # Replace existing lines
    if nav_idx is not None or sub_idx is not None:
        # Remove old lines (in reverse order to preserve indices)
        indices_to_remove = sorted(
            [i for i in [nav_idx, sub_idx] if i is not None],
            reverse=True,
        )
        insert_point = min(i for i in [nav_idx, sub_idx] if i is not None)
        for idx in indices_to_remove:
            new_lines.pop(idx)
        # Insert new lines at the earliest position
        for j, line in enumerate(lines_to_insert):
            new_lines.insert(insert_point + j, line)
        modified = True
    else:
        # Insert after frontmatter
        fm_end = _find_frontmatter_end(lines)
        if fm_end >= 0:
            insert_point = fm_end + 1
        else:
            insert_point = 0

        # Insert a blank line before nav if there isn't one
        if insert_point < len(new_lines) and new_lines[insert_point].strip():
            lines_to_insert.append("")

        for j, line in enumerate(lines_to_insert):
            new_lines.insert(insert_point + j, line)
        modified = True

    new_text = "\n".join(new_lines)
    if new_text == text:
        return False

    file_path.write_text(new_text, encoding="utf-8")
    return modified


def _collect_all_md_files(notes_dir: Path) -> list[Path]:
    """Collect all .md files in the notes directory, excluding RULES.md."""
    files: list[Path] = []
    for md_file in sorted(notes_dir.rglob("*.md")):
        if md_file.name in EXCLUDED_FILES:
            continue
        files.append(md_file)
    return files


def rebuild_all_nav_links(notes_dir: Path) -> list[str]:
    """Rebuild navigation links for all .md files in notes_dir.

    Returns a list of file paths that were modified.
    """
    modified_files: list[str] = []

    all_files = _collect_all_md_files(notes_dir)

    for md_file in all_files:
        links = compute_nav_links(md_file, notes_dir)

        nav_line = format_nav_line(links)
        subtopics_line = ""
        if links["is_index"]:
            subtopics_line = format_subtopics_line(links["subtopics"])

        was_modified = insert_or_replace_nav(md_file, nav_line, subtopics_line)
        if was_modified:
            modified_files.append(str(md_file))

    return modified_files
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_nav_links.py::TestNavPatterns ../tests/test_nav_links.py::TestBuildNotesTree -v
```

Expected: All 9 pattern and tree tests pass.

- [ ] **Step 3: Write failing tests for `compute_nav_links`**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_nav_links.py`:

```python
class TestComputeNavLinks:
    """Test navigation link computation for various file positions."""

    def _make_structure(self, tmp_path):
        """Create a standard test notes structure:

        notes/
          00-overview.md
          01-api/
            index.md
            01-endpoints.md
            02-middleware.md
          02-models/
            index.md
            01-schemas.md
        """
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("---\n---\n# Overview\n")

        api = notes / "01-api"
        api.mkdir()
        (api / "index.md").write_text("---\n---\n# API\n")
        (api / "01-endpoints.md").write_text("---\n---\n# Endpoints\n")
        (api / "02-middleware.md").write_text("---\n---\n# Middleware\n")

        models = notes / "02-models"
        models.mkdir()
        (models / "index.md").write_text("---\n---\n# Models\n")
        (models / "01-schemas.md").write_text("---\n---\n# Schemas\n")

        return notes

    def test_overview_has_no_up(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "00-overview.md", notes)
        assert links["up"] is None

    def test_overview_has_next_but_no_prev(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "00-overview.md", notes)
        assert links["prev"] is None
        assert links["next"] is not None
        assert "01-api/index.md" in links["next"]

    def test_index_up_points_to_overview(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "index.md", notes)
        assert links["up"] is not None
        assert "00-overview.md" in links["up"]

    def test_index_has_subtopics(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "index.md", notes)
        assert links["is_index"] is True
        assert len(links["subtopics"]) == 2
        labels = [s[0] for s in links["subtopics"]]
        assert "Endpoints" in labels
        assert "Middleware" in labels

    def test_child_note_up_points_to_index(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "01-endpoints.md", notes)
        assert links["up"] is not None
        assert "index.md" in links["up"]

    def test_child_note_prev_next(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "01-endpoints.md", notes)
        assert links["prev"] is None  # First child
        assert links["next"] is not None
        assert "02-middleware.md" in links["next"]

    def test_last_child_has_no_next(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "02-middleware.md", notes)
        assert links["prev"] is not None
        assert "01-endpoints.md" in links["prev"]
        assert links["next"] is None

    def test_sibling_folders_prev_next(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "index.md", notes)
        assert links["next"] is not None
        assert "02-models/index.md" in links["next"]

    def test_regular_note_not_index(self, tmp_path):
        notes = self._make_structure(tmp_path)
        links = compute_nav_links(notes / "01-api" / "01-endpoints.md", notes)
        assert links["is_index"] is False
        assert links["subtopics"] == []
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_nav_links.py::TestComputeNavLinks -v
```

Expected: All 9 tests pass.

- [ ] **Step 4: Write failing tests for `insert_or_replace_nav`**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_nav_links.py`:

```python
class TestInsertOrReplaceNav:
    """Test inserting and replacing navigation lines in markdown files."""

    def test_insert_after_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\nlast_updated: 2026-03-16\n---\n# Title\nContent.\n"
        )
        nav = '> **Navigation:** Up: [Parent](../index.md)'
        modified = insert_or_replace_nav(note, nav, "")
        assert modified is True
        text = note.read_text()
        lines = text.split("\n")
        # Nav should be right after closing ---
        fm_end = next(i for i, l in enumerate(lines[1:], 1) if l.strip() == "---")
        assert lines[fm_end + 1] == nav

    def test_insert_at_top_when_no_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("# Title\nContent.\n")
        nav = '> **Navigation:** Up: [Parent](../index.md)'
        modified = insert_or_replace_nav(note, nav, "")
        assert modified is True
        text = note.read_text()
        assert text.startswith(nav)

    def test_replace_existing_nav(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n---\n"
            "> **Navigation:** Up: [Old](../old.md)\n"
            "# Title\n"
        )
        new_nav = '> **Navigation:** Up: [Parent](../index.md) | Next: [Next](./02-next.md)'
        modified = insert_or_replace_nav(note, new_nav, "")
        assert modified is True
        text = note.read_text()
        assert new_nav in text
        assert "Old" not in text

    def test_replace_existing_subtopics(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n---\n"
            "> **Navigation:** Up: [Parent](../00-overview.md)\n"
            "> **Sub-topics:** [Old Topic](./01-old/index.md)\n"
            "# Title\n"
        )
        new_nav = '> **Navigation:** Up: [Parent](../00-overview.md)'
        new_sub = '> **Sub-topics:** [API](./01-api/index.md) | [Models](./02-models/index.md)'
        modified = insert_or_replace_nav(note, new_nav, new_sub)
        assert modified is True
        text = note.read_text()
        assert new_nav in text
        assert new_sub in text
        assert "Old Topic" not in text

    def test_no_modification_when_same(self, tmp_path):
        nav = '> **Navigation:** Up: [Parent](../index.md)'
        note = tmp_path / "note.md"
        note.write_text(f"---\n---\n{nav}\n# Title\n")
        modified = insert_or_replace_nav(note, nav, "")
        assert modified is False

    def test_case_insensitive_match(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n---\n"
            "> **navigation:** Up: [Old](../old.md)\n"
            "# Title\n"
        )
        new_nav = '> **Navigation:** Up: [Parent](../index.md)'
        modified = insert_or_replace_nav(note, new_nav, "")
        assert modified is True
        text = note.read_text()
        assert new_nav in text
        # Old lowercase version should be gone
        assert "navigation:" not in text.lower().replace(new_nav.lower(), "")
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_nav_links.py::TestInsertOrReplaceNav -v
```

Expected: All 6 tests pass.

- [ ] **Step 5: Write failing tests for `rebuild_all_nav_links` (integration tests)**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_nav_links.py`:

```python
class TestRebuildAllNavLinks:
    """Integration tests for full navigation rebuild."""

    def _make_structure(self, tmp_path):
        """Create a standard test notes structure."""
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "00-overview.md").write_text("---\n---\n# Overview\n")

        api = notes / "01-api"
        api.mkdir()
        (api / "index.md").write_text("---\n---\n# API\n")
        (api / "01-endpoints.md").write_text("---\n---\n# Endpoints\n")
        (api / "02-middleware.md").write_text("---\n---\n# Middleware\n")

        models = notes / "02-models"
        models.mkdir()
        (models / "index.md").write_text("---\n---\n# Models\n")
        (models / "01-schemas.md").write_text("---\n---\n# Schemas\n")

        return notes

    def test_all_files_get_nav(self, tmp_path):
        notes = self._make_structure(tmp_path)
        modified = rebuild_all_nav_links(notes)
        # All 6 files should be modified (none had nav before)
        assert len(modified) == 6

    def test_idempotent(self, tmp_path):
        notes = self._make_structure(tmp_path)
        # Run once
        rebuild_all_nav_links(notes)
        # Run again — should modify nothing
        modified = rebuild_all_nav_links(notes)
        assert modified == []

    def test_overview_gets_nav_with_next(self, tmp_path):
        notes = self._make_structure(tmp_path)
        rebuild_all_nav_links(notes)
        text = (notes / "00-overview.md").read_text()
        assert "> **Navigation:**" in text
        assert "Next:" in text
        assert "01-api/index.md" in text

    def test_index_gets_subtopics(self, tmp_path):
        notes = self._make_structure(tmp_path)
        rebuild_all_nav_links(notes)
        text = (notes / "01-api" / "index.md").read_text()
        assert "> **Sub-topics:**" in text
        assert "Endpoints" in text
        assert "Middleware" in text

    def test_regular_note_no_subtopics(self, tmp_path):
        notes = self._make_structure(tmp_path)
        rebuild_all_nav_links(notes)
        text = (notes / "01-api" / "01-endpoints.md").read_text()
        assert "> **Navigation:**" in text
        assert "Sub-topics" not in text

    def test_child_nav_links_correct(self, tmp_path):
        notes = self._make_structure(tmp_path)
        rebuild_all_nav_links(notes)

        endpoints_text = (notes / "01-api" / "01-endpoints.md").read_text()
        assert "Up:" in endpoints_text
        assert "index.md" in endpoints_text
        assert "Next:" in endpoints_text
        assert "02-middleware.md" in endpoints_text
        # First child has no Prev
        assert "Prev:" not in endpoints_text

        middleware_text = (notes / "01-api" / "02-middleware.md").read_text()
        assert "Up:" in middleware_text
        assert "Prev:" in middleware_text
        assert "01-endpoints.md" in middleware_text
        # Last child has no Next
        assert "Next:" not in middleware_text

    def test_rules_md_excluded(self, tmp_path):
        notes = self._make_structure(tmp_path)
        (notes / "RULES.md").write_text("# Rules\nDo not add nav here.\n")
        rebuild_all_nav_links(notes)
        rules_text = (notes / "RULES.md").read_text()
        assert "Navigation" not in rules_text

    def test_output_lists_modified_files(self, tmp_path):
        notes = self._make_structure(tmp_path)
        modified = rebuild_all_nav_links(notes)
        assert all(isinstance(f, str) for f in modified)
        assert all(f.endswith(".md") for f in modified)

    def test_handles_empty_notes_dir(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        modified = rebuild_all_nav_links(notes)
        assert modified == []
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_nav_links.py::TestRebuildAllNavLinks -v
```

Expected: All 9 tests pass.

- [ ] **Step 6: Write test for `format_nav_line` and `format_subtopics_line`**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_nav_links.py`:

```python
from scripts.nav_links import format_nav_line, format_subtopics_line


class TestFormatLines:
    """Test navigation line formatting."""

    def test_format_nav_all_links(self):
        links = {
            "up": "../index.md",
            "prev": "./01-prev.md",
            "next": "./03-next.md",
            "subtopics": [],
            "is_index": False,
        }
        result = format_nav_line(links)
        assert result == (
            "> **Navigation:** Up: [Parent](../index.md) | "
            "Prev: [Previous](./01-prev.md) | "
            "Next: [Next](./03-next.md)"
        )

    def test_format_nav_up_only(self):
        links = {
            "up": "../index.md",
            "prev": None,
            "next": None,
            "subtopics": [],
            "is_index": False,
        }
        result = format_nav_line(links)
        assert result == "> **Navigation:** Up: [Parent](../index.md)"

    def test_format_nav_no_links(self):
        links = {
            "up": None,
            "prev": None,
            "next": None,
            "subtopics": [],
            "is_index": False,
        }
        result = format_nav_line(links)
        assert result == ""

    def test_format_subtopics(self):
        subtopics = [
            ("Endpoints", "./01-endpoints.md"),
            ("Middleware", "./02-middleware.md"),
        ]
        result = format_subtopics_line(subtopics)
        assert result == (
            "> **Sub-topics:** [Endpoints](./01-endpoints.md) | "
            "[Middleware](./02-middleware.md)"
        )

    def test_format_subtopics_empty(self):
        result = format_subtopics_line([])
        assert result == ""
```

Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_nav_links.py::TestFormatLines -v
```

Expected: All 5 tests pass.

- [ ] **Step 7: Run full test suite and commit**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_nav_links.py -v
```

Expected: All 39 tests pass. Commit with message: `feat: add nav_links.py with deterministic navigation rebuilding, insert/replace logic, and idempotent operation`

---

---

## Task 6: render.py + Font Bundling + Tests

### Files

| File | Action |
|------|--------|
| `/Users/karthik/Documents/work/codebase-notes/scripts/render.py` | Create — Excalidraw JSON to PNG renderer |
| `/Users/karthik/Documents/work/codebase-notes/scripts/fonts/DejaVuSansMono.ttf` | Download — bundled monospace font for diagram text |
| `/Users/karthik/Documents/work/codebase-notes/tests/test_render.py` | Create — tests for renderer |

### Prerequisites

- Task 1 (pyproject.toml with Pillow dependency, `__init__.py`, `__main__.py`) must be complete
- Task 2 (repo_id.py) must be complete so `resolve_repo_id` / `get_notes_dir` helpers are available

### TDD Steps

- [ ] **Step 1: Write failing test for font loading and fallback**

Create `/Users/karthik/Documents/work/codebase-notes/tests/test_render.py`:

```python
"""Tests for scripts.render — Excalidraw JSON → PNG renderer."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.render import (
    load_font,
    FONT_DIR,
    FONT_FAMILY_MAP,
)


class TestFontLoading:
    """Test font resolution and fallback logic."""

    def test_font_dir_exists_at_expected_path(self):
        """The fonts/ directory should exist inside scripts/."""
        expected = Path(__file__).resolve().parent.parent / "scripts" / "fonts"
        assert FONT_DIR == expected

    def test_font_family_map_keys(self):
        """Font family map must cover Excalidraw families 1, 2, 3."""
        assert set(FONT_FAMILY_MAP.keys()) == {1, 2, 3}

    def test_load_font_returns_truetype_or_fallback(self):
        """load_font should return a usable font object (TrueType or fallback bitmap)."""
        from PIL import ImageFont

        font = load_font(font_family=3, font_size=16)
        # Must have getbbox (works for both TrueType and bitmap fallback)
        assert hasattr(font, "getbbox")

    def test_load_font_fallback_on_missing_file(self):
        """When the .ttf file is missing, load_font falls back to Pillow bitmap font with a warning."""
        from PIL import ImageFont

        with patch("scripts.render.FONT_DIR", Path("/nonexistent/fonts")):
            import warnings
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                font = load_font(font_family=3, font_size=16)
                assert len(w) >= 1
                assert "fallback" in str(w[0].message).lower() or "font" in str(w[0].message).lower()
            # Still returns a usable font
            assert hasattr(font, "getbbox")

    def test_load_font_family_2_tries_system_then_fallback(self):
        """Font family 2 (Helvetica) should try system Arial, then fall back to monospace."""
        font = load_font(font_family=2, font_size=14)
        assert hasattr(font, "getbbox")
```

Run the test (expect failure — module does not exist):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v -k "TestFontLoading"
```

- [ ] **Step 2: Implement font loading in render.py**

Create `/Users/karthik/Documents/work/codebase-notes/scripts/render.py`:

```python
"""Self-contained Excalidraw JSON → PNG renderer using Pillow.

Handles: rectangles, ellipses, diamonds, lines, arrows, text (bound + free).
Styling: fill colors, stroke colors, font sizes, arrow bindings.
Font bundling: DejaVu Sans Mono in scripts/fonts/, family mapping.
"""

import json
import math
import warnings
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Font handling
# ---------------------------------------------------------------------------

FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Excalidraw fontFamily → font file preference
FONT_FAMILY_MAP: dict[int, list[str]] = {
    1: ["DejaVuSansMono.ttf"],                          # Virgil → monospace
    2: ["Arial.ttf", "Helvetica.ttf", "DejaVuSansMono.ttf"],  # system → fallback
    3: ["DejaVuSansMono.ttf"],                          # Cascadia → monospace
}

# System font search paths (macOS + Linux)
_SYSTEM_FONT_DIRS = [
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path("/usr/share/fonts"),
    Path("/usr/share/fonts/truetype"),
    Path.home() / ".fonts",
]


def _find_font_file(candidates: list[str]) -> Optional[Path]:
    """Search bundled fonts dir, then system dirs for the first matching font file."""
    for name in candidates:
        # Check bundled dir first
        bundled = FONT_DIR / name
        if bundled.is_file():
            return bundled
        # Check system dirs
        for sys_dir in _SYSTEM_FONT_DIRS:
            sys_path = sys_dir / name
            if sys_path.is_file():
                return sys_path
    return None


def load_font(font_family: int = 3, font_size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font for the given Excalidraw font family and size.

    Falls back to Pillow's built-in bitmap font if no .ttf is found, with a warning.
    """
    candidates = FONT_FAMILY_MAP.get(font_family, FONT_FAMILY_MAP[3])
    font_path = _find_font_file(candidates)

    if font_path is not None:
        try:
            return ImageFont.truetype(str(font_path), font_size)
        except (OSError, IOError):
            warnings.warn(
                f"Font file {font_path} is corrupt or unreadable; falling back to bitmap font.",
                RuntimeWarning,
                stacklevel=2,
            )
            return ImageFont.load_default()

    warnings.warn(
        f"No font file found for family {font_family} (searched {candidates}); "
        "falling back to Pillow bitmap font.",
        RuntimeWarning,
        stacklevel=2,
    )
    return ImageFont.load_default()
```

Download and install the bundled font:

```bash
mkdir -p /Users/karthik/Documents/work/codebase-notes/scripts/fonts
curl -L -o /Users/karthik/Documents/work/codebase-notes/scripts/fonts/DejaVuSansMono.ttf \
  "https://github.com/dejavu-fonts/dejavu-fonts/raw/main/src/DejaVuSansMono.ttf"
```

If the URL is unavailable, use the system's DejaVu font (commonly at `/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf` on Linux or install via `brew install font-dejavu` on macOS) and copy it to `scripts/fonts/`.

Run tests (expect pass):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v -k "TestFontLoading"
```

- [ ] **Step 3: Write failing tests for shape rendering primitives**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_render.py`:

```python
from scripts.render import (
    render_element,
    compute_canvas_bounds,
    ExcalidrawRenderer,
)


class TestCanvasBounds:
    """Test bounding-box computation from element list."""

    def test_single_rectangle(self):
        elements = [{"type": "rectangle", "x": 10, "y": 20, "width": 100, "height": 50}]
        min_x, min_y, max_x, max_y = compute_canvas_bounds(elements)
        assert min_x <= 10
        assert min_y <= 20
        assert max_x >= 110
        assert max_y >= 70

    def test_multiple_elements(self):
        elements = [
            {"type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 50},
            {"type": "ellipse", "x": 200, "y": 200, "width": 60, "height": 40},
        ]
        min_x, min_y, max_x, max_y = compute_canvas_bounds(elements)
        assert min_x <= 0
        assert min_y <= 0
        assert max_x >= 260
        assert max_y >= 240

    def test_empty_elements_returns_defaults(self):
        min_x, min_y, max_x, max_y = compute_canvas_bounds([])
        # Should return some sensible default (e.g. 0,0,100,100)
        assert max_x > min_x
        assert max_y > min_y


class TestRenderElement:
    """Test individual element rendering onto a draw context."""

    def test_rectangle_draws_without_error(self):
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "rectangle",
            "x": 10, "y": 10, "width": 80, "height": 40,
            "strokeColor": "#000000",
            "backgroundColor": "#e3f2fd",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roundness": None,
        }
        # Should not raise
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})

    def test_ellipse_draws_without_error(self):
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "ellipse",
            "x": 10, "y": 10, "width": 80, "height": 60,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
        }
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})

    def test_diamond_draws_without_error(self):
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "diamond",
            "x": 10, "y": 10, "width": 80, "height": 80,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
        }
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})

    def test_text_draws_without_error(self):
        img = Image.new("RGB", (300, 200), "white")
        draw = ImageDraw.Draw(img)
        elem = {
            "type": "text",
            "x": 10, "y": 10, "width": 200, "height": 30,
            "text": "Hello World",
            "fontSize": 16,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#000000",
            "containerId": None,
        }
        render_element(draw, elem, offset_x=0, offset_y=0, elements_by_id={})
```

Run tests (expect failure — functions not yet defined):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v -k "TestCanvasBounds or TestRenderElement"
```

- [ ] **Step 4: Implement shape rendering and canvas bounds**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/render.py` (after the font section):

```python
# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _parse_color(color: str | None) -> str | None:
    """Normalize Excalidraw color strings. Return None for 'transparent'."""
    if not color or color == "transparent":
        return None
    return color


def _fill_and_stroke(elem: dict[str, Any]) -> tuple[str | None, str | None, int]:
    """Extract fill color, stroke color, and stroke width from an element."""
    fill = _parse_color(elem.get("backgroundColor"))
    stroke = _parse_color(elem.get("strokeColor", "#000000"))
    width = max(1, elem.get("strokeWidth", 1))
    # Only fill if fillStyle is 'solid' (skip hachure, cross-hatch for simplicity)
    if elem.get("fillStyle") not in ("solid",):
        fill = None
    return fill, stroke, width


# ---------------------------------------------------------------------------
# Canvas bounds
# ---------------------------------------------------------------------------

def compute_canvas_bounds(
    elements: list[dict[str, Any]], padding: int = 20
) -> tuple[float, float, float, float]:
    """Compute (min_x, min_y, max_x, max_y) encompassing all elements, with padding."""
    if not elements:
        return (0, 0, 100, 100)

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for elem in elements:
        if elem.get("isDeleted"):
            continue
        ex = elem.get("x", 0)
        ey = elem.get("y", 0)
        ew = elem.get("width", 0)
        eh = elem.get("height", 0)

        # For lines/arrows, width/height may be 0; use points instead
        if elem.get("type") in ("line", "arrow") and elem.get("points"):
            for px, py in elem["points"]:
                min_x = min(min_x, ex + px)
                min_y = min(min_y, ey + py)
                max_x = max(max_x, ex + px)
                max_y = max(max_y, ey + py)
        else:
            min_x = min(min_x, ex)
            min_y = min(min_y, ey)
            max_x = max(max_x, ex + ew)
            max_y = max(max_y, ey + eh)

    if min_x == float("inf"):
        return (0, 0, 100, 100)

    return (min_x - padding, min_y - padding, max_x + padding, max_y + padding)


# ---------------------------------------------------------------------------
# Element renderers
# ---------------------------------------------------------------------------

def _draw_rectangle(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float
) -> None:
    fill, stroke, width = _fill_and_stroke(elem)
    x, y = elem["x"] - ox, elem["y"] - oy
    w, h = elem["width"], elem["height"]
    coords = [x, y, x + w, y + h]
    draw.rectangle(coords, fill=fill, outline=stroke, width=width)


def _draw_ellipse(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float
) -> None:
    fill, stroke, width = _fill_and_stroke(elem)
    x, y = elem["x"] - ox, elem["y"] - oy
    w, h = elem["width"], elem["height"]
    draw.ellipse([x, y, x + w, y + h], fill=fill, outline=stroke, width=width)


def _draw_diamond(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float
) -> None:
    fill, stroke, width = _fill_and_stroke(elem)
    x, y = elem["x"] - ox, elem["y"] - oy
    w, h = elem["width"], elem["height"]
    cx, cy = x + w / 2, y + h / 2
    points = [(cx, y), (x + w, cy), (cx, y + h), (x, cy)]
    draw.polygon(points, fill=fill, outline=stroke)
    if width > 1 and stroke:
        draw.line(points + [points[0]], fill=stroke, width=width)


def _draw_line_or_arrow(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float,
    elements_by_id: dict[str, dict],
) -> None:
    _, stroke, width = _fill_and_stroke(elem)
    stroke = stroke or "#000000"
    bx, by = elem["x"] - ox, elem["y"] - oy
    points = elem.get("points", [])
    if len(points) < 2:
        return
    xy = [(bx + px, by + py) for px, py in points]
    draw.line(xy, fill=stroke, width=width)

    # Arrowhead for type == "arrow"
    if elem.get("type") == "arrow" and len(xy) >= 2:
        _draw_arrowhead(draw, xy[-2], xy[-1], stroke, width)


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    p1: tuple[float, float],
    p2: tuple[float, float],
    color: str,
    width: int,
) -> None:
    """Draw a simple arrowhead at p2 pointing from p1 to p2."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return
    # Normalize
    udx, udy = dx / length, dy / length
    arrow_len = max(10, width * 4)
    # Two wing points
    angle = math.pi / 6  # 30 degrees
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    lx = p2[0] - arrow_len * (udx * cos_a - udy * sin_a)
    ly = p2[1] - arrow_len * (udy * cos_a + udx * sin_a)
    rx = p2[0] - arrow_len * (udx * cos_a + udy * sin_a)
    ry = p2[1] - arrow_len * (udy * cos_a - udx * sin_a)
    draw.polygon([(p2[0], p2[1]), (lx, ly), (rx, ry)], fill=color)


def _draw_text(
    draw: ImageDraw.ImageDraw, elem: dict, ox: float, oy: float,
    elements_by_id: dict[str, dict],
) -> None:
    """Draw a text element. If it has a containerId, center within that container."""
    text = elem.get("text", "")
    if not text:
        return
    font_family = elem.get("fontFamily", 3)
    font_size = elem.get("fontSize", 16)
    font = load_font(font_family, font_size)
    color = _parse_color(elem.get("strokeColor")) or "#000000"

    container_id = elem.get("containerId")
    if container_id and container_id in elements_by_id:
        container = elements_by_id[container_id]
        cx = container["x"] - ox
        cy = container["y"] - oy
        cw = container["width"]
        ch = container["height"]
        # Measure text
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # Center in container
        tx = cx + (cw - tw) / 2
        ty = cy + (ch - th) / 2
    else:
        tx = elem["x"] - ox
        ty = elem["y"] - oy

    # Handle multiline
    lines = text.split("\n")
    line_height = font_size * 1.2
    for i, line in enumerate(lines):
        if elem.get("textAlign") == "center" and not container_id:
            bbox = font.getbbox(line)
            lw = bbox[2] - bbox[0]
            elem_w = elem.get("width", lw)
            lx = tx + (elem_w - lw) / 2
        else:
            lx = tx
        draw.text((lx, ty + i * line_height), line, fill=color, font=font)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def render_element(
    draw: ImageDraw.ImageDraw,
    elem: dict[str, Any],
    offset_x: float,
    offset_y: float,
    elements_by_id: dict[str, dict],
) -> None:
    """Render a single Excalidraw element onto the draw context."""
    if elem.get("isDeleted"):
        return
    etype = elem.get("type", "")
    if etype == "rectangle":
        _draw_rectangle(draw, elem, offset_x, offset_y)
    elif etype == "ellipse":
        _draw_ellipse(draw, elem, offset_x, offset_y)
    elif etype == "diamond":
        _draw_diamond(draw, elem, offset_x, offset_y)
    elif etype in ("line", "arrow"):
        _draw_line_or_arrow(draw, elem, offset_x, offset_y, elements_by_id)
    elif etype == "text":
        _draw_text(draw, elem, offset_x, offset_y, elements_by_id)
    # Silently ignore unknown types (frame, freedraw, image, etc.)
```

Run tests (expect pass):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v -k "TestCanvasBounds or TestRenderElement"
```

- [ ] **Step 5: Write failing tests for ExcalidrawRenderer (full JSON to PNG pipeline)**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_render.py`:

```python
SIMPLE_EXCALIDRAW = {
    "type": "excalidraw",
    "version": 2,
    "source": "test",
    "elements": [
        {
            "id": "rect1",
            "type": "rectangle",
            "x": 50, "y": 50, "width": 200, "height": 100,
            "strokeColor": "#000000",
            "backgroundColor": "#e3f2fd",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roughness": 0,
            "roundness": None,
            "isDeleted": False,
        },
        {
            "id": "text1",
            "type": "text",
            "x": 80, "y": 80, "width": 140, "height": 30,
            "text": "Service A",
            "fontSize": 20,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#000000",
            "containerId": "rect1",
            "isDeleted": False,
        },
        {
            "id": "rect2",
            "type": "rectangle",
            "x": 400, "y": 50, "width": 200, "height": 100,
            "strokeColor": "#000000",
            "backgroundColor": "#c8e6c9",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roughness": 0,
            "roundness": None,
            "isDeleted": False,
        },
        {
            "id": "text2",
            "type": "text",
            "x": 430, "y": 80, "width": 140, "height": 30,
            "text": "Service B",
            "fontSize": 20,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#000000",
            "containerId": "rect2",
            "isDeleted": False,
        },
        {
            "id": "arrow1",
            "type": "arrow",
            "x": 250, "y": 100,
            "width": 150, "height": 0,
            "points": [[0, 0], [150, 0]],
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "roughness": 0,
            "isDeleted": False,
            "startBinding": {"elementId": "rect1", "focus": 0, "gap": 1},
            "endBinding": {"elementId": "rect2", "focus": 0, "gap": 1},
        },
    ],
    "appState": {"viewBackgroundColor": "#ffffff"},
}


class TestExcalidrawRenderer:
    """Integration tests: full JSON → PNG pipeline."""

    def test_render_json_to_image(self):
        renderer = ExcalidrawRenderer()
        img = renderer.render(SIMPLE_EXCALIDRAW)
        assert isinstance(img, Image.Image)
        assert img.width > 0
        assert img.height > 0

    def test_render_produces_reasonable_dimensions(self):
        renderer = ExcalidrawRenderer()
        img = renderer.render(SIMPLE_EXCALIDRAW)
        # Canvas should encompass all elements (50..600 x, 50..150 y) + padding
        assert img.width >= 500
        assert img.height >= 80
        # But not absurdly large
        assert img.width < 2000
        assert img.height < 1000

    def test_render_white_background(self):
        renderer = ExcalidrawRenderer()
        img = renderer.render(SIMPLE_EXCALIDRAW)
        # Top-left corner should be white (background)
        pixel = img.getpixel((0, 0))
        assert pixel == (255, 255, 255) or pixel == (255, 255, 255, 255)

    def test_render_to_file(self, tmp_path):
        renderer = ExcalidrawRenderer()
        out_path = tmp_path / "test_output.png"
        renderer.render_to_file(SIMPLE_EXCALIDRAW, out_path)
        assert out_path.exists()
        assert out_path.stat().st_size > 100  # Non-trivial PNG

    def test_render_empty_elements(self):
        data = {"type": "excalidraw", "version": 2, "elements": [], "appState": {}}
        renderer = ExcalidrawRenderer()
        img = renderer.render(data)
        assert isinstance(img, Image.Image)

    def test_render_deleted_elements_skipped(self):
        data = {
            "type": "excalidraw", "version": 2, "elements": [
                {"id": "del1", "type": "rectangle", "x": 0, "y": 0,
                 "width": 100, "height": 100, "isDeleted": True,
                 "strokeColor": "#000000", "backgroundColor": "#ff0000",
                 "fillStyle": "solid", "strokeWidth": 1},
            ],
            "appState": {},
        }
        renderer = ExcalidrawRenderer()
        img = renderer.render(data)
        # Should produce only a small default-size canvas
        assert isinstance(img, Image.Image)
```

Run tests (expect failure — `ExcalidrawRenderer` not yet implemented):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v -k "TestExcalidrawRenderer"
```

- [ ] **Step 6: Implement ExcalidrawRenderer class**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/render.py`:

```python
# ---------------------------------------------------------------------------
# ExcalidrawRenderer — main entry point
# ---------------------------------------------------------------------------

class ExcalidrawRenderer:
    """Renders Excalidraw JSON data to a Pillow Image."""

    def render(self, data: dict[str, Any]) -> Image.Image:
        """Render Excalidraw JSON dict to a Pillow Image.

        Args:
            data: Parsed Excalidraw JSON with 'elements' and optional 'appState'.

        Returns:
            PIL Image with the rendered diagram.
        """
        elements = [e for e in data.get("elements", []) if not e.get("isDeleted")]
        app_state = data.get("appState", {})
        bg_color = app_state.get("viewBackgroundColor", "#ffffff")

        min_x, min_y, max_x, max_y = compute_canvas_bounds(elements)
        width = max(1, int(max_x - min_x))
        height = max(1, int(max_y - min_y))

        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Index elements by ID for text container lookups
        elements_by_id: dict[str, dict] = {}
        for elem in data.get("elements", []):
            eid = elem.get("id")
            if eid:
                elements_by_id[eid] = elem

        # Render shapes first, then text on top
        for elem in elements:
            if elem.get("type") != "text":
                render_element(draw, elem, min_x, min_y, elements_by_id)
        for elem in elements:
            if elem.get("type") == "text":
                render_element(draw, elem, min_x, min_y, elements_by_id)

        return img

    def render_to_file(self, data: dict[str, Any], output_path: Path) -> None:
        """Render Excalidraw JSON and save as PNG.

        Args:
            data: Parsed Excalidraw JSON.
            output_path: Path to write the PNG file.
        """
        img = self.render(data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "PNG")
```

Run tests (expect pass):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v -k "TestExcalidrawRenderer"
```

- [ ] **Step 7: Write failing tests for the CLI entry point (find + render stale .excalidraw files)**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_render.py`:

```python
from scripts.render import find_and_render_excalidraw


class TestFindAndRender:
    """Test the CLI-facing function that finds .excalidraw files and renders stale ones."""

    def test_renders_new_excalidraw_file(self, tmp_path):
        """A .excalidraw without a corresponding .png should be rendered."""
        excalidraw_file = tmp_path / "diagram.excalidraw"
        excalidraw_file.write_text(json.dumps(SIMPLE_EXCALIDRAW))

        results = find_and_render_excalidraw(tmp_path)
        png_file = tmp_path / "diagram.png"
        assert png_file.exists()
        assert len(results["rendered"]) == 1
        assert results["rendered"][0] == str(png_file)

    def test_skips_fresh_png(self, tmp_path):
        """If .png is newer than .excalidraw, skip rendering."""
        excalidraw_file = tmp_path / "diagram.excalidraw"
        excalidraw_file.write_text(json.dumps(SIMPLE_EXCALIDRAW))
        png_file = tmp_path / "diagram.png"
        # Pre-render
        renderer = ExcalidrawRenderer()
        renderer.render_to_file(SIMPLE_EXCALIDRAW, png_file)
        # Ensure png mtime >= excalidraw mtime
        import time
        time.sleep(0.05)
        os.utime(png_file, None)  # touch to make it newer

        results = find_and_render_excalidraw(tmp_path)
        assert len(results["rendered"]) == 0
        assert len(results["skipped"]) == 1

    def test_re_renders_stale_png(self, tmp_path):
        """If .excalidraw is newer than .png, re-render."""
        excalidraw_file = tmp_path / "diagram.excalidraw"
        png_file = tmp_path / "diagram.png"
        # Create PNG first, then excalidraw (so excalidraw is newer)
        png_file.write_bytes(b"old png data")
        import time
        time.sleep(0.05)
        excalidraw_file.write_text(json.dumps(SIMPLE_EXCALIDRAW))

        results = find_and_render_excalidraw(tmp_path)
        assert len(results["rendered"]) == 1
        # PNG should now be a valid image
        img = Image.open(png_file)
        assert img.width > 0

    def test_warns_on_invalid_json(self, tmp_path):
        """Invalid JSON should warn, not error."""
        bad_file = tmp_path / "broken.excalidraw"
        bad_file.write_text("not valid json {{{")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            results = find_and_render_excalidraw(tmp_path)
            assert len(results["errors"]) == 1
            assert len(w) >= 1

    def test_finds_in_subdirectories(self, tmp_path):
        """Should recursively find .excalidraw files in subdirs."""
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        (subdir / "nested.excalidraw").write_text(json.dumps(SIMPLE_EXCALIDRAW))

        results = find_and_render_excalidraw(tmp_path)
        assert len(results["rendered"]) == 1
        assert (subdir / "nested.png").exists()
```

Run tests (expect failure — `find_and_render_excalidraw` not defined):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v -k "TestFindAndRender"
```

- [ ] **Step 8: Implement find_and_render_excalidraw**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/render.py`:

```python
# ---------------------------------------------------------------------------
# CLI entry point: find and render stale .excalidraw files
# ---------------------------------------------------------------------------

def find_and_render_excalidraw(
    notes_dir: Path,
) -> dict[str, list[str]]:
    """Find all .excalidraw files under notes_dir and render stale ones to PNG.

    Returns dict with keys: 'rendered', 'skipped', 'errors'.
    """
    results: dict[str, list[str]] = {"rendered": [], "skipped": [], "errors": []}

    excalidraw_files = sorted(notes_dir.rglob("*.excalidraw"))
    renderer = ExcalidrawRenderer()

    for exc_path in excalidraw_files:
        png_path = exc_path.with_suffix(".png")
        try:
            # Check staleness
            if png_path.exists():
                exc_mtime = exc_path.stat().st_mtime
                png_mtime = png_path.stat().st_mtime
                if png_mtime >= exc_mtime:
                    results["skipped"].append(str(png_path))
                    continue

            # Parse and render
            raw = exc_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            renderer.render_to_file(data, png_path)
            results["rendered"].append(str(png_path))

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            warnings.warn(
                f"Failed to render {exc_path}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            results["errors"].append(str(exc_path))
        except Exception as exc:
            warnings.warn(
                f"Unexpected error rendering {exc_path}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            results["errors"].append(str(exc_path))

    return results


def run_render_command(repo_id: str | None = None) -> None:
    """CLI handler for the 'render' command."""
    from scripts.repo_id import resolve_repo_id, get_notes_dir

    rid = repo_id or resolve_repo_id()
    notes_dir = get_notes_dir(rid)

    if not notes_dir.exists():
        print(f"Notes directory not found: {notes_dir}")
        return

    results = find_and_render_excalidraw(notes_dir)

    if results["rendered"]:
        print(f"Rendered {len(results['rendered'])} diagram(s):")
        for p in results["rendered"]:
            print(f"  ✓ {p}")
    if results["skipped"]:
        print(f"Skipped {len(results['skipped'])} fresh diagram(s)")
    if results["errors"]:
        print(f"WARNING: {len(results['errors'])} diagram(s) failed to render:")
        for p in results["errors"]:
            print(f"  ✗ {p}")
```

Run all render tests (expect pass):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v
```

- [ ] **Step 9: Register `render` command in `__main__.py`**

Add the render subcommand to `/Users/karthik/Documents/work/codebase-notes/scripts/__main__.py` (in the argparse setup section):

```python
    # In the subparsers section, add:
    render_parser = subparsers.add_parser("render", help="Render .excalidraw → .png")
    render_parser.add_argument("--repo-id", default=None, help="Override repo ID")
```

And in the dispatch section:

```python
    elif args.command == "render":
        from scripts.render import run_render_command
        run_render_command(repo_id=args.repo_id)
```

- [ ] **Step 10: Run full test suite and commit**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py -v
```

Commit message: `feat: add render.py — self-contained Excalidraw JSON to PNG renderer with font bundling`

---

## Task 7: commits.py + Tests

### Files

| File | Action |
|------|--------|
| `/Users/karthik/Documents/work/codebase-notes/scripts/commits.py` | Create — git log extraction, grouping, markdown output |
| `/Users/karthik/Documents/work/codebase-notes/tests/test_commits.py` | Create — tests with mocked git subprocess |

### Prerequisites

- Task 1 (pyproject.toml with pyyaml, `__init__.py`, `__main__.py`) must be complete
- Task 2 (repo_id.py with `resolve_repo_id` / `get_notes_dir`) must be complete

### TDD Steps

- [ ] **Step 1: Write failing tests for git log parsing**

Create `/Users/karthik/Documents/work/codebase-notes/tests/test_commits.py`:

```python
"""Tests for scripts.commits — git log extraction and markdown generation."""

import os
import textwrap
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.commits import (
    parse_git_log_output,
    Commit,
    group_commits_by_author,
    group_by_path_prefix,
)


# Sample git log output matching --format="%H|%an|%ae|%ad|%s"
SAMPLE_GIT_LOG = textwrap.dedent("""\
    abc1234abc1234abc1234abc1234abc1234abc1234|Alice Smith|alice@company.com|Mon Mar 10 14:30:00 2026 -0700|Refactor auth middleware to JWT
    def5678def5678def5678def5678def5678def5678|Alice Smith|alice@company.com|Wed Mar 5 09:15:00 2026 -0700|Add rate limiting to /users endpoint
    111aaaa111aaaa111aaaa111aaaa111aaaa111aaaa|Bob Jones|bob@company.com|Tue Mar 11 10:00:00 2026 -0700|Fix database connection pooling
    222bbbb222bbbb222bbbb222bbbb222bbbb222bbbb|Alice Smith|alice@company.com|Mon Mar 3 16:45:00 2026 -0700|Update API documentation
    333cccc333cccc333cccc333cccc333cccc333cccc|Bob Jones|bob@company.com|Fri Feb 28 11:20:00 2026 -0700|Add user profile endpoints
""").strip()


class TestParseGitLog:
    """Test parsing raw git log output into Commit objects."""

    def test_parses_all_commits(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        assert len(commits) == 5

    def test_commit_fields(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        c = commits[0]
        assert isinstance(c, Commit)
        assert c.hash == "abc1234abc1234abc1234abc1234abc1234abc1234"
        assert c.author == "Alice Smith"
        assert c.email == "alice@company.com"
        assert "Refactor auth middleware" in c.subject

    def test_handles_empty_input(self):
        commits = parse_git_log_output("")
        assert commits == []

    def test_handles_malformed_lines(self):
        """Lines that don't have exactly 5 pipe-separated fields are skipped."""
        bad_input = "not|enough|fields\ngood_hash|Author|email@x.com|Mon Mar 10 14:30:00 2026 -0700|Subject"
        commits = parse_git_log_output(bad_input)
        assert len(commits) == 1

    def test_date_parsed(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        c = commits[0]
        assert isinstance(c.date, str)
        assert "2026" in c.date


class TestGroupByAuthor:
    """Test grouping commits by author name."""

    def test_groups_correctly(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        grouped = group_commits_by_author(commits)
        assert "Alice Smith" in grouped
        assert "Bob Jones" in grouped
        assert len(grouped["Alice Smith"]) == 3
        assert len(grouped["Bob Jones"]) == 2

    def test_empty_list(self):
        grouped = group_commits_by_author([])
        assert grouped == {}


class TestGroupByPathPrefix:
    """Test grouping commits by path prefix."""

    def test_default_depth_2(self):
        # Simulated file paths from git log
        paths = [
            "src/api/routes.py",
            "src/api/middleware.py",
            "src/models/user.py",
            "docs/readme.md",
        ]
        grouped = group_by_path_prefix(paths, depth=2)
        assert "src/api" in grouped
        assert "src/models" in grouped
        assert "docs" in grouped  # only 1 level deep, so just "docs"

    def test_depth_1(self):
        paths = ["src/api/routes.py", "src/models/user.py", "docs/readme.md"]
        grouped = group_by_path_prefix(paths, depth=1)
        assert "src" in grouped
        assert "docs" in grouped
        assert len(grouped) == 2

    def test_root_level_files(self):
        paths = ["README.md", "setup.py"]
        grouped = group_by_path_prefix(paths, depth=2)
        # Root-level files group under "." or "root"
        assert len(grouped) == 1
```

Run tests (expect failure — module does not exist):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_commits.py -v -k "TestParseGitLog or TestGroupByAuthor or TestGroupByPathPrefix"
```

- [ ] **Step 2: Implement core data parsing and grouping**

Create `/Users/karthik/Documents/work/codebase-notes/scripts/commits.py`:

```python
"""Git commit history extraction, grouping, and markdown generation.

Runs git log, groups commits by author and path prefix, outputs markdown
files to ~/.claude/repo_notes/<repo_id>/commits/<author>/<path-slug>.md.
"""

import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class Commit:
    """A single parsed git commit."""
    hash: str
    author: str
    email: str
    date: str
    subject: str


def parse_git_log_output(raw: str) -> list[Commit]:
    """Parse output of git log --format='%H|%an|%ae|%ad|%s' into Commit objects.

    Lines that don't match the expected 5-field pipe format are silently skipped.
    """
    commits: list[Commit] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|", maxsplit=4)
        if len(parts) != 5:
            continue
        commits.append(Commit(
            hash=parts[0].strip(),
            author=parts[1].strip(),
            email=parts[2].strip(),
            date=parts[3].strip(),
            subject=parts[4].strip(),
        ))
    return commits


def group_commits_by_author(commits: list[Commit]) -> dict[str, list[Commit]]:
    """Group a list of commits by author name."""
    grouped: dict[str, list[Commit]] = defaultdict(list)
    for c in commits:
        grouped[c.author].append(c)
    return dict(grouped)


def group_by_path_prefix(paths: list[str], depth: int = 2) -> dict[str, list[str]]:
    """Group file paths by their prefix up to `depth` directory levels.

    Files at the root level are grouped under '.'.
    """
    grouped: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        parts = Path(p).parts
        if len(parts) <= depth:
            prefix = str(Path(*parts[:-1])) if len(parts) > 1 else "."
        else:
            prefix = str(Path(*parts[:depth]))
        grouped[prefix].append(p)
    return dict(grouped)
```

Run tests (expect pass):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_commits.py -v -k "TestParseGitLog or TestGroupByAuthor or TestGroupByPathPrefix"
```

- [ ] **Step 3: Write failing tests for markdown generation**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_commits.py`:

```python
from scripts.commits import (
    generate_commit_markdown,
    path_to_slug,
    parse_frontmatter,
    merge_commits_into_existing,
)


class TestPathToSlug:
    """Test path-to-filename slug conversion."""

    def test_simple_path(self):
        assert path_to_slug("src/api") == "src-api"

    def test_deep_path(self):
        assert path_to_slug("src/api/v2") == "src-api-v2"

    def test_root_path(self):
        assert path_to_slug(".") == "root"

    def test_strips_slashes(self):
        assert path_to_slug("src/api/") == "src-api"


class TestGenerateCommitMarkdown:
    """Test markdown output generation."""

    def test_produces_valid_frontmatter(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        alice_commits = [c for c in commits if c.author == "Alice Smith"]
        md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=alice_commits,
            date_range="2026-02-18 to 2026-03-18",
        )
        # Should start with YAML frontmatter
        assert md.startswith("---\n")
        # Parse frontmatter
        fm = parse_frontmatter(md)
        assert fm["author"] == "Alice Smith"
        assert fm["author_email"] == "alice@company.com"
        assert fm["path_filter"] == "src/api/"
        assert "2026-02-18" in fm["date_range"]
        assert "last_updated" in fm

    def test_contains_commit_table(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        alice_commits = [c for c in commits if c.author == "Alice Smith"]
        md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=alice_commits,
            date_range="2026-02-18 to 2026-03-18",
        )
        assert "| Date | Message |" in md  # table header
        assert "Refactor auth middleware" in md
        assert "Add rate limiting" in md

    def test_contains_summary_placeholder(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter=".",
            commits=commits[:1],
            date_range="2026-03-18 to 2026-03-18",
        )
        assert "## Summary" in md

    def test_heading_format(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        md = generate_commit_markdown(
            author="Bob Jones",
            email="bob@company.com",
            path_filter="src/models/",
            commits=commits[-1:],
            date_range="2026-02-28 to 2026-02-28",
        )
        assert "# Bob Jones" in md


class TestMergeCommits:
    """Test deduplication when merging into existing markdown."""

    def test_merge_deduplicates_by_hash(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        existing_md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=commits[:2],
            date_range="2026-03-05 to 2026-03-10",
        )
        # Now merge with overlapping + new commits
        all_alice = [c for c in commits if c.author == "Alice Smith"]
        merged_md = merge_commits_into_existing(
            existing_md=existing_md,
            new_commits=all_alice,
            date_range="2026-03-03 to 2026-03-10",
        )
        # Should have all 3 unique Alice commits, not 2 + 3 = 5
        hash_count = merged_md.count("abc1234abc1234")
        assert hash_count == 1  # not duplicated

    def test_merge_preserves_summary_section(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        existing_md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=commits[:1],
            date_range="2026-03-10 to 2026-03-10",
        )
        # Simulate Claude having filled in the summary
        existing_md = existing_md.replace(
            "## Summary\n\n[Claude-generated narrative summary — to be filled by Claude]\n",
            "## Summary\n\nAlice refactored the auth middleware to use JWT tokens.\n",
        )
        merged_md = merge_commits_into_existing(
            existing_md=existing_md,
            new_commits=commits[:2],
            date_range="2026-03-05 to 2026-03-10",
        )
        assert "Alice refactored the auth middleware" in merged_md

    def test_merge_updates_frontmatter_dates(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        existing_md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=commits[:1],
            date_range="2026-03-10 to 2026-03-10",
        )
        merged_md = merge_commits_into_existing(
            existing_md=existing_md,
            new_commits=commits[:2],
            date_range="2026-03-05 to 2026-03-10",
        )
        fm = parse_frontmatter(merged_md)
        assert "2026-03-05" in fm["date_range"]
```

Run tests (expect failure):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_commits.py -v -k "TestPathToSlug or TestGenerateCommitMarkdown or TestMergeCommits"
```

- [ ] **Step 4: Implement markdown generation and merge logic**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/commits.py`:

```python
# ---------------------------------------------------------------------------
# Slug + frontmatter helpers
# ---------------------------------------------------------------------------

def path_to_slug(path: str) -> str:
    """Convert a path like 'src/api/' to a filename slug like 'src-api'."""
    cleaned = path.strip("/").strip()
    if not cleaned or cleaned == ".":
        return "root"
    return re.sub(r"[/\\]+", "-", cleaned)


def parse_frontmatter(md: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a markdown string (between --- delimiters)."""
    match = re.match(r"^---\n(.*?)\n---", md, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def _format_date_short(date_str: str) -> str:
    """Extract a short date like '2026-03-10' from git's verbose date format."""
    # Try to parse git's default date format
    for fmt in ("%a %b %d %H:%M:%S %Y %z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Fallback: return as-is truncated
    return date_str.strip()[:10]


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def generate_commit_markdown(
    author: str,
    email: str,
    path_filter: str,
    commits: list[Commit],
    date_range: str,
) -> str:
    """Generate a complete markdown file with frontmatter, commit table, and summary placeholder.

    Args:
        author: Author display name.
        email: Author email.
        path_filter: Path scope (e.g., 'src/api/').
        commits: List of Commit objects to include.
        date_range: Human-readable date range string (e.g., '2026-02-18 to 2026-03-18').

    Returns:
        Complete markdown string.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    path_display = path_filter if path_filter and path_filter != "." else "(all paths)"

    frontmatter = yaml.dump(
        {
            "author": author,
            "author_email": email,
            "path_filter": path_filter,
            "date_range": date_range,
            "last_updated": today,
        },
        default_flow_style=False,
        sort_keys=False,
    ).strip()

    lines = [
        f"---\n{frontmatter}\n---",
        f"# {author} — {path_display}",
        "",
        "## Summary",
        "",
        "[Claude-generated narrative summary — to be filled by Claude]",
        "",
        "## Commits",
        "",
        "| Date | Message | Hash |",
        "|------|---------|------|",
    ]

    for c in commits:
        short_date = _format_date_short(c.date)
        short_hash = c.hash[:8]
        # Escape pipes in subject
        safe_subject = c.subject.replace("|", "\\|")
        lines.append(f"| {short_date} | {safe_subject} | `{short_hash}` |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Merge / deduplication
# ---------------------------------------------------------------------------

def _extract_commit_hashes_from_table(md: str) -> set[str]:
    """Extract all commit hashes (short, 8-char) from the markdown commit table."""
    hashes: set[str] = set()
    for match in re.finditer(r"`([0-9a-f]{8})`", md):
        hashes.add(match.group(1))
    return hashes


def _extract_sections(md: str) -> dict[str, str]:
    """Split markdown into: 'frontmatter', 'summary', 'commits_header', 'commits_table', 'rest'."""
    sections: dict[str, str] = {}

    # Frontmatter
    fm_match = re.match(r"^(---\n.*?\n---)\n", md, re.DOTALL)
    if fm_match:
        sections["frontmatter"] = fm_match.group(1)
        remainder = md[fm_match.end():]
    else:
        sections["frontmatter"] = ""
        remainder = md

    # Split at ## Summary and ## Commits
    summary_match = re.search(r"(## Summary\n.*?)(?=\n## Commits)", remainder, re.DOTALL)
    if summary_match:
        sections["pre_summary"] = remainder[:summary_match.start()]
        sections["summary"] = summary_match.group(1)
    else:
        sections["pre_summary"] = remainder
        sections["summary"] = "## Summary\n\n[Claude-generated narrative summary — to be filled by Claude]\n"

    commits_match = re.search(r"(## Commits\n.*)", remainder, re.DOTALL)
    if commits_match:
        sections["commits"] = commits_match.group(1)
    else:
        sections["commits"] = ""

    return sections


def merge_commits_into_existing(
    existing_md: str,
    new_commits: list[Commit],
    date_range: str,
) -> str:
    """Merge new commits into an existing markdown file, deduplicating by hash.

    Preserves the existing Summary section (which Claude may have written).
    Updates frontmatter date_range and last_updated.
    """
    existing_hashes = _extract_commit_hashes_from_table(existing_md)
    sections = _extract_sections(existing_md)

    # Filter to only truly new commits
    unique_new = [c for c in new_commits if c.hash[:8] not in existing_hashes]

    # Build new table rows from unique new commits
    new_rows: list[str] = []
    for c in unique_new:
        short_date = _format_date_short(c.date)
        short_hash = c.hash[:8]
        safe_subject = c.subject.replace("|", "\\|")
        new_rows.append(f"| {short_date} | {safe_subject} | `{short_hash}` |")

    # Rebuild commits section: existing table + new rows
    commits_section = sections.get("commits", "")
    if new_rows:
        # Append new rows before the trailing empty line
        commits_section = commits_section.rstrip("\n")
        commits_section += "\n" + "\n".join(new_rows) + "\n"

    # Update frontmatter
    fm = parse_frontmatter(existing_md)
    fm["date_range"] = date_range
    fm["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    new_frontmatter = "---\n" + yaml.dump(fm, default_flow_style=False, sort_keys=False).strip() + "\n---"

    # Reassemble
    result = (
        new_frontmatter + "\n"
        + sections.get("pre_summary", "")
        + sections["summary"] + "\n"
        + commits_section
    )
    return result
```

Run tests (expect pass):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_commits.py -v -k "TestPathToSlug or TestGenerateCommitMarkdown or TestMergeCommits"
```

- [ ] **Step 5: Write failing tests for the full CLI flow (mocked git subprocess)**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_commits.py`:

```python
from scripts.commits import (
    run_git_log,
    run_commits_command,
    get_changed_files_for_commit,
)


SAMPLE_GIT_LOG_WITH_FILES = SAMPLE_GIT_LOG  # reuse same fixture


class TestRunGitLog:
    """Test the subprocess wrapper for git log."""

    @patch("scripts.commits.subprocess.run")
    def test_calls_git_with_correct_args(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        commits = run_git_log(since="4w", path="src/api/", cwd="/fake/repo")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "git" in cmd[0]
        assert "log" in cmd
        assert '--format=%H|%an|%ae|%ad|%s' in cmd
        assert "--since=4w" in cmd
        assert "src/api/" in cmd
        assert len(commits) == 5

    @patch("scripts.commits.subprocess.run")
    def test_default_since_4w(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        run_git_log(since=None, path=None, cwd="/fake/repo")
        cmd = mock_run.call_args[0][0]
        assert "--since=4w" in cmd

    @patch("scripts.commits.subprocess.run")
    def test_handles_git_error_gracefully(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: not a git repository", returncode=128
        )
        commits = run_git_log(since="4w", path=None, cwd="/fake/repo")
        assert commits == []


class TestRunCommitsCommand:
    """Integration test for the full commits command with mocked git."""

    @patch("scripts.commits.subprocess.run")
    @patch("scripts.commits.resolve_repo_id", return_value="test--repo")
    def test_creates_output_files(self, mock_repo_id, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        # Patch get_notes_dir to use tmp_path
        commits_dir = tmp_path / "commits"
        with patch("scripts.commits.get_notes_dir", return_value=tmp_path):
            run_commits_command(
                author=None,  # all authors
                since="4w",
                path="src/",
                repo_id=None,
                cwd="/fake/repo",
                depth=2,
            )

        # Should create author directories
        assert (commits_dir / "Alice Smith").is_dir() or (commits_dir / "alice-smith").is_dir()

    @patch("scripts.commits.subprocess.run")
    @patch("scripts.commits.resolve_repo_id", return_value="test--repo")
    def test_output_file_has_valid_frontmatter(self, mock_repo_id, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        commits_dir = tmp_path / "commits"
        with patch("scripts.commits.get_notes_dir", return_value=tmp_path):
            run_commits_command(
                author="Alice Smith",
                since="4w",
                path=None,
                repo_id=None,
                cwd="/fake/repo",
                depth=2,
            )

        # Find any generated .md file
        md_files = list(commits_dir.rglob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text()
        fm = parse_frontmatter(content)
        assert fm["author"] == "Alice Smith"
        assert "## Commits" in content

    @patch("scripts.commits.subprocess.run")
    @patch("scripts.commits.resolve_repo_id", return_value="test--repo")
    def test_merge_mode_deduplicates(self, mock_repo_id, mock_run, tmp_path):
        """Running commits command twice should not duplicate entries."""
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        with patch("scripts.commits.get_notes_dir", return_value=tmp_path):
            run_commits_command(
                author="Alice Smith", since="4w", path=None,
                repo_id=None, cwd="/fake/repo", depth=2,
            )
            # Run again — should merge, not duplicate
            run_commits_command(
                author="Alice Smith", since="4w", path=None,
                repo_id=None, cwd="/fake/repo", depth=2,
            )

        md_files = list((tmp_path / "commits").rglob("*.md"))
        for md_file in md_files:
            content = md_file.read_text()
            # Count occurrences of Alice's first commit hash (short)
            count = content.count("`abc1234a`")
            assert count <= 1, f"Duplicate hash found in {md_file}"
```

Run tests (expect failure):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_commits.py -v -k "TestRunGitLog or TestRunCommitsCommand"
```

- [ ] **Step 6: Implement git subprocess wrapper and CLI handler**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/commits.py`:

```python
# ---------------------------------------------------------------------------
# Git subprocess wrapper
# ---------------------------------------------------------------------------

def run_git_log(
    since: Optional[str] = None,
    path: Optional[str] = None,
    cwd: Optional[str] = None,
) -> list[Commit]:
    """Run git log and return parsed commits.

    Args:
        since: Git --since value (default '4w').
        path: Optional path filter for git log.
        cwd: Working directory for git command.

    Returns:
        List of Commit objects (empty on error).
    """
    since = since or "4w"
    cmd = [
        "git", "log",
        "--format=%H|%an|%ae|%ad|%s",
        f"--since={since}",
    ]
    if path:
        cmd.append("--")
        cmd.append(path)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        if result.returncode != 0:
            return []
        return parse_git_log_output(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_changed_files_for_commit(commit_hash: str, cwd: Optional[str] = None) -> list[str]:
    """Get list of files changed in a commit."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _author_to_dirname(author: str) -> str:
    """Convert author name to a safe directory name."""
    return re.sub(r"[^\w\s-]", "", author).strip().replace(" ", "-").lower()


# ---------------------------------------------------------------------------
# Lazy imports for repo_id (avoids circular imports at module level)
# ---------------------------------------------------------------------------

def resolve_repo_id() -> str:
    from scripts.repo_id import resolve_repo_id as _resolve
    return _resolve()


def get_notes_dir(repo_id: str) -> Path:
    from scripts.repo_id import get_notes_dir as _get
    return _get(repo_id)


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def run_commits_command(
    author: Optional[str] = None,
    since: Optional[str] = None,
    path: Optional[str] = None,
    repo_id: Optional[str] = None,
    cwd: Optional[str] = None,
    depth: int = 2,
) -> None:
    """Main entry point for the 'commits' CLI command.

    Fetches git log, groups by author and path prefix, writes markdown files.
    Supports merge mode: if output file exists, deduplicates commits.
    """
    rid = repo_id or resolve_repo_id()
    notes_base = get_notes_dir(rid)
    commits_dir = notes_base / "commits"
    commits_dir.mkdir(parents=True, exist_ok=True)

    # Fetch commits
    all_commits = run_git_log(since=since, path=path, cwd=cwd)
    if not all_commits:
        print("No commits found.")
        return

    # Group by author
    by_author = group_commits_by_author(all_commits)

    # Filter to specific author if requested
    if author:
        if author in by_author:
            by_author = {author: by_author[author]}
        else:
            # Try case-insensitive match
            matched = {k: v for k, v in by_author.items() if k.lower() == author.lower()}
            if matched:
                by_author = matched
            else:
                print(f"No commits found for author: {author}")
                return

    # Compute date range
    since_val = since or "4w"
    today = datetime.now().strftime("%Y-%m-%d")
    # Approximate start date from --since
    date_range = f"last {since_val} to {today}"
    if all_commits:
        dates = [c.date for c in all_commits]
        first_short = _format_date_short(dates[-1])
        last_short = _format_date_short(dates[0])
        date_range = f"{first_short} to {last_short}"

    # For each author, group their commits by path prefix and write files
    for auth_name, auth_commits in by_author.items():
        auth_dir = commits_dir / _author_to_dirname(auth_name)
        auth_dir.mkdir(parents=True, exist_ok=True)

        # If we have a specific path filter, use it as the slug directly
        if path:
            slug = path_to_slug(path)
            _write_commit_file(
                auth_dir, slug, auth_name, auth_commits[0].email,
                path, auth_commits, date_range,
            )
        else:
            # Group by path prefix (we use "root" for all since we don't have per-commit files here)
            slug = "all"
            _write_commit_file(
                auth_dir, slug, auth_name, auth_commits[0].email,
                ".", auth_commits, date_range,
            )

    print(f"Generated commit notes for {len(by_author)} author(s) in {commits_dir}")


def _write_commit_file(
    auth_dir: Path,
    slug: str,
    author: str,
    email: str,
    path_filter: str,
    commits: list[Commit],
    date_range: str,
) -> None:
    """Write or merge a commit markdown file."""
    out_file = auth_dir / f"{slug}.md"

    if out_file.exists():
        existing_md = out_file.read_text(encoding="utf-8")
        merged = merge_commits_into_existing(existing_md, commits, date_range)
        out_file.write_text(merged, encoding="utf-8")
    else:
        md = generate_commit_markdown(
            author=author,
            email=email,
            path_filter=path_filter,
            commits=commits,
            date_range=date_range,
        )
        out_file.write_text(md, encoding="utf-8")
```

Run all tests (expect pass):

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_commits.py -v
```

- [ ] **Step 7: Register `commits` command in `__main__.py`**

Add the commits subcommand to `/Users/karthik/Documents/work/codebase-notes/scripts/__main__.py` (in the argparse setup section):

```python
    # In the subparsers section, add:
    commits_parser = subparsers.add_parser("commits", help="Generate commit history notes")
    commits_parser.add_argument("--author", default=None, help="Filter by author name")
    commits_parser.add_argument("--since", default=None, help="Git --since value (default: 4w)")
    commits_parser.add_argument("--path", default=None, help="Path filter for git log")
    commits_parser.add_argument("--repo-id", default=None, help="Override repo ID")
    commits_parser.add_argument("--depth", type=int, default=2, help="Path prefix grouping depth")
```

And in the dispatch section:

```python
    elif args.command == "commits":
        from scripts.commits import run_commits_command
        run_commits_command(
            author=args.author,
            since=args.since,
            path=args.path,
            repo_id=args.repo_id,
            depth=args.depth,
        )
```

- [ ] **Step 8: Run full test suite for both modules and commit**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_render.py ../tests/test_commits.py -v
```

Commit message: `feat: add commits.py — git log extraction, author/path grouping, and markdown generation with merge mode`

---

---

## Task 8: cron.py + Tests

### Files

| File | Purpose |
|------|---------|
| `/Users/karthik/Documents/work/codebase-notes/scripts/cron.py` | Cron install/uninstall, auto-update orchestration, lock file management |
| `/Users/karthik/Documents/work/codebase-notes/tests/test_cron.py` | Tests for all cron.py functionality |

### Prerequisites

- Task 1 (project structure, `__main__.py`, `__init__.py`, `pyproject.toml`) must be complete
- Task 2 (`repo_id.py`) must be complete
- Task 4 (`staleness.py`) must be complete — `auto-update` calls staleness checks

### IMPORTANT: Function Naming Convention

This module must expose `run_cron(args)` and `run_auto_update(args)` as entry points (matching `__main__.py` dispatch). When importing from `staleness.py`, use the actual exported functions: `check_all_notes`, `check_all_repos`, and `parse_frontmatter` — NOT `check_staleness_for_repo` or `get_valid_clone_path` (these don't exist). For clone path validation, either make `_find_valid_clone` public by renaming to `find_valid_clone`, or implement the logic directly in cron.py.

### Implementation Steps

- [ ] **Step 1: Write failing tests for lock file acquire/release**

Create `/Users/karthik/Documents/work/codebase-notes/tests/test_cron.py`:

```python
"""Tests for cron.py — lock file management, plist generation, auto-update orchestration."""

import os
import signal
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# We'll import from scripts.cron once implemented
# For now these tests define the expected interface


class TestLockFile:
    """Test lock file acquire/release and stale lock detection."""

    def test_acquire_lock_creates_file(self, tmp_path):
        """Acquiring a lock should create .cron.lock with current PID."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        assert acquire_lock(lock_path) is True
        assert lock_path.exists()
        assert lock_path.read_text().strip() == str(os.getpid())
        release_lock(lock_path)

    def test_acquire_lock_fails_if_process_alive(self, tmp_path):
        """Should fail to acquire if lock exists and owning process is alive."""
        from scripts.cron import acquire_lock

        lock_path = tmp_path / ".cron.lock"
        # Write our own PID — we are alive
        lock_path.write_text(str(os.getpid()))

        assert acquire_lock(lock_path) is False

    def test_acquire_lock_removes_stale_lock(self, tmp_path):
        """Should remove lock and acquire if owning process is dead."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        # Write a PID that almost certainly doesn't exist
        lock_path.write_text("9999999")

        # Mock os.kill to raise OSError (process not found)
        with patch("os.kill", side_effect=OSError("No such process")):
            assert acquire_lock(lock_path) is True
            assert lock_path.read_text().strip() == str(os.getpid())

        release_lock(lock_path)

    def test_release_lock_removes_file(self, tmp_path):
        """Releasing the lock should delete the lock file."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        acquire_lock(lock_path)
        assert lock_path.exists()
        release_lock(lock_path)
        assert not lock_path.exists()

    def test_release_lock_noop_if_missing(self, tmp_path):
        """Releasing a non-existent lock should not error."""
        from scripts.cron import release_lock

        lock_path = tmp_path / ".cron.lock"
        release_lock(lock_path)  # Should not raise

    def test_acquire_lock_replaces_lock_with_non_numeric_content(self, tmp_path):
        """If lock file has garbage content, treat as stale and acquire."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        lock_path.write_text("not-a-pid\n")

        assert acquire_lock(lock_path) is True
        release_lock(lock_path)
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestLockFile -v
```

- [ ] **Step 2: Implement lock file management in cron.py**

Create `/Users/karthik/Documents/work/codebase-notes/scripts/cron.py`:

```python
"""Cron installation/uninstall, auto-update orchestration, and lock file management.

Provides:
- acquire_lock / release_lock for .cron.lock PID-based locking
- install/uninstall launchd plist (macOS) or crontab (Linux)
- auto_update: staleness check -> spawn claude for stale notes
- auto_update_all_repos: iterate all repos
"""

import datetime
import os
import platform
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO_NOTES_BASE = Path.home() / ".claude" / "repo_notes"
LOCK_FILE = REPO_NOTES_BASE / ".cron.lock"
LOG_FILE = REPO_NOTES_BASE / "cron.log"
SCRIPTS_DIR = Path.home() / ".claude" / "skills" / "codebase-notes" / "scripts"
SKILL_MD = Path.home() / ".claude" / "skills" / "codebase-notes" / "SKILL.md"
PLIST_LABEL = "com.codebase-notes.auto-update"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

MAX_REPOS_PER_RUN = 5
PER_REPO_TIMEOUT = 600  # 10 minutes


def acquire_lock(lock_path: Path = LOCK_FILE) -> bool:
    """Acquire a PID-based lock file.

    Returns True if lock acquired, False if another live process holds it.
    Removes stale locks (dead processes or non-numeric content).
    """
    if lock_path.exists():
        try:
            pid_str = lock_path.read_text().strip()
            pid = int(pid_str)
        except (ValueError, OSError):
            # Garbage content — treat as stale
            lock_path.unlink(missing_ok=True)
        else:
            # Check if process is alive
            try:
                os.kill(pid, 0)  # Signal 0 = check existence
                return False  # Process is alive, cannot acquire
            except OSError:
                # Process is dead — stale lock
                lock_path.unlink(missing_ok=True)

    # Write our PID
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))
    return True


def release_lock(lock_path: Path = LOCK_FILE) -> None:
    """Release the lock file by removing it."""
    lock_path.unlink(missing_ok=True)


def log_message(message: str, log_path: Path = LOG_FILE) -> None:
    """Append a timestamped message to the cron log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
```

Run the lock file tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestLockFile -v
```

- [ ] **Step 3: Write failing tests for launchd plist generation**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_cron.py`:

```python
class TestPlistGeneration:
    """Test launchd plist XML generation for macOS."""

    def test_generate_plist_default_interval(self):
        """Plist should default to 6h (21600s) interval."""
        from scripts.cron import generate_plist_content

        content = generate_plist_content(interval_hours=6)
        assert "com.codebase-notes.auto-update" in content
        assert "<integer>21600</integer>" in content

    def test_generate_plist_custom_interval(self):
        """Plist should accept custom interval in hours."""
        from scripts.cron import generate_plist_content

        content = generate_plist_content(interval_hours=12)
        assert "<integer>43200</integer>" in content

    def test_generate_plist_contains_correct_command(self):
        """Plist should run: cd scripts dir && uv run python -m scripts auto-update --all-repos."""
        from scripts.cron import generate_plist_content, SCRIPTS_DIR

        content = generate_plist_content(interval_hours=6)
        assert "uv" in content
        assert "auto-update" in content
        assert "--all-repos" in content
        assert str(SCRIPTS_DIR) in content

    def test_generate_plist_has_log_paths(self):
        """Plist should set stdout/stderr log paths."""
        from scripts.cron import generate_plist_content, LOG_FILE

        content = generate_plist_content(interval_hours=6)
        assert str(LOG_FILE) in content or "cron.log" in content

    def test_generate_plist_is_valid_xml(self):
        """Plist content should be parseable XML."""
        import xml.etree.ElementTree as ET
        from scripts.cron import generate_plist_content

        content = generate_plist_content(interval_hours=6)
        # Should not raise
        ET.fromstring(content)

    def test_install_cron_creates_plist_file(self, tmp_path):
        """install_cron should write the plist file to the given path."""
        from scripts.cron import install_cron

        plist_path = tmp_path / "com.codebase-notes.auto-update.plist"
        with patch("scripts.cron.PLIST_PATH", plist_path), \
             patch("subprocess.run") as mock_run, \
             patch("platform.system", return_value="Darwin"):
            install_cron(interval_hours=6)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "com.codebase-notes.auto-update" in content

    def test_uninstall_cron_removes_plist(self, tmp_path):
        """uninstall_cron should unload and delete the plist file."""
        from scripts.cron import uninstall_cron

        plist_path = tmp_path / "com.codebase-notes.auto-update.plist"
        plist_path.write_text("<plist></plist>")

        with patch("scripts.cron.PLIST_PATH", plist_path), \
             patch("subprocess.run") as mock_run, \
             patch("platform.system", return_value="Darwin"):
            uninstall_cron()

        assert not plist_path.exists()
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestPlistGeneration -v
```

- [ ] **Step 4: Implement plist generation and cron install/uninstall**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/cron.py`:

```python
def generate_plist_content(interval_hours: int = 6) -> str:
    """Generate launchd plist XML content for auto-update scheduling.

    Args:
        interval_hours: How often to run, in hours. Converted to seconds for launchd.

    Returns:
        Complete plist XML string.
    """
    interval_seconds = interval_hours * 3600
    # Use /bin/bash -c so we can cd first
    command = f"cd {SCRIPTS_DIR} && uv run python -m scripts auto-update --all-repos"

    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{PLIST_LABEL}</string>
            <key>ProgramArguments</key>
            <array>
                <string>/bin/bash</string>
                <string>-c</string>
                <string>{command}</string>
            </array>
            <key>WorkingDirectory</key>
            <string>{SCRIPTS_DIR}</string>
            <key>StartInterval</key>
            <integer>{interval_seconds}</integer>
            <key>StandardOutPath</key>
            <string>{LOG_FILE}</string>
            <key>StandardErrorPath</key>
            <string>{LOG_FILE}</string>
            <key>RunAtLoad</key>
            <false/>
        </dict>
        </plist>
    """)


def generate_crontab_entry(interval_hours: int = 6) -> str:
    """Generate a crontab line for Linux fallback.

    Args:
        interval_hours: How often to run, in hours.

    Returns:
        Single crontab line string.
    """
    # e.g., for 6h: "0 */6 * * *"
    return f"0 */{interval_hours} * * * cd {SCRIPTS_DIR} && uv run python -m scripts auto-update --all-repos >> {LOG_FILE} 2>&1"


CRONTAB_MARKER = "# codebase-notes-auto-update"


def install_cron(interval_hours: int = 6) -> str:
    """Install cron schedule. Uses launchd on macOS, crontab on Linux.

    Returns:
        Human-readable message about what was installed.
    """
    system = platform.system()

    if system == "Darwin":
        # macOS: write plist and load it
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        content = generate_plist_content(interval_hours)
        PLIST_PATH.write_text(content)
        subprocess.run(
            ["launchctl", "load", str(PLIST_PATH)],
            check=False,
            capture_output=True,
        )
        return f"Installed launchd plist at {PLIST_PATH} (every {interval_hours}h)"

    elif system == "Linux":
        # Linux: add crontab entry
        entry = generate_crontab_entry(interval_hours)
        tagged_entry = f"{entry} {CRONTAB_MARKER}"

        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True
        )
        existing = result.stdout if result.returncode == 0 else ""

        # Remove any existing codebase-notes entry
        lines = [
            line for line in existing.splitlines()
            if CRONTAB_MARKER not in line
        ]
        lines.append(tagged_entry)

        # Write new crontab
        new_crontab = "\n".join(lines) + "\n"
        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True,
        )
        return f"Installed crontab entry (every {interval_hours}h)"

    else:
        return f"Unsupported platform: {system}. Manually schedule: cd {SCRIPTS_DIR} && uv run python -m scripts auto-update --all-repos"


def uninstall_cron() -> str:
    """Remove cron schedule.

    Returns:
        Human-readable message about what was removed.
    """
    system = platform.system()

    if system == "Darwin":
        if PLIST_PATH.exists():
            subprocess.run(
                ["launchctl", "unload", str(PLIST_PATH)],
                check=False,
                capture_output=True,
            )
            PLIST_PATH.unlink()
            return f"Removed launchd plist at {PLIST_PATH}"
        return "No plist found to remove."

    elif system == "Linux":
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True
        )
        if result.returncode != 0:
            return "No crontab found."

        lines = [
            line for line in result.stdout.splitlines()
            if CRONTAB_MARKER not in line
        ]
        new_crontab = "\n".join(lines) + "\n" if lines else ""
        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True,
        )
        return "Removed crontab entry for codebase-notes."

    else:
        return f"Unsupported platform: {system}"
```

Run the plist generation tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestPlistGeneration -v
```

- [ ] **Step 5: Write failing tests for crontab fallback (Linux)**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_cron.py`:

```python
class TestCrontabFallback:
    """Test crontab generation for Linux systems."""

    def test_generate_crontab_entry_default(self):
        """Should generate valid crontab entry with 6h interval."""
        from scripts.cron import generate_crontab_entry

        entry = generate_crontab_entry(interval_hours=6)
        assert entry.startswith("0 */6 * * *")
        assert "auto-update --all-repos" in entry

    def test_generate_crontab_entry_custom(self):
        """Should handle custom interval."""
        from scripts.cron import generate_crontab_entry

        entry = generate_crontab_entry(interval_hours=2)
        assert "*/2" in entry

    def test_install_cron_linux_adds_entry(self):
        """On Linux, install_cron should add a tagged crontab entry."""
        from scripts.cron import install_cron, CRONTAB_MARKER

        with patch("platform.system", return_value="Linux"), \
             patch("subprocess.run") as mock_run:
            # First call: crontab -l returns empty
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="no crontab"),  # crontab -l
                MagicMock(returncode=0),  # crontab -
            ]
            result = install_cron(interval_hours=6)

        assert "crontab" in result.lower()
        # Verify crontab - was called with the marker
        written_input = mock_run.call_args_list[1].kwargs.get("input", "")
        assert CRONTAB_MARKER in written_input

    def test_uninstall_cron_linux_removes_entry(self):
        """On Linux, uninstall_cron should remove the tagged crontab line."""
        from scripts.cron import uninstall_cron, CRONTAB_MARKER

        existing = f"0 * * * * some-other-job\n0 */6 * * * cd /path && uv run ... {CRONTAB_MARKER}\n"

        with patch("platform.system", return_value="Linux"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=existing),  # crontab -l
                MagicMock(returncode=0),  # crontab -
            ]
            uninstall_cron()

        written_input = mock_run.call_args_list[1].kwargs.get("input", "")
        assert CRONTAB_MARKER not in written_input
        assert "some-other-job" in written_input
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestCrontabFallback -v
```

- [ ] **Step 6: Run crontab tests (should pass with existing implementation)**

The crontab functions were already implemented in Step 4. Run:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestCrontabFallback -v
```

- [ ] **Step 7: Write failing tests for auto-update orchestration**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_cron.py`:

```python
class TestAutoUpdate:
    """Test auto-update orchestration: staleness check, claude spawning, timeouts."""

    def test_build_update_prompt_includes_stale_notes(self):
        """The prompt sent to claude should list stale notes and changed files."""
        from scripts.cron import build_update_prompt

        stale_entries = [
            {
                "note": "02-models/index.md",
                "changed_files": ["src/models/user.py", "src/models/auth.py"],
                "files_changed": 2,
            }
        ]
        prompt = build_update_prompt(stale_entries, "my-org--my-repo")
        assert "02-models/index.md" in prompt
        assert "src/models/user.py" in prompt
        assert "src/models/auth.py" in prompt

    def test_build_update_prompt_limits_to_max_repos(self):
        """Prompt builder should respect the list it's given (caller limits)."""
        from scripts.cron import build_update_prompt

        stale_entries = [
            {"note": f"note-{i}/index.md", "changed_files": [f"file{i}.py"], "files_changed": i + 1}
            for i in range(3)
        ]
        prompt = build_update_prompt(stale_entries, "org--repo")
        for entry in stale_entries:
            assert entry["note"] in prompt

    def test_spawn_claude_for_repo_calls_subprocess(self, tmp_path):
        """Should invoke claude CLI with correct flags and working directory."""
        from scripts.cron import spawn_claude_for_repo

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
            result = spawn_claude_for_repo(
                prompt="Update the notes",
                working_dir=tmp_path,
                timeout=60,
            )

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "claude" in cmd[0]
        assert "-p" in cmd
        assert "--allowedTools" in cmd
        assert str(tmp_path) == call_args[1].get("cwd") or call_args.kwargs.get("cwd") == str(tmp_path)

    def test_spawn_claude_for_repo_handles_timeout(self, tmp_path):
        """Should return timeout status when claude exceeds time limit."""
        from scripts.cron import spawn_claude_for_repo

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=10)):
            result = spawn_claude_for_repo(
                prompt="Update",
                working_dir=tmp_path,
                timeout=10,
            )

        assert result["status"] == "timeout"

    def test_spawn_claude_for_repo_handles_error(self, tmp_path):
        """Should return error status when claude fails."""
        from scripts.cron import spawn_claude_for_repo

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error occurred")
            result = spawn_claude_for_repo(
                prompt="Update",
                working_dir=tmp_path,
                timeout=60,
            )

        assert result["status"] == "error"

    def test_auto_update_acquires_and_releases_lock(self, tmp_path):
        """auto_update_all_repos should acquire lock at start, release at end."""
        from scripts.cron import auto_update_all_repos

        lock_path = tmp_path / ".cron.lock"
        log_path = tmp_path / "cron.log"

        with patch("scripts.cron.LOCK_FILE", lock_path), \
             patch("scripts.cron.LOG_FILE", log_path), \
             patch("scripts.cron.REPO_NOTES_BASE", tmp_path), \
             patch("scripts.cron.get_all_stale_repos", return_value=[]):
            auto_update_all_repos()

        assert not lock_path.exists()  # Lock released

    def test_auto_update_skips_if_locked(self, tmp_path):
        """auto_update_all_repos should skip if lock is held by live process."""
        from scripts.cron import auto_update_all_repos

        lock_path = tmp_path / ".cron.lock"
        lock_path.write_text(str(os.getpid()))  # Our PID — alive
        log_path = tmp_path / "cron.log"

        with patch("scripts.cron.LOCK_FILE", lock_path), \
             patch("scripts.cron.LOG_FILE", log_path), \
             patch("scripts.cron.REPO_NOTES_BASE", tmp_path), \
             patch("scripts.cron.get_all_stale_repos") as mock_stale:
            auto_update_all_repos()

        mock_stale.assert_not_called()  # Should have bailed before checking staleness

    def test_auto_update_limits_to_max_repos(self, tmp_path):
        """Should process at most MAX_REPOS_PER_RUN repos, sorted by severity."""
        from scripts.cron import select_top_stale_repos, MAX_REPOS_PER_RUN

        repos = [
            {"repo_id": f"org--repo{i}", "total_changed_files": i * 3, "stale_notes": [], "clone_path": f"/tmp/r{i}"}
            for i in range(10)
        ]
        selected = select_top_stale_repos(repos, max_repos=MAX_REPOS_PER_RUN)
        assert len(selected) == MAX_REPOS_PER_RUN
        # Should be sorted by severity descending
        for j in range(len(selected) - 1):
            assert selected[j]["total_changed_files"] >= selected[j + 1]["total_changed_files"]

    def test_auto_update_logs_outcomes(self, tmp_path):
        """Each repo update outcome should be logged."""
        from scripts.cron import log_message

        log_path = tmp_path / "cron.log"
        log_message("org--repo1: success", log_path)
        log_message("org--repo2: timeout", log_path)

        content = log_path.read_text()
        assert "org--repo1: success" in content
        assert "org--repo2: timeout" in content
        # Each line should have a timestamp
        lines = content.strip().split("\n")
        for line in lines:
            assert line.startswith("[")
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestAutoUpdate -v
```

- [ ] **Step 8: Implement auto-update orchestration**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/cron.py`:

```python
def build_update_prompt(stale_entries: list[dict], repo_id: str) -> str:
    """Build the prompt string sent to claude for updating stale notes.

    Args:
        stale_entries: List of dicts with keys: note, changed_files, files_changed
        repo_id: The repo identifier

    Returns:
        Prompt string for claude -p
    """
    notes_dir = REPO_NOTES_BASE / repo_id / "notes"
    lines = [
        f"You are updating codebase notes for repo '{repo_id}'.",
        f"Notes are at: {notes_dir}",
        "",
        "The following notes are STALE and need updating:",
        "",
    ]

    for entry in stale_entries:
        lines.append(f"### {entry['note']} ({entry['files_changed']} files changed)")
        lines.append("Changed files:")
        for f in entry["changed_files"]:
            lines.append(f"  - {f}")
        lines.append("")

    lines.extend([
        "For each stale note:",
        "1. Read the current note",
        "2. Check the changed files listed above to understand what changed",
        "3. Update the note content to reflect the current state of the code",
        "4. Update the git_tracked_paths commit hashes in frontmatter",
        "5. Update last_updated date",
        "",
        "Do NOT create new notes. Only update the listed stale notes.",
    ])

    return "\n".join(lines)


def spawn_claude_for_repo(
    prompt: str,
    working_dir: Path,
    timeout: int = PER_REPO_TIMEOUT,
) -> dict:
    """Spawn a non-interactive claude session to update notes.

    Args:
        prompt: The update prompt
        working_dir: Directory to run claude from (a valid git clone)
        timeout: Max seconds to wait

    Returns:
        Dict with keys: status ("success", "timeout", "error"), message
    """
    cmd = [
        "claude",
        "-p", prompt,
        "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
        "-C", str(SKILL_MD),
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(working_dir),
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {"status": "success", "message": result.stdout[:500]}
        else:
            return {"status": "error", "message": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": f"Killed after {timeout}s"}
    except FileNotFoundError:
        return {"status": "error", "message": "claude CLI not found"}


def select_top_stale_repos(
    repos: list[dict],
    max_repos: int = MAX_REPOS_PER_RUN,
) -> list[dict]:
    """Select the top N stale repos sorted by severity (most changed files first).

    Args:
        repos: List of dicts with repo_id, total_changed_files, stale_notes, clone_path
        max_repos: Maximum number of repos to return

    Returns:
        Top repos sorted by total_changed_files descending.
    """
    sorted_repos = sorted(repos, key=lambda r: r["total_changed_files"], reverse=True)
    return sorted_repos[:max_repos]


def get_all_stale_repos() -> list[dict]:
    """Scan all repos in REPO_NOTES_BASE and return staleness info.

    Delegates to staleness.py for actual checking. Returns a list of dicts
    for repos that have at least one stale note, including a valid clone_path.
    """
    from scripts.staleness import check_staleness_for_repo, get_valid_clone_path

    stale_repos = []
    if not REPO_NOTES_BASE.exists():
        return stale_repos

    for repo_dir in REPO_NOTES_BASE.iterdir():
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue

        repo_id = repo_dir.name
        clone_path = get_valid_clone_path(repo_id)
        if clone_path is None:
            log_message(f"{repo_id}: skipped — no valid clone path")
            continue

        stale_notes = check_staleness_for_repo(repo_id, clone_path, use_cache=False)
        stale_entries = [n for n in stale_notes if n.get("status") == "STALE"]

        if stale_entries:
            total_changed = sum(n.get("files_changed", 0) for n in stale_entries)
            stale_repos.append({
                "repo_id": repo_id,
                "total_changed_files": total_changed,
                "stale_notes": stale_entries,
                "clone_path": str(clone_path),
            })

    return stale_repos


def auto_update_all_repos() -> None:
    """Main entry point for cron-triggered auto-update of all repos.

    Acquires lock, checks staleness, spawns claude for top stale repos,
    logs outcomes, releases lock.
    """
    if not acquire_lock():
        log_message("Skipped: previous run still active (lock held)")
        return

    try:
        log_message("Auto-update started")
        stale_repos = get_all_stale_repos()

        if not stale_repos:
            log_message("No stale repos found")
            return

        selected = select_top_stale_repos(stale_repos)
        log_message(f"Processing {len(selected)} of {len(stale_repos)} stale repos")

        for repo in selected:
            repo_id = repo["repo_id"]
            clone_path = Path(repo["clone_path"])
            prompt = build_update_prompt(repo["stale_notes"], repo_id)

            log_message(f"{repo_id}: starting update ({repo['total_changed_files']} files changed)")
            result = spawn_claude_for_repo(prompt, clone_path)
            log_message(f"{repo_id}: {result['status']} — {result['message'][:200]}")

    except Exception as e:
        log_message(f"Auto-update error: {e}")
    finally:
        release_lock()
        log_message("Auto-update finished")


def auto_update_single_repo(repo_id: str) -> None:
    """Run auto-update for a single repo.

    Args:
        repo_id: The repo identifier. If None, resolved from current git repo.
    """
    from scripts.staleness import check_staleness_for_repo, get_valid_clone_path

    clone_path = get_valid_clone_path(repo_id)
    if clone_path is None:
        print(f"Error: no valid clone path for {repo_id}", file=sys.stderr)
        sys.exit(1)

    stale_notes = check_staleness_for_repo(repo_id, clone_path, use_cache=False)
    stale_entries = [n for n in stale_notes if n.get("status") == "STALE"]

    if not stale_entries:
        print(f"No stale notes for {repo_id}")
        return

    prompt = build_update_prompt(stale_entries, repo_id)
    print(f"Updating {len(stale_entries)} stale notes for {repo_id}...")
    result = spawn_claude_for_repo(prompt, clone_path)
    print(f"Result: {result['status']} — {result['message'][:200]}")
```

Run the auto-update tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestAutoUpdate -v
```

- [ ] **Step 9: Write failing tests for CLI integration**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_cron.py`:

```python
class TestCronCLI:
    """Test the CLI entry points for cron and auto-update commands."""

    def test_parse_interval_default(self):
        """Default interval should be 6 hours."""
        from scripts.cron import parse_interval

        assert parse_interval("6h") == 6
        assert parse_interval(None) == 6

    def test_parse_interval_custom(self):
        """Should parse Nh format."""
        from scripts.cron import parse_interval

        assert parse_interval("12h") == 12
        assert parse_interval("1h") == 1
        assert parse_interval("24h") == 24

    def test_parse_interval_invalid(self):
        """Should raise ValueError for bad format."""
        from scripts.cron import parse_interval

        with pytest.raises(ValueError):
            parse_interval("abc")
        with pytest.raises(ValueError):
            parse_interval("6m")  # Only hours supported

    def test_handle_cron_install(self, tmp_path):
        """handle_cron with --install should call install_cron."""
        from scripts.cron import handle_cron

        plist_path = tmp_path / "test.plist"
        with patch("scripts.cron.install_cron", return_value="Installed") as mock_install:
            handle_cron(install=True, uninstall=False, interval="6h")

        mock_install.assert_called_once_with(interval_hours=6)

    def test_handle_cron_uninstall(self):
        """handle_cron with --uninstall should call uninstall_cron."""
        from scripts.cron import handle_cron

        with patch("scripts.cron.uninstall_cron", return_value="Removed") as mock_uninstall:
            handle_cron(install=False, uninstall=True, interval=None)

        mock_uninstall.assert_called_once()
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestCronCLI -v
```

- [ ] **Step 10: Implement CLI entry points and parse_interval**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/cron.py`:

```python
def parse_interval(interval: str | None) -> int:
    """Parse interval string like '6h' into integer hours.

    Args:
        interval: String like '6h', '12h'. None defaults to 6.

    Returns:
        Integer hours.

    Raises:
        ValueError: If format is not Nh.
    """
    if interval is None:
        return 6

    import re
    match = re.fullmatch(r"(\d+)h", interval)
    if not match:
        raise ValueError(f"Invalid interval format '{interval}'. Expected format: Nh (e.g., 6h, 12h)")
    return int(match.group(1))


def handle_cron(install: bool, uninstall: bool, interval: str | None) -> None:
    """Handle the 'cron' CLI command.

    Args:
        install: Whether --install was passed.
        uninstall: Whether --uninstall was passed.
        interval: Interval string like '6h', or None for default.
    """
    if install:
        hours = parse_interval(interval)
        result = install_cron(interval_hours=hours)
        print(result)
    elif uninstall:
        result = uninstall_cron()
        print(result)
    else:
        print("Usage: cron --install [--interval=6h] | cron --uninstall", file=sys.stderr)
        sys.exit(1)


def handle_auto_update(repo_id: str | None, all_repos: bool) -> None:
    """Handle the 'auto-update' CLI command.

    Args:
        repo_id: Specific repo ID, or None to resolve from cwd.
        all_repos: Whether --all-repos was passed.
    """
    if all_repos:
        auto_update_all_repos()
    elif repo_id:
        auto_update_single_repo(repo_id)
    else:
        # Resolve from current directory
        from scripts.repo_id import get_repo_id
        resolved_id = get_repo_id()
        auto_update_single_repo(resolved_id)
```

Run all CLI tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py::TestCronCLI -v
```

- [ ] **Step 11: Register cron and auto-update commands in `__main__.py`**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/__main__.py` inside the argument parser setup:

```python
    # cron subcommand
    cron_parser = subparsers.add_parser("cron", help="Install/uninstall cron schedule")
    cron_parser.add_argument("--install", action="store_true", help="Install launchd/crontab entry")
    cron_parser.add_argument("--uninstall", action="store_true", help="Remove cron entry")
    cron_parser.add_argument("--interval", default=None, help="Run interval (e.g., 6h, 12h). Default: 6h")

    # auto-update subcommand
    auto_parser = subparsers.add_parser("auto-update", help="Run auto-update for stale notes")
    auto_parser.add_argument("--repo-id", default=None, help="Specific repo ID")
    auto_parser.add_argument("--all-repos", action="store_true", help="Update all repos")
```

And in the command dispatch section:

```python
    elif args.command == "cron":
        from scripts.cron import handle_cron
        handle_cron(install=args.install, uninstall=args.uninstall, interval=args.interval)

    elif args.command == "auto-update":
        from scripts.cron import handle_auto_update
        handle_auto_update(repo_id=args.repo_id, all_repos=args.all_repos)
```

- [ ] **Step 12: Run full test suite and commit**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_cron.py -v
```

Commit message: `feat: add cron.py with launchd/crontab install, lock file management, and auto-update orchestration`

---

## Task 9: migrate.py + Tests

### Files

| File | Purpose |
|------|---------|
| `/Users/karthik/Documents/work/codebase-notes/scripts/migrate.py` | v1 to v2 notes migration logic |
| `/Users/karthik/Documents/work/codebase-notes/tests/test_migrate.py` | Tests for all migration functionality |

### Prerequisites

- Task 1 (project structure, `__main__.py`) must be complete
- Task 2 (`repo_id.py`) must be complete — migration needs repo ID resolution

### Implementation Steps

- [ ] **Step 1: Write failing tests for v1 notes detection**

Create `/Users/karthik/Documents/work/codebase-notes/tests/test_migrate.py`:

```python
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
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestDetectV1Notes -v
```

- [ ] **Step 2: Implement v1 notes detection**

Create `/Users/karthik/Documents/work/codebase-notes/scripts/migrate.py`:

```python
"""Migrate v1 notes (repo-local) to v2 centralized location.

v1 notes lived at:
  - docs/notes/
  - notes/
  - docs/knowledge/

v2 notes live at:
  - ~/.claude/repo_notes/<repo_id>/notes/
"""

import os
import re
import shutil
from pathlib import Path

REPO_NOTES_BASE = Path.home() / ".claude" / "repo_notes"

# Candidate v1 note directories, checked in order
V1_CANDIDATE_DIRS = [
    "docs/notes",
    "notes",
    "docs/knowledge",
]

# File extensions to copy
COPYABLE_EXTENSIONS = {".md", ".excalidraw", ".png"}


def detect_v1_notes(repo_root: Path) -> Path | None:
    """Detect v1 notes at known locations within a repo.

    Checks candidate directories in priority order. A directory is considered
    to contain v1 notes if it has a 00-overview.md file.

    Args:
        repo_root: Root path of the git repository.

    Returns:
        Path to the v1 notes directory, or None if not found.
    """
    for candidate in V1_CANDIDATE_DIRS:
        notes_dir = repo_root / candidate
        if (notes_dir / "00-overview.md").is_file():
            return notes_dir
    return None
```

Run the detection tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestDetectV1Notes -v
```

- [ ] **Step 3: Write failing tests for file copying**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_migrate.py`:

```python
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
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestCopyFiles -v
```

- [ ] **Step 4: Implement file copying**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/migrate.py`:

```python
def copy_v1_notes(source: Path, dest: Path) -> list[Path]:
    """Copy v1 notes to centralized v2 location, preserving directory structure.

    Only copies files with extensions in COPYABLE_EXTENSIONS (.md, .excalidraw, .png).
    Does NOT delete the source directory.

    Args:
        source: Path to v1 notes directory.
        dest: Path to v2 notes directory (will be created if needed).

    Returns:
        List of destination Paths for all files that were copied.
    """
    copied_files = []

    for root, dirs, files in os.walk(source):
        rel_root = Path(root).relative_to(source)
        dest_dir = dest / rel_root
        dest_dir.mkdir(parents=True, exist_ok=True)

        for filename in files:
            src_file = Path(root) / filename
            if src_file.suffix in COPYABLE_EXTENSIONS:
                dest_file = dest_dir / filename
                shutil.copy2(src_file, dest_file)
                copied_files.append(dest_file)

    return copied_files
```

Run the copy tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestCopyFiles -v
```

- [ ] **Step 5: Write failing tests for link updating**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_migrate.py`:

```python
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
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestUpdateLinks -v
```

- [ ] **Step 6: Implement link updating**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/migrate.py`:

```python
# Regex to find markdown links: [text](url)
LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')


def _is_external_url(url: str) -> bool:
    """Check if a URL is an external HTTP(S) link."""
    return url.startswith(("http://", "https://", "mailto:"))


def _is_anchor_link(url: str) -> bool:
    """Check if a link is a same-page anchor."""
    return url.startswith("#")


def _link_escapes_notes_dir(url: str) -> bool:
    """Check if a relative link navigates outside the notes directory tree.

    Heuristic: count how many ../ segments there are. Links within notes
    use ../ to navigate between sibling folders, but links that escape
    the notes dir will have more ../ segments than their depth allows.
    We conservatively flag links containing paths that look like source
    code paths (not ending in .md, .png, .excalidraw).
    """
    if _is_external_url(url) or _is_anchor_link(url):
        return False

    # Normalize and resolve to check if it goes to a non-note file
    # Links to .md, .png, .excalidraw within ./ or ../ are fine
    # Links to source files (e.g., ../../src/foo.py) are problematic
    parts = url.split("/")
    up_count = sum(1 for p in parts if p == "..")

    # If the link target has a notes-like extension, keep it
    target_ext = Path(url).suffix
    if target_ext in COPYABLE_EXTENSIONS:
        return False

    # If it starts with ./ or just a filename, it's within notes
    if not url.startswith(".."):
        return False

    # Links with 3+ levels of ../ from any note likely escape notes dir
    # But really, any ../ link to a non-notes file type is suspect
    if target_ext and target_ext not in COPYABLE_EXTENSIONS:
        return True

    # Absolute-looking paths
    if url.startswith("/"):
        return True

    return False


def update_links_in_content(
    content: str,
    repo_root: Path,
    old_notes_rel: str,
) -> tuple[str, list[str]]:
    """Update links in a markdown file's content after migration.

    Links within the notes tree (to .md, .png, .excalidraw) are preserved as-is
    since the directory structure is maintained. Links that escape the notes
    directory (pointing to repo source files) are flagged as broken since
    the relative path relationship changes.

    Args:
        content: The full file content (including frontmatter).
        repo_root: Original repo root path.
        old_notes_rel: Relative path from repo root to old notes dir (e.g., "docs/notes").

    Returns:
        Tuple of (updated_content, list_of_broken_link_urls).
    """
    broken_links = []

    def check_link(match: re.Match) -> str:
        text = match.group(1)
        url = match.group(2)

        # External URLs: pass through
        if _is_external_url(url) or _is_anchor_link(url):
            return match.group(0)

        # Absolute file paths: flag as broken
        if url.startswith("/"):
            broken_links.append(url)
            return match.group(0)

        # Check if link escapes notes directory
        if _link_escapes_notes_dir(url):
            broken_links.append(url)

        # Keep all links as-is in content — structure is preserved
        return match.group(0)

    updated = LINK_PATTERN.sub(check_link, content)
    return updated, broken_links
```

Run the link update tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestUpdateLinks -v
```

- [ ] **Step 7: Write failing tests for full migration flow**

Append to `/Users/karthik/Documents/work/codebase-notes/tests/test_migrate.py`:

```python
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
```

Run the failing tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestMigrateFullFlow -v
```

- [ ] **Step 8: Implement the full migrate function**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/migrate.py`:

```python
def migrate(
    from_path: Path,
    repo_id: str,
    repo_root: Path,
) -> dict:
    """Migrate v1 notes to centralized v2 location.

    Copies all .md, .excalidraw, .png files preserving directory structure.
    Updates links in .md files and reports any that couldn't be auto-fixed.
    Does NOT delete the source directory.

    Args:
        from_path: Path to the v1 notes directory.
        repo_id: The resolved repo identifier.
        repo_root: Root path of the git repository.

    Returns:
        Dict with keys: files_copied (int), broken_links (list of dicts),
        dest_path (Path).
    """
    dest_notes = REPO_NOTES_BASE / repo_id / "notes"

    # Step 1: Copy all eligible files
    copied_files = copy_v1_notes(from_path, dest_notes)

    # Step 2: Process links in all .md files
    all_broken_links = []
    old_notes_rel = str(from_path.relative_to(repo_root))

    for dest_file in copied_files:
        if dest_file.suffix != ".md":
            continue

        content = dest_file.read_text()
        updated_content, broken = update_links_in_content(content, repo_root, old_notes_rel)

        if updated_content != content:
            dest_file.write_text(updated_content)

        for url in broken:
            rel_note = str(dest_file.relative_to(dest_notes))
            all_broken_links.append({"file": rel_note, "url": url})

    return {
        "files_copied": len(copied_files),
        "broken_links": all_broken_links,
        "dest_path": dest_notes,
    }


def handle_migrate(from_path: str, repo_id: str | None = None) -> None:
    """Handle the 'migrate' CLI command.

    Args:
        from_path: Path to v1 notes directory (--from argument).
        repo_id: Optional repo ID. Resolved from cwd if not provided.
    """
    import sys

    from_path = Path(from_path).resolve()
    if not from_path.is_dir():
        print(f"Error: {from_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    if not (from_path / "00-overview.md").is_file():
        print(f"Warning: {from_path} does not contain 00-overview.md — are you sure this is a notes directory?",
              file=sys.stderr)

    # Resolve repo ID
    if repo_id is None:
        from scripts.repo_id import get_repo_id
        repo_id = get_repo_id()

    # Determine repo root (parent of from_path up to where .git is)
    repo_root = from_path
    while repo_root != repo_root.parent:
        if (repo_root / ".git").exists():
            break
        repo_root = repo_root.parent
    else:
        # Fallback: use from_path parent
        repo_root = from_path.parent

    result = migrate(from_path=from_path, repo_id=repo_id, repo_root=repo_root)

    # Print summary
    print(f"Migration complete:")
    print(f"  Files copied: {result['files_copied']}")
    print(f"  Destination:  {result['dest_path']}")

    if result["broken_links"]:
        print(f"\n  Links that could not be automatically updated ({len(result['broken_links'])}):")
        for bl in result["broken_links"]:
            print(f"    {bl['file']}: {bl['url']}")
        print("\n  These links pointed to files outside the notes directory.")
        print("  You may need to update them manually to use absolute paths or remove them.")
    else:
        print("  All links OK.")

    print(f"\n  Original directory was NOT deleted: {from_path}")
```

Run the full flow tests:

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py::TestMigrateFullFlow -v
```

- [ ] **Step 9: Register migrate command in `__main__.py`**

Add to `/Users/karthik/Documents/work/codebase-notes/scripts/__main__.py` inside the argument parser setup:

```python
    # migrate subcommand
    migrate_parser = subparsers.add_parser("migrate", help="Migrate v1 notes to centralized location")
    migrate_parser.add_argument("--from", dest="from_path", required=True, help="Path to v1 notes directory")
    migrate_parser.add_argument("--repo-id", default=None, help="Repo ID (auto-resolved if omitted)")
```

And in the command dispatch section:

```python
    elif args.command == "migrate":
        from scripts.migrate import handle_migrate
        handle_migrate(from_path=args.from_path, repo_id=args.repo_id)
```

- [ ] **Step 10: Run full test suite and commit**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/test_migrate.py -v
```

Commit message: `feat: add migrate.py for v1-to-v2 notes migration with link analysis and structure preservation`

---

---

## Task 10: RULES-template.md Overhaul

### Files
- Modify: `references/RULES-template.md` — complete rewrite

- [ ] **10.1: Write the COMPLETE new `references/RULES-template.md`**

**IMPORTANT: Write the full file content, not an outline. The executing agent must produce every line of the final file.** The subagent that planned this task generated a complete ~300-line RULES-template.md. Use the spec (Section 5) and the content guidelines below to write the full file.

The new RULES-template.md must contain these sections:

1. **Structure** — hierarchical folders, numbering, `00-overview.md` as root, centralized paths
2. **Navigation** — nav bar format, relative links, sub-topics on index.md, rebuilt via `scripts nav`
3. **Capture Matrix** — all 8 capture types with Good/Bad examples:
   - What + Why (Architecture Decisions)
   - What + How (Implementation Patterns)
   - What + Where (Data Flow)
   - What + When (Configuration)
   - What + Who (Integration Points)
   - What + What-If (Error Handling)
   - What + When (Lifecycle/Deployment) — distinct from Configuration: focuses on processes, triggers, schedules
   - What + Constraints (Schemas / Models)
4. **Applying Multiple Capture Rules in One Note** — full example note using multiple lenses
5. **Content Rules** — tables over prose, code snippets sparingly, no filler, no ASCII art
6. **Anti-Patterns** — 7 explicit anti-patterns with Bad/Fix:
   - Vague labeling without insight
   - Listing files without saying what's interesting
   - Describing config without saying when to change
   - Architecture diagrams that are just labeled boxes
   - "See code for details"
   - Prose where table would be clearer
   - Copying docstrings verbatim
7. **Diagrams (Excalidraw)** — content-type-to-diagram-style mapping (8 entries), file format, style rules, rendering via `scripts render`
8. **Git Freshness Tracking** — frontmatter format, checking via `scripts stale`, updating rules
9. **Maintenance** — update overview, parent links, prefer updates, run nav/render after changes

All script references must use: `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts <cmd>`

No references to `excalidraw-diagram` skill or `docs/notes/` default location.

- [ ] **10.2: Verify all required sections present**

```bash
grep -c "## Structure\|## Navigation\|## Capture Matrix\|## Applying Multiple\|## Content Rules\|## Anti-Patterns\|## Diagrams\|## Git Freshness\|## Maintenance" references/RULES-template.md
```
Expected: 9 matches

Verify all 8 capture types:
```bash
grep -c "### What + Why\|### What + How\|### What + Where\|### What + When\|### What + Who\|### What + What-If\|### What + Constraints" references/RULES-template.md
```
Expected: 8 matches (What + When appears twice: Configuration and Lifecycle)

Verify all anti-patterns have Bad/Fix pairs:
```bash
grep -c "\*\*Bad:\*\*\|\*\*Fix:\*\*" references/RULES-template.md
```
Expected: at least 14 (7 anti-patterns x 2)

- [ ] **10.3: Verify no forbidden references**

```bash
grep -c "excalidraw-diagram\|docs/notes/\|render_excalidraw.py" references/RULES-template.md
```
Expected: 0 matches

- [ ] **10.4: Commit**

```bash
git add references/RULES-template.md
git commit -m "Overhaul RULES-template.md with capture matrix and anti-patterns"
```

---

## Task 11: SKILL.md Complete Rewrite

### Files
- Modify: `SKILL.md` — complete rewrite

- [ ] **11.1: Write the COMPLETE new `SKILL.md`**

**IMPORTANT: Write the full file content (~500 lines), not an outline. The executing agent must produce every line of the final file.** The subagent that planned this task generated a complete SKILL.md. Use the spec (Sections 6-7) and the content guidelines below to write the full file. Read the current SKILL.md first to understand the v1 structure, then write v2 from scratch.

The new SKILL.md must contain (per spec Section 6):

**Frontmatter:**
```yaml
---
name: codebase-notes
description: Generate, explore, and maintain a hierarchical knowledge base of structured notes for any codebase. Notes are stored centrally at ~/.claude/repo_notes/<repo_id>/ and shared across all clones of the same repo. Use this skill when the user wants to understand a codebase, create documentation notes, explore a repo progressively, build a knowledge graph, or asks to "learn about this codebase", "create notes", "explore this repo", "document this project", or "help me understand this code". Also triggers for requests to update existing notes, add diagrams, dive deeper into specific areas, or when any agent needs codebase context. On activation, always run Step 0 to resolve the notes path and check for existing notes.
---
```

**Sections (in order):**

1. **Core Philosophy** — notes as primary context, knowledge graph, diagrams argue, text stands alone, capture what code can't tell you, self-contained skill
2. **Script Invocation** — table of all commands with `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts <cmd>` pattern
3. **Step 0: Auto-Setup and Notes Resolution**
   - 0.1 Bootstrap scripts (check .venv, uv sync)
   - 0.2 Resolve notes path (repo-id command)
   - 0.3 Check for existing notes (stale command or scaffold)
   - 0.4 Check for v1 notes (migration offer)
4. **Context Priming Protocol** — read notes → fall back to code → update notes
5. **Phase 1: Initialize** — explore repo, write overview, present topics
6. **Phase 2: Explore (Core Loop)** — dispatch Explore agent, write notes, update parents, present options, parallel exploration
7. **Phase 3: Update and Maintain** — staleness detection, update in-place, add detail
8. **Commit History** — generate commit notes, summarize, when to use
9. **Cron Auto-Updates** — install, what it does, uninstall, monitoring
10. **Note Structure** — directory layout, note template with frontmatter
11. **Diagrams** — creating, rendering via `scripts render`, style rules
12. **Parallelization Patterns** — multiple topics, batch diagrams, sub-topics
13. **Knowledge Map** — overview table with staleness status
14. **v1 to v2 Migration** — comparison table, migration command, manual migration
15. **Quick Reference** — user-says → action table

**Key removals from v1:**
- All inline bash snippets (staleness loops, nav link management, batch rendering)
- All `excalidraw-diagram` skill references
- `docs/notes/` default location
- `{notes_dir}` and `{repo_root}` template variables

- [ ] **11.2: Verify frontmatter is correct**

```bash
head -5 SKILL.md
```
Expected: starts with `---`, has `name: codebase-notes`, has `description:`

- [ ] **11.3: Verify no forbidden references**

```bash
grep -c "excalidraw-diagram\|docs/notes/\|{notes_dir}\|{repo_root}\|render_excalidraw.py" SKILL.md
```
Expected: 0 matches

- [ ] **11.4: Verify all script invocations use canonical pattern**

```bash
grep "uv run python -m scripts" SKILL.md | grep -v "cd ~/.claude/skills/codebase-notes/scripts &&" | grep -v "uv sync"
```
Expected: 0 matches (all invocations prefixed with cd)

- [ ] **11.5: Commit**

```bash
git add SKILL.md
git commit -m "Complete rewrite of SKILL.md for v2 centralized architecture"
```

---

## Task 12: Integration Testing + Verification

### Files
- All files from tasks 1-11

- [ ] **12.1: Run full test suite**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m pytest ../tests/ -v
```
Expected: all tests pass

- [ ] **12.2: Test CLI end-to-end — each command --help**

```bash
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts repo-id --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts scaffold --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts stale --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts nav --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts render --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts commits --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts auto-update --help
cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts cron --help
```

- [ ] **12.3: Test full workflow — repo-id → scaffold → stale → nav → render**

```bash
# Step 1: resolve repo ID
cd /Users/karthik/Documents/work/codebase-notes && cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id

# Step 2: scaffold
cd /Users/karthik/Documents/work/codebase-notes && cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts scaffold

# Step 3: verify structure created
ls -la ~/.claude/repo_notes/$(cd /Users/karthik/Documents/work/codebase-notes && cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id)/

# Step 4: staleness check
cd /Users/karthik/Documents/work/codebase-notes && cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale

# Step 5: nav rebuild
cd /Users/karthik/Documents/work/codebase-notes && cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav

# Step 6: render (should report nothing to render)
cd /Users/karthik/Documents/work/codebase-notes && cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render
```

- [ ] **12.4: Verify no forbidden references in SKILL.md and RULES-template.md**

```bash
grep -n "excalidraw-diagram\|docs/notes/\|{notes_dir}\|{repo_root}\|render_excalidraw.py" SKILL.md references/RULES-template.md
```
Expected: 0 matches

- [ ] **12.5: Final commit**

```bash
git add -A
git status
git commit -m "Integration verification complete — codebase-notes v2"
```
