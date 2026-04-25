# Obsidian Vault Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate codebase-notes plugin from flat-file `~/.claude/repo_notes/` to Obsidian vault storage at `~/vaults/<slug>/`.

**Architecture:** New `vault.py` module handles vault resolution. `scaffold.py` creates Obsidian vault structure. `migrate.py` gains a `migrate_to_vault()` function for v2→v3 conversion. `staleness.py` outputs markdown instead of JSON cache. Dropped scripts: `nav_links.py`, `render.py`, `context_index.py`. New `vault-git-sync` hook replaces `context-prime`.

**Tech Stack:** Python 3.11+, PyYAML, Pillow (retained for verify_diagrams), uv, bash hooks

**Spec:** `docs/superpowers/specs/2026-04-25-obsidian-vault-migration-design.md`

---

## Task 0: Create Feature Branch

**Files:**
- None (git only)

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feat/obsidian-vault-migration
```

- [ ] **Step 2: Commit the spec and plan documents**

```bash
git add docs/superpowers/specs/2026-04-25-obsidian-vault-migration-design.md docs/superpowers/plans/2026-04-25-obsidian-vault-migration.md
git commit -m "docs: add Obsidian vault migration spec and implementation plan"
```

---

## Task 1: Create `vault.py` — Vault Resolution Module

**Files:**
- Create: `scripts/vault.py`
- Create: `tests/test_vault.py`

This is the foundational module. Every other task depends on it.

- [ ] **Step 1: Write failing tests for slug derivation**

```python
# tests/test_vault.py
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
        # non-vault dir (no config)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_vault.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.vault'`

- [ ] **Step 3: Implement vault.py**

```python
# scripts/vault.py
"""Vault resolution and management for Obsidian-based codebase notes."""

import json
import sys
from pathlib import Path
from typing import Optional

from scripts.repo_id import resolve_repo_id

VAULTS_BASE = Path.home() / "vaults"


def repo_id_to_slug(repo_id: str) -> str:
    """Convert a repo_id to a vault directory slug.

    Replaces '--' separators with '-'.
    """
    return repo_id.replace("--", "-")


def get_vault_dir(repo_id: str) -> Path:
    """Return the vault path for a given repo_id (may not exist yet)."""
    return VAULTS_BASE / repo_id_to_slug(repo_id)


def resolve_vault(
    repo_id: str,
    vaults_base: Optional[Path] = None,
) -> Optional[Path]:
    """Find an existing vault for repo_id. Returns None if not found."""
    base = vaults_base or VAULTS_BASE
    slug = repo_id_to_slug(repo_id)
    vault_dir = base / slug
    config_file = vault_dir / ".vault-config.json"
    if config_file.is_file():
        return vault_dir
    return None


def read_vault_config(vault_dir: Path) -> Optional[dict]:
    """Read and parse .vault-config.json from a vault directory."""
    config_file = vault_dir / ".vault-config.json"
    if not config_file.is_file():
        return None
    try:
        return json.loads(config_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_vault_config(vault_dir: Path, config: dict) -> None:
    """Write .vault-config.json to a vault directory."""
    config_file = vault_dir / ".vault-config.json"
    config_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def set_active_vault(vault_path: Path) -> None:
    """Set the active vault by writing its path to ~/vaults/.active-vault."""
    active_file = VAULTS_BASE / ".active-vault"
    VAULTS_BASE.mkdir(parents=True, exist_ok=True)
    active_file.write_text(str(vault_path) + "\n")


def list_vaults(vaults_base: Optional[Path] = None) -> list[dict]:
    """List all vaults with their config metadata."""
    base = vaults_base or VAULTS_BASE
    if not base.is_dir():
        return []

    results = []
    for item in sorted(base.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        config = read_vault_config(item)
        if config is not None:
            results.append(config)
    return results


def run_resolve_vault(args) -> int:
    """CLI entry point for resolve-vault command."""
    try:
        repo_id = resolve_repo_id()
        vault_dir = resolve_vault(repo_id)
        if vault_dir is None:
            print(f"No vault found for {repo_id} (expected at {get_vault_dir(repo_id)})")
            return 1
        print(str(vault_dir))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_list_vaults(args) -> int:
    """CLI entry point for list-vaults command."""
    try:
        vaults = list_vaults()
        if not vaults:
            print("No vaults found in ~/vaults/")
            return 0
        for v in vaults:
            slug = v.get("repo_slug", "unknown")
            repo_id = v.get("repo_id", "unknown")
            print(f"  {slug}  ({repo_id})")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_vault.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/vault.py tests/test_vault.py
git commit -m "feat: add vault.py — vault resolution and management module"
```

---

## Task 2: Rewrite `scaffold.py` for Obsidian Vaults

**Files:**
- Modify: `scripts/scaffold.py`
- Modify: `tests/test_scaffold.py`

- [ ] **Step 1: Write failing tests for new vault scaffolding**

Replace the entire test file:

```python
# tests/test_scaffold.py
"""Tests for vault scaffolding."""

import json
from pathlib import Path

from scripts.scaffold import scaffold_vault, OVERVIEW_SKELETON


class TestScaffoldVault:
    def test_creates_vault_directory_structure(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        vault = tmp_path / "my-repo"
        assert (vault / "notes").is_dir()
        assert (vault / "research").is_dir()
        assert (vault / "projects").is_dir()
        assert (vault / "commits").is_dir()
        assert (vault / "code-reviews").is_dir()
        assert (vault / "meta").is_dir()
        assert (vault / "wiki").is_dir()
        assert (vault / "_templates").is_dir()
        assert (vault / ".obsidian").is_dir()
        assert (vault / ".obsidian" / "snippets").is_dir()

    def test_creates_vault_config(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        config_file = tmp_path / "my-repo" / ".vault-config.json"
        assert config_file.is_file()
        config = json.loads(config_file.read_text())
        assert config["repo_id"] == "org--my-repo"
        assert config["repo_slug"] == "org-my-repo"
        assert config["clone_paths"] == ["/tmp/my-repo"]
        assert config["version"] == 3

    def test_creates_overview_with_dataview(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        overview = tmp_path / "my-repo" / "notes" / "overview.md"
        assert overview.is_file()
        content = overview.read_text()
        assert "dataview" in content
        assert "git_tracked_paths" in content

    def test_creates_hot_md(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        hot = tmp_path / "my-repo" / "wiki" / "hot.md"
        assert hot.is_file()

    def test_creates_log_md(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        log = tmp_path / "my-repo" / "wiki" / "log.md"
        assert log.is_file()

    def test_creates_obsidian_config_files(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        obs = tmp_path / "my-repo" / ".obsidian"
        assert (obs / "app.json").is_file()
        assert (obs / "core-plugins.json").is_file()
        assert (obs / "community-plugins.json").is_file()
        assert (obs / "graph.json").is_file()

    def test_creates_dashboard_with_dataview(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        dashboard = tmp_path / "my-repo" / "meta" / "dashboard.md"
        assert dashboard.is_file()
        content = dashboard.read_text()
        assert "dataview" in content

    def test_copies_rules_md(self, tmp_path):
        refs = tmp_path / "refs"
        refs.mkdir()
        (refs / "RULES-template.md").write_text("# Rules\nTest rules content.")
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=refs,
        )
        rules = tmp_path / "my-repo" / "RULES.md"
        assert rules.is_file()
        assert "Test rules content" in rules.read_text()

    def test_idempotent_does_not_overwrite_existing(self, tmp_path):
        refs = tmp_path / "refs"
        refs.mkdir()
        (refs / "RULES-template.md").write_text("original")
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=refs,
        )
        # Modify overview
        overview = tmp_path / "my-repo" / "notes" / "overview.md"
        overview.write_text("custom content")
        # Re-scaffold
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=refs,
        )
        assert overview.read_text() == "custom content"

    def test_adds_clone_path_to_existing_config(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/clone1",
            references_dir=tmp_path / "refs",
        )
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/clone2",
            references_dir=tmp_path / "refs",
        )
        config = json.loads((tmp_path / "my-repo" / ".vault-config.json").read_text())
        assert "/tmp/clone1" in config["clone_paths"]
        assert "/tmp/clone2" in config["clone_paths"]

    def test_creates_templates(self, tmp_path):
        scaffold_vault(
            vault_dir=tmp_path / "my-repo",
            repo_id="org--my-repo",
            clone_path="/tmp/my-repo",
            references_dir=tmp_path / "refs",
        )
        templates = tmp_path / "my-repo" / "_templates"
        assert (templates / "note.md").is_file()
        assert (templates / "research-paper.md").is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_scaffold.py -v`
Expected: FAIL — `scaffold_vault` not found

- [ ] **Step 3: Rewrite scaffold.py**

```python
# scripts/scaffold.py
"""Scaffold Obsidian vault structure for a repo."""

import json
import shutil
import sys
from datetime import date
from pathlib import Path

from scripts.repo_id import resolve_repo_id
from scripts.vault import repo_id_to_slug, VAULTS_BASE, write_vault_config, read_vault_config

REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"

OVERVIEW_SKELETON = """\
---
git_tracked_paths: []
last_updated: {today}
---
# Codebase Overview

## Topics

_No topics yet. Run exploration to populate._

## Knowledge Map

```dataview
TABLE status, file.mtime as "Last Updated"
FROM "notes"
WHERE file.name != "overview"
SORT file.name ASC
```

## Key Files

| File | Purpose |
|------|---------|
| | |
"""

HOT_MD_SKELETON = """\
---
updated: {today}
---
# Session Context

_New vault. No session history yet._
"""

LOG_MD_SKELETON = """\
---
updated: {today}
---
# Operations Log

_Append new entries at the top._
"""

DASHBOARD_SKELETON = """\
---
updated: {today}
---
# Dashboard

## Notes by Staleness

```dataview
TABLE git_tracked_paths as "Tracked Paths", last_updated as "Updated"
FROM "notes"
SORT last_updated ASC
```

## Research

```dataview
TABLE relevance, source_url as "Source", date_added as "Added"
FROM "research"
SORT date_added DESC
```

## Code Reviews

```dataview
TABLE status, identifier, current_version as "Version"
FROM "code-reviews"
WHERE file.name = "review"
SORT file.mtime DESC
```
"""

NOTE_TEMPLATE = """\
---
git_tracked_paths: []
last_updated: {{date}}
tags: []
aliases: []
---
# {{title}}

## What is it?

## Architecture

## Key Files

| File | Purpose |
|------|---------|
| | |
"""

RESEARCH_TEMPLATE = """\
---
type: research-paper
source_url:
relevance:
date_added: {{date}}
tags: []
---
# {{title}}

## Core Contribution

## Technical Approach

## Key Results

## Project Context
"""

OBSIDIAN_APP_JSON = json.dumps({
    "strictLineBreaks": True,
    "showFrontmatter": True,
    "livePreview": True,
    "readableLineLength": True,
}, indent=2)

OBSIDIAN_CORE_PLUGINS = json.dumps([
    "file-explorer", "global-search", "graph", "backlink",
    "outgoing-link", "tag-pane", "properties", "page-preview",
    "command-palette", "editor-status", "bookmarks",
], indent=2)

OBSIDIAN_COMMUNITY_PLUGINS = json.dumps([
    "dataview", "obsidian-excalidraw-plugin", "templater-obsidian",
], indent=2)

OBSIDIAN_GRAPH_JSON = json.dumps({
    "colorGroups": [
        {"query": "path:notes", "color": {"a": 1, "rgb": 2201331}},
        {"query": "path:research", "color": {"a": 1, "rgb": 5025616}},
        {"query": "path:code-reviews", "color": {"a": 1, "rgb": 16098816}},
        {"query": "path:projects", "color": {"a": 1, "rgb": 8388736}},
        {"query": "path:commits", "color": {"a": 1, "rgb": 8421504}},
    ]
}, indent=2)


def scaffold_vault(
    vault_dir: Path,
    repo_id: str,
    clone_path: str,
    references_dir: Path | None = None,
) -> None:
    """Create or update an Obsidian vault for a repo."""
    refs = references_dir or REFERENCES_DIR
    today = date.today().isoformat()
    slug = repo_id_to_slug(repo_id)

    # Create directory structure
    for subdir in [
        "notes", "research", "projects", "commits",
        "code-reviews", "meta", "wiki", "_templates",
        ".obsidian", ".obsidian/snippets",
    ]:
        (vault_dir / subdir).mkdir(parents=True, exist_ok=True)

    # .vault-config.json — create or update clone_paths
    existing_config = read_vault_config(vault_dir)
    if existing_config is not None:
        clone_paths = existing_config.get("clone_paths", [])
        if clone_path not in clone_paths:
            clone_paths.append(clone_path)
            existing_config["clone_paths"] = clone_paths
            write_vault_config(vault_dir, existing_config)
    else:
        write_vault_config(vault_dir, {
            "repo_id": repo_id,
            "repo_slug": slug,
            "repo_root": clone_path,
            "clone_paths": [clone_path],
            "created": today,
            "version": 3,
        })

    # Overview — only if not exists
    overview = vault_dir / "notes" / "overview.md"
    if not overview.exists():
        overview.write_text(OVERVIEW_SKELETON.format(today=today))

    # wiki/hot.md — only if not exists
    hot_md = vault_dir / "wiki" / "hot.md"
    if not hot_md.exists():
        hot_md.write_text(HOT_MD_SKELETON.format(today=today))

    # wiki/log.md — only if not exists
    log_md = vault_dir / "wiki" / "log.md"
    if not log_md.exists():
        log_md.write_text(LOG_MD_SKELETON.format(today=today))

    # meta/dashboard.md — only if not exists
    dashboard = vault_dir / "meta" / "dashboard.md"
    if not dashboard.exists():
        dashboard.write_text(DASHBOARD_SKELETON.format(today=today))

    # RULES.md — only if not exists
    rules_dest = vault_dir / "RULES.md"
    rules_src = refs / "RULES-template.md"
    if not rules_dest.exists() and rules_src.exists():
        shutil.copy2(rules_src, rules_dest)

    # Templates — only if not exist
    templates = {
        "note.md": NOTE_TEMPLATE,
        "research-paper.md": RESEARCH_TEMPLATE,
    }
    for name, content in templates.items():
        tmpl = vault_dir / "_templates" / name
        if not tmpl.exists():
            tmpl.write_text(content)

    # .obsidian configs — always overwrite (these are defaults)
    (vault_dir / ".obsidian" / "app.json").write_text(OBSIDIAN_APP_JSON)
    (vault_dir / ".obsidian" / "core-plugins.json").write_text(OBSIDIAN_CORE_PLUGINS)
    (vault_dir / ".obsidian" / "community-plugins.json").write_text(OBSIDIAN_COMMUNITY_PLUGINS)
    (vault_dir / ".obsidian" / "graph.json").write_text(OBSIDIAN_GRAPH_JSON)


def run(args) -> int:
    try:
        from scripts.repo_id import _resolve_cwd
        clone_path = _resolve_cwd()
        repo_id = resolve_repo_id(cwd=clone_path)
        vault_dir = VAULTS_BASE / repo_id_to_slug(repo_id)
        scaffold_vault(vault_dir, repo_id, clone_path)
        print(f"Scaffolded vault: {vault_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_scaffold.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scaffold.py tests/test_scaffold.py
git commit -m "feat: rewrite scaffold.py for Obsidian vault structure"
```

---

## Task 3: Update `repo_id.py` — Add Vault-Aware Path Helpers

**Files:**
- Modify: `scripts/repo_id.py`
- Modify: `tests/test_repo_id.py`

- [ ] **Step 1: Write failing test for vault-aware path helpers**

Add to `tests/test_repo_id.py`:

```python
class TestVaultAwarePaths:
    def test_get_repo_dir_returns_vault_path(self, monkeypatch):
        from scripts.repo_id import get_repo_dir
        monkeypatch.setattr("scripts.repo_id.resolve_repo_id", lambda cwd=None: "org--my-repo")
        result = get_repo_dir()
        assert "vaults" in str(result)
        assert "org-my-repo" in str(result)

    def test_get_notes_dir_returns_vault_notes_path(self, monkeypatch):
        from scripts.repo_id import get_notes_dir
        monkeypatch.setattr("scripts.repo_id.resolve_repo_id", lambda cwd=None: "org--my-repo")
        result = get_notes_dir()
        assert str(result).endswith("notes")
        assert "vaults" in str(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_repo_id.py::TestGetVaultDir -v`
Expected: FAIL

- [ ] **Step 3: Update repo_id.py — replace get_notes_dir and get_repo_dir with vault-aware versions**

In `scripts/repo_id.py`, replace `get_notes_dir` and `get_repo_dir`:

```python
def get_notes_dir(cwd: str | None = None) -> Path:
    """Return the notes directory — vault-based at ~/vaults/<slug>/notes/."""
    from scripts.vault import get_vault_dir
    repo_id = resolve_repo_id(cwd=cwd)
    return get_vault_dir(repo_id) / "notes"


def get_repo_dir(cwd: str | None = None) -> Path:
    """Return the vault directory for the repo at cwd."""
    from scripts.vault import get_vault_dir
    repo_id = resolve_repo_id(cwd=cwd)
    return get_vault_dir(repo_id)
```

- [ ] **Step 4: Run all repo_id tests**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_repo_id.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/repo_id.py tests/test_repo_id.py
git commit -m "feat: update repo_id.py path helpers to use vault-based storage"
```

---

## Task 4: Update `staleness.py` — Markdown Report Output

**Files:**
- Modify: `scripts/staleness.py`
- Modify: `tests/test_staleness.py`

- [ ] **Step 1: Write failing test for markdown report output**

Add to `tests/test_staleness.py`:

```python
class TestMarkdownReport:
    def test_generates_markdown_with_frontmatter(self, tmp_path):
        from scripts.staleness import generate_staleness_report, NoteReport, StalenessStatus
        reports = [
            NoteReport("notes/auth/index.md", StalenessStatus.STALE, ["src/auth.py"], "abc1234", "1 file changed"),
            NoteReport("notes/api/index.md", StalenessStatus.FRESH, [], "def5678", "0 files changed"),
        ]
        output = generate_staleness_report(reports)
        assert output.startswith("---")
        assert "staleness_check" in output
        assert "STALE" in output
        assert "FRESH" in output
        assert "auth/index.md" in output

    def test_markdown_report_dataview_compatible(self, tmp_path):
        from scripts.staleness import generate_staleness_report, NoteReport, StalenessStatus
        reports = [
            NoteReport("notes/overview.md", StalenessStatus.NO_TRACKING, [], None, "no tracking"),
        ]
        output = generate_staleness_report(reports)
        assert "| Note |" in output
        assert "NO_TRACKING" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_staleness.py::TestMarkdownReport -v`
Expected: FAIL — `generate_staleness_report` not found

- [ ] **Step 3: Add generate_staleness_report function to staleness.py**

Add after the existing `format_report` function:

```python
def generate_staleness_report(reports: list[NoteReport]) -> str:
    """Generate a Dataview-compatible markdown staleness report."""
    from datetime import date
    today = date.today().isoformat()

    lines = [
        "---",
        f"staleness_check: {today}",
        f"total_notes: {len(reports)}",
        f"stale_count: {sum(1 for r in reports if r.status == StalenessStatus.STALE)}",
        f"fresh_count: {sum(1 for r in reports if r.status == StalenessStatus.FRESH)}",
        "---",
        "# Staleness Report",
        "",
        "| Note | Status | Changed Files | Commit |",
        "|------|--------|---------------|--------|",
    ]

    for r in reports:
        note_name = Path(r.note_path).as_posix()
        changed = ", ".join(r.changed_files[:5])
        if len(r.changed_files) > 5:
            changed += f" (+{len(r.changed_files) - 5} more)"
        commit = r.commit or "—"
        lines.append(f"| {note_name} | {r.status.value} | {changed} | {commit} |")

    return "\n".join(lines) + "\n"


def write_staleness_report(vault_dir: Path, reports: list[NoteReport]) -> Path:
    """Write staleness report to meta/staleness-report.md in the vault."""
    report_path = vault_dir / "meta" / "staleness-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(generate_staleness_report(reports), encoding="utf-8")
    return report_path
```

- [ ] **Step 4: Update the `run()` function to use vault paths and write markdown report**

Replace `REPO_NOTES_BASE` references with vault-based resolution. In the `run()` function, after computing reports, call `write_staleness_report` in addition to `save_cache`:

```python
def run(args) -> int:
    try:
        from scripts.vault import resolve_vault, VAULTS_BASE, list_vaults

        if getattr(args, "all_repos", False):
            results = check_all_vaults(VAULTS_BASE)
            for repo_id, reports in results.items():
                print(f"\n=== {repo_id} ===")
                print(format_report(reports))
            return 0

        explicit_id = getattr(args, "repo_id", None)
        if explicit_id:
            from scripts.vault import get_vault_dir
            vault_dir = get_vault_dir(explicit_id)
            notes_dir = vault_dir / "notes"
        else:
            from scripts.repo_id import get_repo_dir, get_notes_dir
            vault_dir = get_repo_dir()
            notes_dir = get_notes_dir()

        if not getattr(args, "no_cache", False) and is_cache_valid(vault_dir):
            cached = load_cache(vault_dir)
            if cached:
                print("(cached)")
                for r in cached:
                    print(f"  {r['status']}: {Path(r['note_path']).name}")
                return 0

        from scripts.repo_id import _resolve_cwd
        repo_root = Path(_resolve_cwd())

        reports = check_all_notes(notes_dir, repo_root)
        save_cache(vault_dir, reports)
        write_staleness_report(vault_dir, reports)

        if getattr(args, "json", False):
            print(json.dumps([r.to_dict() for r in reports], indent=2))
        else:
            print(format_report(reports))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

Also add a `check_all_vaults` function:

```python
def check_all_vaults(vaults_base: Path) -> dict[str, list[NoteReport]]:
    """Check staleness for all vaults in ~/vaults/."""
    from scripts.vault import read_vault_config

    results: dict[str, list[NoteReport]] = {}
    if not vaults_base.is_dir():
        return results

    for vault_dir in sorted(vaults_base.iterdir()):
        if not vault_dir.is_dir() or vault_dir.name.startswith("."):
            continue

        config = read_vault_config(vault_dir)
        if config is None:
            continue

        repo_id = config.get("repo_id", vault_dir.name)
        clone_paths = config.get("clone_paths", [])

        valid_clone = _find_valid_clone_from_list(clone_paths, repo_id)
        if valid_clone is None:
            print(f"WARNING: {repo_id} — no valid clone path found, skipping")
            results[repo_id] = []
            continue

        notes_dir = vault_dir / "notes"
        reports = check_all_notes(notes_dir, valid_clone)
        write_staleness_report(vault_dir, reports)
        results[repo_id] = reports

    return results


def _find_valid_clone_from_list(clone_paths: list[str], expected_repo_id: str) -> Optional[Path]:
    """Find first valid clone from a list of paths."""
    from scripts.repo_id import get_repo_id

    for path_str in clone_paths:
        clone_path = Path(path_str)
        if not clone_path.is_dir() or not (clone_path / ".git").exists():
            continue
        try:
            if get_repo_id(str(clone_path)) == expected_repo_id:
                return clone_path
        except Exception:
            continue
    return None
```

- [ ] **Step 5: Run all staleness tests**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_staleness.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/staleness.py tests/test_staleness.py
git commit -m "feat: staleness.py outputs markdown report, uses vault paths"
```

---

## Task 5: Write Migration Script (`migrate_to_vault`)

**Files:**
- Modify: `scripts/migrate.py`
- Create: `tests/test_migrate_to_vault.py`

- [ ] **Step 1: Write failing tests for link conversion**

```python
# tests/test_migrate_to_vault.py
"""Tests for v2→v3 migration (repo_notes → Obsidian vault)."""

import re
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_migrate_to_vault.py -v`
Expected: FAIL — functions not found

- [ ] **Step 3: Add migration functions to migrate.py**

Add these functions to `scripts/migrate.py`:

```python
import json
from scripts.vault import repo_id_to_slug, VAULTS_BASE, write_vault_config

NN_PREFIX_RE = re.compile(r"^\d{2}-(.+)$")
NAV_BAR_RE = re.compile(r"^>\s*\*\*(navigation|sub-topics):\*\*.*$", re.IGNORECASE)
MD_LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")


def strip_nn_prefix(name: str) -> str:
    """Strip NN- prefix from a file or directory name."""
    m = NN_PREFIX_RE.match(name)
    return m.group(1) if m else name


def build_rename_map(source_dir: Path) -> dict[str, str]:
    """Build a mapping from old filenames to new (prefix-stripped) filenames."""
    rename_map = {}
    for item in source_dir.rglob("*"):
        old_name = item.name
        new_name = strip_nn_prefix(item.stem)
        if item.is_file():
            new_name = new_name + item.suffix
        if old_name != new_name:
            rename_map[old_name] = new_name
    return rename_map


def convert_relative_link_to_wikilink(
    label: str,
    url: str,
    rename_map: dict[str, str],
) -> str | None:
    """Convert a markdown relative link to an Obsidian wikilink.

    Returns None if the link should be left unchanged (external URL, anchor).
    """
    if _is_external_url(url) or _is_anchor_link(url):
        return None

    # Resolve the target filename
    target_path = Path(url)
    target_name = target_path.name

    # Apply rename map
    if target_name in rename_map:
        target_name = rename_map[target_name]

    # Handle PNG → excalidraw
    if target_name.endswith(".png"):
        stem = strip_nn_prefix(Path(target_name).stem)
        return f"![[{stem}.excalidraw]]"

    # Build wikilink
    stem = strip_nn_prefix(Path(target_name).stem)

    # If the path has directory components, include the parent folder
    parts = list(target_path.parts)
    # Remove relative prefixes (., ..)
    clean_parts = [p for p in parts[:-1] if p not in (".", "..")]
    clean_parts = [strip_nn_prefix(p) for p in clean_parts]

    if clean_parts:
        wiki_target = "/".join(clean_parts) + "/" + stem
    else:
        wiki_target = stem

    if label and label != stem:
        return f"[[{wiki_target}|{label}]]"
    return f"[[{wiki_target}]]"


def strip_nav_bars(content: str) -> str:
    """Remove navigation bar and sub-topics bar lines from content."""
    lines = content.split("\n")
    filtered = [line for line in lines if not NAV_BAR_RE.match(line.strip())]
    return "\n".join(filtered)


def convert_links_in_content(content: str, rename_map: dict[str, str]) -> str:
    """Convert all markdown relative links to wikilinks in content."""
    def replace_link(match: re.Match) -> str:
        is_image = match.group(1) == "!"
        label = match.group(2)
        url = match.group(3)

        wikilink = convert_relative_link_to_wikilink(label, url, rename_map)
        if wikilink is None:
            return match.group(0)
        return wikilink

    return MD_LINK_RE.sub(replace_link, content)


def migrate_to_vault(
    source_dir: Path,
    repo_id: str,
    clone_path: str,
    dry_run: bool = False,
) -> dict:
    """Migrate v2 repo_notes to v3 Obsidian vault.

    Returns summary dict with counts and issues.
    """
    from scripts.scaffold import scaffold_vault

    slug = repo_id_to_slug(repo_id)
    vault_dir = VAULTS_BASE / slug

    if dry_run:
        # Count what would be migrated
        md_count = len(list(source_dir.rglob("*.md")))
        excalidraw_count = len(list(source_dir.rglob("*.excalidraw")))
        png_count = len(list(source_dir.rglob("*.png")))
        return {
            "dry_run": True,
            "vault_dir": str(vault_dir),
            "files_to_copy": md_count + excalidraw_count,
            "pngs_to_skip": png_count,
        }

    # Step 1: Scaffold vault
    scaffold_vault(vault_dir, repo_id, clone_path)

    # Step 2: Build rename map from source
    rename_map = build_rename_map(source_dir)

    # Step 3: Copy files with prefix stripping (skip .png)
    files_copied = 0
    for src_file in source_dir.rglob("*"):
        if not src_file.is_file():
            continue
        if src_file.suffix not in (".md", ".excalidraw"):
            continue

        # Compute destination with stripped prefixes
        rel = src_file.relative_to(source_dir)
        new_parts = [strip_nn_prefix(p) for p in rel.parts]
        dest_file = vault_dir / Path(*new_parts)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        files_copied += 1

    # Step 4: Convert links and strip nav bars in all .md files
    links_converted = 0
    broken_links = []
    for md_file in vault_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        original = content

        content = strip_nav_bars(content)
        content = convert_links_in_content(content, rename_map)

        if content != original:
            md_file.write_text(content, encoding="utf-8")
            links_converted += 1

    # Step 5: Seed hot.md from overview if overview exists
    overview = vault_dir / "notes" / "overview.md"
    hot_md = vault_dir / "wiki" / "hot.md"
    if overview.exists() and hot_md.exists():
        overview_content = overview.read_text(encoding="utf-8")
        # Extract first paragraph after frontmatter
        lines = overview_content.split("\n")
        in_frontmatter = False
        summary_lines = []
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            if line.startswith("#"):
                continue
            if line.strip() and not line.startswith("```"):
                summary_lines.append(line.strip())
                if len(summary_lines) >= 5:
                    break

        if summary_lines:
            from datetime import date
            hot_content = f"---\nupdated: {date.today().isoformat()}\n---\n# Session Context\n\n"
            hot_content += "Migrated from v2 notes.\n\n"
            hot_content += "\n".join(summary_lines) + "\n"
            hot_md.write_text(hot_content, encoding="utf-8")

    return {
        "dry_run": False,
        "vault_dir": str(vault_dir),
        "files_copied": files_copied,
        "links_converted": links_converted,
        "broken_links": broken_links,
    }


def run_migrate_to_vault(args) -> int:
    """CLI entry point for migrate-to-vault command."""
    from scripts.repo_id import resolve_repo_id

    dry_run = getattr(args, "dry_run", False)
    migrate_all = getattr(args, "all", False)
    explicit_id = getattr(args, "repo_id", None)

    old_base = Path.home() / ".claude" / "repo_notes"
    if not old_base.is_dir():
        print("No ~/.claude/repo_notes/ directory found.", file=sys.stderr)
        return 1

    targets = []
    if migrate_all:
        for d in sorted(old_base.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                targets.append((d.name, d))
    elif explicit_id:
        d = old_base / explicit_id
        if d.is_dir():
            targets.append((explicit_id, d))
        else:
            print(f"No repo_notes found for {explicit_id}", file=sys.stderr)
            return 1
    else:
        # Interactive: list available repos
        repos = [d.name for d in sorted(old_base.iterdir()) if d.is_dir() and not d.name.startswith(".")]
        if not repos:
            print("No repos found in ~/.claude/repo_notes/")
            return 0
        print("Available repos:")
        for i, r in enumerate(repos, 1):
            print(f"  {i}. {r}")
        print("\nUse --repo-id <id> or --all to migrate.")
        return 0

    for repo_id, source_dir in targets:
        # Find clone path from .repo_paths
        repo_paths = source_dir / ".repo_paths"
        clone_path = str(source_dir)
        if repo_paths.is_file():
            lines = [l.strip() for l in repo_paths.read_text().splitlines() if l.strip()]
            if lines:
                clone_path = lines[0]

        print(f"Migrating {repo_id}...")
        result = migrate_to_vault(source_dir, repo_id, clone_path, dry_run=dry_run)

        if dry_run:
            print(f"  [DRY RUN] Would create vault at: {result['vault_dir']}")
            print(f"  Files to copy: {result['files_to_copy']}")
            print(f"  PNGs to skip: {result['pngs_to_skip']}")
        else:
            print(f"  Vault created at: {result['vault_dir']}")
            print(f"  Files copied: {result['files_copied']}")
            print(f"  Files with links converted: {result['links_converted']}")
            if result["broken_links"]:
                print(f"  Broken links: {len(result['broken_links'])}")

    if not dry_run:
        print(f"\nOriginal ~/.claude/repo_notes/ was NOT deleted.")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_migrate_to_vault.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate.py tests/test_migrate_to_vault.py
git commit -m "feat: add migrate-to-vault for v2→v3 Obsidian vault migration"
```

---

## Task 6: Update `__main__.py` — New Commands, Remove Old

**Files:**
- Modify: `scripts/__main__.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing test for new commands**

Add to `tests/test_cli.py`:

```python
def test_help_includes_new_commands(capsys):
    from scripts.__main__ import main
    import sys
    sys.argv = ["scripts", "--help"]
    try:
        main()
    except SystemExit:
        pass
    output = capsys.readouterr().out
    assert "resolve-vault" in output
    assert "list-vaults" in output
    assert "migrate-to-vault" in output


def test_help_excludes_removed_commands(capsys):
    from scripts.__main__ import main
    import sys
    sys.argv = ["scripts", "--help"]
    try:
        main()
    except SystemExit:
        pass
    output = capsys.readouterr().out
    assert "context-index" not in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_cli.py::test_help_includes_new_commands -v`
Expected: FAIL

- [ ] **Step 3: Update __main__.py**

Remove these subparser registrations and dispatch entries: `nav`, `render`, `context-index`.

Add these subparser registrations:

```python
    # resolve-vault
    subparsers.add_parser("resolve-vault", help="Print the vault path for the current repo")

    # list-vaults
    subparsers.add_parser("list-vaults", help="List all Obsidian vaults")

    # migrate-to-vault
    mtv_parser = subparsers.add_parser("migrate-to-vault", help="Migrate repo_notes to Obsidian vault")
    mtv_parser.add_argument("--repo-id", help="Specific repo ID to migrate")
    mtv_parser.add_argument("--all", action="store_true", help="Migrate all repos")
    mtv_parser.add_argument("--dry-run", action="store_true", help="Preview only")
```

Update the dispatch dict:

```python
    dispatch = {
        "repo-id": "scripts.repo_id",
        "scaffold": "scripts.scaffold",
        "stale": "scripts.staleness",
        "commits": "scripts.commits",
        "auto-update": "scripts.cron",
        "cron": "scripts.cron",
        "migrate": "scripts.migrate",
        "stats": "scripts.stats",
        "verify-diagrams": "scripts.verify_diagrams",
        "resolve-vault": "scripts.vault",
        "list-vaults": "scripts.vault",
        "migrate-to-vault": "scripts.migrate",
        "review-forge": "scripts.code_review",
        "review-assess": "scripts.code_review",
        "review-deferred": "scripts.code_review",
        "review-stack": "scripts.code_review",
        "review-loop-state": "scripts.code_review",
        "review-preflight": "scripts.code_review",
        "review-delta": "scripts.code_review",
        "review-status": "scripts.code_review",
        "review-frontmatter": "scripts.code_review",
    }
```

Add dispatch cases:

```python
        elif args.command == "resolve-vault":
            return mod.run_resolve_vault(args)
        elif args.command == "list-vaults":
            return mod.run_list_vaults(args)
        elif args.command == "migrate-to-vault":
            return mod.run_migrate_to_vault(args)
```

- [ ] **Step 4: Run CLI tests**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/__main__.py tests/test_cli.py
git commit -m "feat: update CLI — add vault commands, remove nav/render/context-index"
```

---

## Task 7: Update `cron.py` — Vault-Based Discovery

**Files:**
- Modify: `scripts/cron.py`
- Modify: `tests/test_cron.py`

- [ ] **Step 1: Write failing test for vault-based discovery**

Add to `tests/test_cron.py`:

```python
class TestGetAllStaleVaults:
    def test_discovers_vaults_with_config(self, tmp_path, monkeypatch):
        from scripts import cron
        monkeypatch.setattr(cron, "VAULTS_BASE", tmp_path)

        # Create a vault with config
        vault = tmp_path / "my-repo"
        vault.mkdir()
        (vault / "notes").mkdir()
        config = {"repo_id": "org--my-repo", "clone_paths": [], "version": 3}
        import json
        (vault / ".vault-config.json").write_text(json.dumps(config))

        # Should not crash, returns list
        result = cron.get_all_stale_vaults(tmp_path)
        assert isinstance(result, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_cron.py::TestGetAllStaleVaults -v`
Expected: FAIL — `get_all_stale_vaults` not found

- [ ] **Step 3: Update cron.py**

Replace `REPO_NOTES_BASE` with vault-based paths. Add:

```python
from scripts.vault import VAULTS_BASE, read_vault_config

# Replace REPO_NOTES_BASE usage at module level
LOCK_FILE = VAULTS_BASE / ".cron.lock"
LOG_FILE = VAULTS_BASE / "cron.log"
```

Add `get_all_stale_vaults`:

```python
def get_all_stale_vaults(vaults_base: Path | None = None) -> list[dict]:
    """Scan all vaults and return staleness info."""
    from scripts.staleness import check_all_notes, StalenessStatus, _find_valid_clone_from_list

    base = vaults_base or VAULTS_BASE
    stale_repos = []
    if not base.is_dir():
        return stale_repos

    for vault_dir in sorted(base.iterdir()):
        if not vault_dir.is_dir() or vault_dir.name.startswith("."):
            continue

        config = read_vault_config(vault_dir)
        if config is None:
            continue

        repo_id = config.get("repo_id", vault_dir.name)
        clone_paths = config.get("clone_paths", [])

        clone_path = _find_valid_clone_from_list(clone_paths, repo_id)
        if clone_path is None:
            log_message(f"{repo_id}: skipped — no valid clone path")
            continue

        notes_dir = vault_dir / "notes"
        reports = check_all_notes(notes_dir, clone_path)
        stale_entries = []
        for r in reports:
            if r.status == StalenessStatus.STALE:
                stale_entries.append({
                    "note": r.note_path,
                    "changed_files": r.changed_files,
                    "files_changed": len(r.changed_files),
                })

        if stale_entries:
            total_changed = sum(e["files_changed"] for e in stale_entries)
            stale_repos.append({
                "repo_id": repo_id,
                "total_changed_files": total_changed,
                "stale_notes": stale_entries,
                "clone_path": str(clone_path),
            })

    return stale_repos
```

Update `auto_update_all_repos` to use `get_all_stale_vaults` instead of `get_all_stale_repos`.

Update `build_update_prompt` to reference vault paths instead of `REPO_NOTES_BASE`.

- [ ] **Step 4: Run cron tests**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_cron.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cron.py tests/test_cron.py
git commit -m "feat: cron.py discovers vaults at ~/vaults/ instead of repo_notes"
```

---

## Task 8: Replace Hooks — `vault-git-sync` + Updated `hooks.json`

**Files:**
- Delete: `hooks/context-prime`
- Create: `hooks/vault-git-sync`
- Modify: `hooks/hooks.json`

- [ ] **Step 1: Create vault-git-sync hook script**

```bash
#!/usr/bin/env bash
set -euo pipefail

EVENT="${1:-}"
VAULTS_DIR="$HOME/vaults"

if [ -z "$EVENT" ] || [ "$EVENT" != "post-tool-use" ]; then
  exit 0
fi

# Read stdin to get the file path from the tool use
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except:
    pass
" 2>/dev/null || true)

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Check if the file is inside a vault
if [[ "$FILE_PATH" != "$VAULTS_DIR/"* ]]; then
  exit 0
fi

# Extract vault directory (first two path components under ~/vaults/)
VAULT_DIR=$(echo "$FILE_PATH" | sed -E "s|^($VAULTS_DIR/[^/]+)/.*|\1|")

if [ ! -d "$VAULT_DIR/.git" ]; then
  exit 0
fi

cd "$VAULT_DIR"
git add -A 2>/dev/null || true
git commit -m "auto: $(date -u +%Y-%m-%dT%H:%M:%SZ)" --no-verify 2>/dev/null || true
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x hooks/vault-git-sync
```

- [ ] **Step 3: Write new hooks.json**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "cat \"$(cat ~/vaults/.active-vault 2>/dev/null)/wiki/hot.md\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/vault-git-sync\" post-tool-use",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Update wiki/hot.md in the active vault with a brief summary of what was accomplished this session. Keep it under 500 words. Focus on decisions made, findings, and next steps."
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Delete old context-prime script**

```bash
rm hooks/context-prime
```

- [ ] **Step 5: Commit**

```bash
git add hooks/vault-git-sync hooks/hooks.json
git rm hooks/context-prime
git commit -m "feat: replace context-prime with vault-git-sync hook and hot.md pattern"
```

---

## Task 9: Delete Dropped Scripts and Tests

**Files:**
- Delete: `scripts/nav_links.py`, `scripts/render.py`, `scripts/context_index.py`
- Delete: `tests/test_nav_links.py`, `tests/test_render.py`, `tests/test_context_index.py`
- Delete: `scripts/fonts/DejaVuSansMono.ttf` (only used by render.py)

- [ ] **Step 1: Remove files**

```bash
git rm scripts/nav_links.py scripts/render.py scripts/context_index.py
git rm tests/test_nav_links.py tests/test_render.py tests/test_context_index.py
git rm scripts/fonts/DejaVuSansMono.ttf
rmdir scripts/fonts 2>/dev/null || true
```

- [ ] **Step 2: Remove Pillow from dependencies (only needed by render.py)**

In `pyproject.toml`, remove `"Pillow>=10.0,<12.0"` from dependencies (verify `verify_diagrams.py` doesn't import it — if it does, keep it).

- [ ] **Step 3: Run remaining tests to verify nothing is broken**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest -v`
Expected: All remaining tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove nav_links.py, render.py, context_index.py and their tests"
```

---

## Task 10: Update `stats.py` — Vault Paths

**Files:**
- Modify: `scripts/stats.py`
- Modify: `tests/test_stats.py`

- [ ] **Step 1: Update stats.py to use vault paths**

Replace `get_repo_dir` import and add `code-reviews` to the directory list:

```python
from scripts.repo_id import get_repo_dir


def collect_stats(repo_dir: Path) -> dict:
    """Collect stats for all directories under a vault."""
    dirs = {
        "notes": repo_dir / "notes",
        "research": repo_dir / "research",
        "commits": repo_dir / "commits",
        "projects": repo_dir / "projects",
        "code-reviews": repo_dir / "code-reviews",
    }
    result = {}
    for name, path in dirs.items():
        result[name] = _count_dir(path)
    return result
```

Update `format_stats` to include "code-reviews" in the iteration list.

- [ ] **Step 2: Run stats tests**

Run: `cd /Users/karthik/work1/codebase-notes && uv run pytest tests/test_stats.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/stats.py tests/test_stats.py
git commit -m "feat: stats.py includes code-reviews, uses vault paths"
```

---

## Task 11: Update Shared Context and Skills

**Files:**
- Modify: `references/shared-context.md`
- Modify: All 14 `skills/*/SKILL.md` files

This task updates the documentation layer. Each skill needs vault path resolution, wikilinks, and removal of nav/render steps.

- [ ] **Step 1: Rewrite references/shared-context.md**

Key changes:
- Section 2 (Script Invocation): update command table — remove `nav`, `render`, `context-index`; add `resolve-vault`, `list-vaults`, `migrate-to-vault`
- Section 3 (Auto-Setup): use `resolve-vault` instead of `repo-id` + path math. Write `~/vaults/.active-vault`.
- Section 4 (Context Priming): replace index injection with `wiki/hot.md` pattern
- Section 10 (Note Structure): remove NN- prefixes, replace relative links with wikilinks, remove navigation bar convention
- Section 11 (Diagrams): remove PNG rendering — just create `.excalidraw`, embed with `![[name.excalidraw]]`
- Section 12 (Parallelization): remove render batch step
- Section 13 (Knowledge Map): replace manual table with Dataview query
- Add Section 15: Obsidian Conventions (wikilinks, frontmatter properties, Dataview, Excalidraw embedding, tags)

- [ ] **Step 2: Update all SKILL.md files**

For each skill, make the changes described in the spec Section 8:
- Replace `export REPO_ROOT=... && cd <plugin_root>/scripts && uv run python -m scripts repo-id` with `resolve-vault`
- Replace relative links with wikilinks in all content templates
- Remove `nav` script calls
- Remove `render` script calls
- Add `wiki/hot.md` update step where applicable
- Replace `~/.claude/repo_notes/<repo_id>/` paths with `~/vaults/<slug>/`

- [ ] **Step 3: Commit**

```bash
git add references/shared-context.md skills/
git commit -m "feat: update shared-context and all skills for Obsidian vault workflow"
```

---

## Task 12: Update RULES-template.md

**Files:**
- Modify: `references/RULES-template.md`

- [ ] **Step 1: Update RULES-template.md**

Key changes:
- Replace all relative link examples with wikilink syntax
- Remove navigation bar section
- Remove NN- prefix naming convention
- Update diagram section to reference Excalidraw plugin (no PNG rendering)
- Update image embedding from `![desc](./file.png)` to `![[file.excalidraw]]`

- [ ] **Step 2: Commit**

```bash
git add references/RULES-template.md
git commit -m "docs: update RULES-template for Obsidian conventions"
```

---

## Task 13: Update Plugin Metadata

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `package.json`
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version to 3.0.0 across all files**

This is a major version bump since storage location changes.

In `.claude-plugin/plugin.json`:
```json
{
  "name": "codebase-notes",
  "description": "Generate, explore, and maintain an Obsidian-based knowledge vault for any codebase",
  "version": "3.0.0"
}
```

In `pyproject.toml`:
```toml
version = "3.0.0"
```

In `package.json`:
```json
"version": "3.0.0"
```

In `.claude-plugin/marketplace.json`:
```json
"version": "3.0.0"
```

- [ ] **Step 2: Remove Pillow dependency if unused**

Check if `verify_diagrams.py` imports Pillow. If not, remove from `pyproject.toml` dependencies.

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/ package.json pyproject.toml
git commit -m "chore: bump version to 3.0.0 — Obsidian vault migration"
```

---

## Task 14: Final Integration Test

**Files:**
- None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/karthik/work1/codebase-notes && uv run pytest -v
```

Expected: All tests PASS. No import errors from removed modules.

- [ ] **Step 2: Verify no references to removed modules**

```bash
grep -r "nav_links\|render\|context_index" scripts/ tests/ --include="*.py" | grep -v "__pycache__"
```

Expected: No matches (or only in migrate.py for v1→v2 backward compat).

- [ ] **Step 3: Verify no references to old storage path**

```bash
grep -r "repo_notes" scripts/ tests/ --include="*.py" | grep -v "__pycache__" | grep -v "migrate.py"
```

Expected: No matches outside migrate.py (which preserves v1→v2 path for backward compat).

- [ ] **Step 4: Dry-run migration test (manual)**

If you have existing notes at `~/.claude/repo_notes/`:

```bash
cd /Users/karthik/work1/codebase-notes && uv run python -m scripts migrate-to-vault --dry-run --all
```

Expected: Shows preview of what would be migrated without writing files.
