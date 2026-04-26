"""Scaffold Obsidian vault structure for a repo."""

import json
import shutil
import sys
from datetime import date
from pathlib import Path

from scripts.repo_id import resolve_repo_id
from scripts.vault import repo_id_to_slug, VAULTS_BASE, read_vault_config, write_vault_config

REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"

# ---------------------------------------------------------------------------
# Skeleton content
# ---------------------------------------------------------------------------

OVERVIEW_SKELETON = """\
---
git_tracked_paths: []
last_updated: {today}
---
# Codebase Overview

> **Navigation:** This is the root knowledge map for the vault.

```dataview
TABLE status, file.mtime as "Last Updated"
FROM "notes"
WHERE file.name != "overview"
SORT file.name ASC
```

## Topics

_No topics yet. Run exploration to populate._

## Key Files

| File | Purpose |
|------|---------|
| | |
"""

HOT_SKELETON = """\
---
last_updated: {today}
---
# Hot Topics

Active threads, open questions, and things to watch.

- _Nothing yet._
"""

LOG_SKELETON = """\
---
last_updated: {today}
---
# Session Log

Chronological log of exploration and research sessions.

| Date | Activity | Notes |
|------|----------|-------|
| | | |
"""

DASHBOARD_SKELETON = """\
---
last_updated: {today}
---
# Dashboard

## Stale Notes

```dataview
TABLE file.mtime as "Last Modified"
FROM "notes"
WHERE date(now) - file.mtime > dur(14 days)
SORT file.mtime ASC
```

## Research

```dataview
TABLE status, source
FROM "research"
SORT file.mtime DESC
LIMIT 10
```

## Recent Code Reviews

```dataview
TABLE file.mtime as "Reviewed"
FROM "code-reviews"
SORT file.mtime DESC
LIMIT 10
```
"""

NOTE_TEMPLATE = """\
---
title: "{{title}}"
date: {{date}}
status: draft
tags: []
---
# {{title}}

## Summary

## Details

## Related Notes
"""

RESEARCH_PAPER_TEMPLATE = """\
---
title: "{{title}}"
date: {{date}}
source: ""
status: unread
relevance: []
tags: []
---
# {{title}}

## Key Points

## Relevance to Codebase

## Notes
"""

# ---------------------------------------------------------------------------
# Obsidian config files
# ---------------------------------------------------------------------------

OBSIDIAN_APP = {
    "strictLineBreaks": True,
    "showFrontmatter": True,
    "livePreview": True,
    "readableLineLength": True,
}

OBSIDIAN_CORE_PLUGINS = [
    "file-explorer",
    "global-search",
    "graph",
    "backlink",
    "outgoing-link",
    "tag-pane",
    "properties",
    "page-preview",
    "command-palette",
    "editor-status",
    "bookmarks",
]

OBSIDIAN_COMMUNITY_PLUGINS = [
    "dataview",
    "obsidian-excalidraw-plugin",
    "templater-obsidian",
]

EXCALIDRAW_PLUGIN_CONFIG = {
    "autoexportPNG": True,
    "autoexportSVG": False,
    "width": 1600,
    "compatibilityMode": True,
    "loadPropertySuggestions": True,
}

OBSIDIAN_GRAPH = {
    "colorGroups": [
        {"query": "path:notes", "color": {"a": 1, "h": 212, "s": 100, "l": 50}},
        {"query": "path:research", "color": {"a": 1, "h": 120, "s": 60, "l": 40}},
        {"query": "path:code-reviews", "color": {"a": 1, "h": 30, "s": 100, "l": 50}},
        {"query": "path:projects", "color": {"a": 1, "h": 270, "s": 60, "l": 50}},
        {"query": "path:commits", "color": {"a": 1, "h": 0, "s": 0, "l": 50}},
    ]
}

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------

VAULT_DIRS = [
    "notes",
    "research",
    "projects",
    "commits",
    "code-reviews",
    "meta",
    "wiki",
    "_templates",
    ".obsidian",
    ".obsidian/snippets",
    ".obsidian/plugins/obsidian-excalidraw-plugin",
]

# ---------------------------------------------------------------------------
# Main scaffolding function
# ---------------------------------------------------------------------------


def scaffold_vault(
    vault_dir: Path,
    repo_id: str,
    clone_path: str,
    references_dir: Path | None = None,
) -> None:
    """Create or update an Obsidian vault for a repository.

    Idempotent: safe to call multiple times. Content files (overview, wiki,
    templates, RULES) are only written if they don't already exist. Obsidian
    config files (.obsidian/) are always overwritten to stay current.
    """
    refs = references_dir or REFERENCES_DIR

    # 1. Create directories
    for d in VAULT_DIRS:
        (vault_dir / d).mkdir(parents=True, exist_ok=True)

    # 2. Create or update .vault-config.json
    config = read_vault_config(vault_dir)
    if config is None:
        config = {
            "repo_id": repo_id,
            "repo_slug": repo_id_to_slug(repo_id),
            "clone_paths": [clone_path],
            "created": date.today().isoformat(),
            "version": 3,
        }
    else:
        if clone_path not in config.get("clone_paths", []):
            config.setdefault("clone_paths", []).append(clone_path)
    write_vault_config(vault_dir, config)

    today = date.today().isoformat()

    # 3. Create notes/overview.md (only if not exists)
    overview = vault_dir / "notes" / "overview.md"
    if not overview.exists():
        overview.write_text(OVERVIEW_SKELETON.format(today=today))

    # 4. Create wiki/hot.md (only if not exists)
    hot = vault_dir / "wiki" / "hot.md"
    if not hot.exists():
        hot.write_text(HOT_SKELETON.format(today=today))

    # 5. Create wiki/log.md (only if not exists)
    log = vault_dir / "wiki" / "log.md"
    if not log.exists():
        log.write_text(LOG_SKELETON.format(today=today))

    # 6. Create meta/dashboard.md (only if not exists)
    dashboard = vault_dir / "meta" / "dashboard.md"
    if not dashboard.exists():
        dashboard.write_text(DASHBOARD_SKELETON.format(today=today))

    # 7. Copy RULES.md from references (only if not exists)
    rules_dest = vault_dir / "RULES.md"
    rules_src = refs / "RULES-template.md"
    if not rules_dest.exists() and rules_src.exists():
        shutil.copy2(rules_src, rules_dest)

    # 8. Create templates (only if not exist)
    note_tpl = vault_dir / "_templates" / "note.md"
    if not note_tpl.exists():
        note_tpl.write_text(NOTE_TEMPLATE)

    research_tpl = vault_dir / "_templates" / "research-paper.md"
    if not research_tpl.exists():
        research_tpl.write_text(RESEARCH_PAPER_TEMPLATE)

    # 9. Write .obsidian/ config files (always overwrite)
    obsidian = vault_dir / ".obsidian"
    _write_json(obsidian / "app.json", OBSIDIAN_APP)
    _write_json(obsidian / "core-plugins.json", OBSIDIAN_CORE_PLUGINS)
    _write_json(obsidian / "community-plugins.json", OBSIDIAN_COMMUNITY_PLUGINS)
    _write_json(obsidian / "graph.json", OBSIDIAN_GRAPH)
    _write_json(
        obsidian / "plugins" / "obsidian-excalidraw-plugin" / "data.json",
        EXCALIDRAW_PLUGIN_CONFIG,
    )


def _write_json(path: Path, data) -> None:
    """Write a JSON file with consistent formatting."""
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run(args) -> int:
    try:
        from scripts.repo_id import _resolve_cwd
        clone_path = _resolve_cwd()
        repo_id = resolve_repo_id(cwd=clone_path)
        slug = repo_id_to_slug(repo_id)
        vault_dir = VAULTS_BASE / slug
        scaffold_vault(vault_dir, repo_id, clone_path)
        print(f"Scaffolded vault: {vault_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
