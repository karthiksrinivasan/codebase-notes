---
name: notes-stats
version: 2.23.0
description: Display statistics for codebase notes — number of sections, files, lines, and words across notes, research, commits, and projects directories. Use when the user says "how many notes do I have", "show stats", "notes statistics", "note counts", or wants a quantitative overview of their knowledge base.
allowed-tools: ["Read", "Bash"]
---

**Shared context:** Before starting, read `${CLAUDE_PLUGIN_ROOT}/references/shared-context.md` for script invocation patterns, note structure rules, and diagram guidelines.

# Notes Statistics

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--json` | No | Output as JSON instead of a table |

**Examples:**
- `/codebase-notes:notes-stats`
- `/codebase-notes:notes-stats --json`

---

You are displaying statistics about the codebase notes for the current repository.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts repo-id
```

## Step 1: Run Stats Command

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts stats
```

For JSON output:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts stats --json
```

## Step 2: Present Results

Display the output to the user. The stats command shows a table with counts for:

| Directory | What it counts |
|-----------|---------------|
| `notes` | Main codebase notes (topics, subtopics, diagrams) |
| `research` | External research notes (papers, articles, web resources) |
| `commits` | Commit history notes (grouped by author) |
| `projects` | Project brainstorming and planning notes |

Each directory reports: sections (top-level subfolders), files (.md only), lines, and words.

If no notes exist yet, suggest running `/codebase-notes:init` to get started.
