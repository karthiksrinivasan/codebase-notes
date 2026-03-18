---
description: Show the full knowledge map with staleness status for all notes. Quick overview of what's documented, what's stale, and what's missing.
argument-hint: "[--all-repos] [--verbose]"
allowed-tools: ["Read", "Bash(cd ~/.claude/*)", "Bash(uv run*)", "Glob"]
---

# Notes Status / Knowledge Map

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--all-repos` | No | Show status for all repos, not just the current one |
| `--verbose` | No | Show changed files for stale notes |

**Examples:**
- `/codebase-notes:status` — Show knowledge map for the current repo
- `/codebase-notes:status --verbose` — Include changed file details for stale notes

---

You are showing the current status of all codebase notes.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

Notes are at: `~/.claude/repo_notes/<repo_id>/notes/`

## Step 1: Read Overview

```
Read ~/.claude/repo_notes/<repo_id>/notes/00-overview.md
```

## Step 2: Check Staleness

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale --no-cache
```

If `--all-repos` was specified, check all repos:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale --all-repos --no-cache
```

## Step 3: Present Knowledge Map

Combine the overview's topic list with staleness data to present. If `--verbose` was specified, include the list of changed files for each stale note:

```
Knowledge Map for <repo>
========================

| # | Topic | Status | Notes | Last Updated |
|---|-------|--------|-------|--------------|
| 1 | API Layer | FRESH | 01-api/ (3 notes) | 2026-03-18 |
| 2 | Data Models | STALE (7 files) | 02-models/ (2 notes) | 2026-03-10 |
| 3 | Auth System | — | not yet explored | — |
| 4 | Config | FRESH | 04-config/ (1 note) | 2026-03-17 |

Suggested actions:
- Topic 2 (Data Models) has 7 changed files — run /codebase-notes:update
- Topic 3 (Auth System) not explored — run /codebase-notes:explore Auth
```

## Step 4: Offer Actions

Based on the status, suggest:
- `/codebase-notes:update` for stale notes
- `/codebase-notes:explore TOPIC` for unexplored areas
- `/codebase-notes:research TOPIC` for shallow notes that need depth
- `/codebase-notes:commit-explore` if there are recent commits in stale areas
