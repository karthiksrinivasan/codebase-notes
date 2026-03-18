---
description: Check the staleness status of all codebase notes, showing which notes are fresh, stale, or untracked. Presents a knowledge map with actionable next steps.
argument-hint: "[--all-repos] [--no-cache]"
---

# Check Notes Staleness

You are checking the freshness of codebase notes.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

## Step 1: Run Staleness Check

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale --no-cache
```

If `--all-repos` was specified:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale --all-repos --no-cache
```

## Step 2: Present Results

Format the staleness report as a clear Knowledge Map table:

| Note | Status | Changed Files | Last Updated |
|------|--------|---------------|--------------|
| 00-overview.md | FRESH | 0 | 2026-03-18 |
| 01-api/index.md | STALE (5 files) | src/api/router.py, ... | 2026-03-10 |
| 02-models/index.md | NO_TRACKING | — | — |

## Step 3: Suggest Actions

Based on the results, suggest:

- **For STALE notes**: "Run `/codebase-notes:update` to refresh these notes"
- **For NO_TRACKING notes**: "These notes lack git freshness tracking. Consider adding `git_tracked_paths` frontmatter"
- **For all FRESH**: "All notes are up to date!"

If there are stale notes, offer to update them immediately.
