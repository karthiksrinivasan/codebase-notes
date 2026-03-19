---
name: check
description: Show the knowledge map with staleness status for all codebase notes. Reports which notes are fresh, stale, or untracked, with actionable suggestions.
allowed-tools: ["Read", "Bash", "Glob"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/check/SKILL.md` → plugin root is `../../`.

# Check Notes Status

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--all-repos` | No | Check all repos, not just the current one |
| `--no-cache` | No | Skip the staleness cache (default: uses 10-min cache) |
| `--json` | No | Output as JSON instead of table |
| `--verbose` | No | Show changed files for stale notes |

**Examples:**
- `/codebase-notes:check` — Show knowledge map with staleness for current repo
- `/codebase-notes:check --all-repos` — Check staleness across all repos
- `/codebase-notes:check --verbose` — Include changed file details

---

You are checking the status and freshness of codebase notes.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

Notes are at: `~/.claude/repo_notes/<repo_id>/notes/`

## Step 0.5: Ensure index.md exists

Run scaffold to ensure `index.md` and all subdirectories exist (idempotent — safe for already-initialized repos):

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold
```

## Step 1: Read Overview

```
Read ~/.claude/repo_notes/<repo_id>/notes/00-overview.md
```

## Step 2: Run Staleness Check

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --no-cache
```

If `--all-repos` was specified:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --all-repos --no-cache
```

## Step 3: Present Knowledge Map

Combine the overview's topic list with staleness data. If `--json` was specified, output as JSON. If `--verbose` was specified, include changed files for stale notes.

```
Knowledge Map for <repo>
========================

| # | Topic | Status | Notes | Last Updated |
|---|-------|--------|-------|--------------|
| 1 | API Layer | FRESH | 01-api/ (3 notes) | 2026-03-18 |
| 2 | Data Models | STALE (7 files) | 02-models/ (2 notes) | 2026-03-10 |
| 3 | Auth System | — | not yet explored | — |
| 4 | Config | FRESH | 04-config/ (1 note) | 2026-03-17 |
```

## Step 4: Suggest Actions

Based on the results:

- **For STALE notes**: "Run `/codebase-notes:update` to refresh these notes"
- **For NO_TRACKING notes**: "These notes lack git freshness tracking. Consider adding `git_tracked_paths` frontmatter"
- **For all FRESH**: "All notes are up to date!"
- **For unexplored topics**: "Run `/codebase-notes:explore TOPIC` to document this area"
- **For recent commits in stale areas**: "Run `/codebase-notes:commits` to see what changed"

If there are stale notes, offer to update them immediately.
