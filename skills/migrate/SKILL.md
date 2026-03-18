---
name: migrate
description: Migrate v1 codebase notes (stored in-repo at docs/notes/) to the v2 centralized location at ~/.claude/repo_notes/. Copies files, preserves structure, and reports broken links.
allowed-tools: ["Read", "Bash", "Glob"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/migrate/SKILL.md` → plugin root is `../../`.

# Migrate v1 Notes to v2

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--from PATH` | No | Path to v1 notes directory. Auto-detected if omitted (checks `docs/notes/`, `notes/`, `docs/knowledge/`). |

**Examples:**
- `/codebase-notes:migrate` — Auto-detect and migrate v1 notes
- `/codebase-notes:migrate --from docs/notes/` — Migrate from a specific path

---

You are migrating existing codebase notes from the old in-repo location to the new centralized storage.

## Step 0: Resolve Repo Identity

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

## Step 1: Detect v1 Notes

If `--from` was not specified, check common v1 locations:
- `docs/notes/`
- `notes/`
- `docs/knowledge/`

Look for a `00-overview.md` file as the marker.

If no v1 notes are found, tell the user and suggest `/codebase-notes:init` instead.

## Step 2: Run Migration

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate --from <path>
```

This will:
- Copy all `.md`, `.excalidraw`, `.png` files preserving directory structure
- Update internal links between notes
- Report any broken links that can't be auto-fixed
- NOT delete the source directory

## Step 3: Scaffold Missing Structure

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold
```

## Step 4: Rebuild Navigation

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts nav
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render
```

## Step 5: Report

Tell the user:
- How many files were migrated
- Where the new notes live
- Any broken links that need manual attention
- That the original directory was NOT deleted (they can remove it when ready)
- Suggest adding the old notes path to `.gitignore` if it was tracked
