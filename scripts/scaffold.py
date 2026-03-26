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

INDEX_CONTENT = """\
# Codebase Notes

This directory contains structured knowledge about the repository, organized into four areas:

## `notes/`

Architecture and design notes about the codebase itself. Each note covers a topic
(API layer, data models, auth system, etc.) with Excalidraw diagrams, key file references,
and links to related notes. Start with `notes/00-overview.md` for the knowledge map.

Managed by: `/codebase-notes:init`, `/codebase-notes:explore`, `/codebase-notes:update`

## `commits/`

Structured summaries of recent git activity, grouped by author and code area.
Useful for onboarding, understanding what changed recently, or preparing release notes.

Managed by: `/codebase-notes:commits`

## `research/`

Notes from external sources — papers, articles, blog posts, and documentation.
Organized by topic with relevance tags linking back to codebase areas.

Managed by: `/codebase-notes:research`

## `projects/`

Brainstorming, planning, and tracking notes for ongoing projects within the codebase.
Each project gets its own subdirectory with design docs, open questions, and decision logs.

Managed by: `/codebase-notes:project`

## `code-reviews/`

Multi-persona code reviews for PRs and feature branches. Each review contains
onboarding context (pre-reqs, motivation, scope) and structured feedback from
four review personas: Systems Architect, Domain Expert, Standards Compliance,
and Adversarial Path Tracer.

Managed by: `/codebase-notes:code-review`
"""

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
    research_dir = repo_dir / "research"
    projects_dir = repo_dir / "projects"

    code_reviews_dir = repo_dir / "code-reviews"

    notes_dir.mkdir(parents=True, exist_ok=True)
    commits_dir.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)
    projects_dir.mkdir(parents=True, exist_ok=True)
    code_reviews_dir.mkdir(parents=True, exist_ok=True)

    rules_dest = notes_dir / "RULES.md"
    rules_src = REFERENCES_DIR / "RULES-template.md"
    if not rules_dest.exists() and rules_src.exists():
        shutil.copy2(rules_src, rules_dest)

    overview = notes_dir / "00-overview.md"
    if not overview.exists():
        overview.write_text(OVERVIEW_SKELETON.format(today=date.today().isoformat()))

    index_file = repo_dir / "index.md"
    if not index_file.exists():
        index_file.write_text(INDEX_CONTENT)

    # Patch existing index.md to include code-reviews section if missing
    if index_file.exists():
        content = index_file.read_text(encoding="utf-8")
        if "code-reviews" not in content:
            code_reviews_section = (
                '\n## `code-reviews/`\n\n'
                'Multi-persona code reviews for PRs and feature branches. Each review contains\n'
                'onboarding context (pre-reqs, motivation, scope) and structured feedback from\n'
                'four review personas: Systems Architect, Domain Expert, Standards Compliance,\n'
                'and Adversarial Path Tracer.\n\n'
                'Managed by: `/codebase-notes:code-review`\n'
            )
            index_file.write_text(content + code_reviews_section, encoding="utf-8")

    _register_clone_path(repo_dir, clone_path)


def run(args) -> int:
    try:
        from scripts.repo_id import _resolve_cwd
        clone_path = _resolve_cwd()
        repo_id = resolve_repo_id(cwd=clone_path)
        scaffold_repo(repo_id, clone_path)
        print(f"Scaffolded: {REPO_NOTES_BASE / repo_id}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
