---
description: Migrate v1 codebase notes (stored in-repo at docs/notes/) to the v2 centralized location at ~/.claude/repo_notes/. Copies files, updates links, and reports any broken references.
argument-hint: "[--from PATH]"
---

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
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
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
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts migrate --from <path>
```

This will:
- Copy all `.md`, `.excalidraw`, `.png` files preserving directory structure
- Update internal links between notes
- Report any broken links that can't be auto-fixed
- NOT delete the source directory

## Step 3: Scaffold Missing Structure

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts scaffold
```

This ensures the notes directory has all required structure (commits/, .repo_paths, etc.).

## Step 4: Rebuild Navigation

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render
```

## Step 5: Report

Tell the user:
- How many files were migrated
- Where the new notes live
- Any broken links that need manual attention
- That the original directory was NOT deleted (they can remove it when ready)
- Suggest adding `docs/notes/` to `.gitignore` if it was tracked
