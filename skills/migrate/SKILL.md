---
name: migrate
description: Migrate codebase notes to the current storage format. Supports v1 (in-repo) → v2 (centralized ~/.claude/repo_notes/) and v2 → v3 (Obsidian vault at ~/vaults/).
allowed-tools: ["Read", "Bash", "Glob"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/migrate/SKILL.md` → plugin root is `../../`.

# Migrate Notes

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--from PATH` | No | Path to v1 notes directory for v1→v2 migration. Auto-detected if omitted. |
| `--to-vault` | No | Migrate v2 notes to Obsidian vault (v2→v3). Default when v2 notes exist. |
| `--all` | No | Migrate all repos (used with `--to-vault`) |
| `--dry-run` | No | Preview migration without writing |

**Examples:**
- `/codebase-notes:migrate` — Auto-detect migration type and run
- `/codebase-notes:migrate --to-vault` — Migrate v2 notes to Obsidian vault
- `/codebase-notes:migrate --to-vault --all` — Migrate all repos to vaults
- `/codebase-notes:migrate --to-vault --dry-run` — Preview v2→v3 migration
- `/codebase-notes:migrate --from docs/notes/` — Migrate v1 notes from specific path

---

You are migrating codebase notes from an older storage format to the current one.

## Step 0: Detect Migration Type

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts resolve-vault
```

Then determine which migration is needed:

1. **v2→v3 (most common):** v2 notes exist at `~/.claude/repo_notes/<repo_id>/` but no vault at `~/vaults/<slug>/`. Use `migrate-to-vault`.
2. **v1→v2:** Notes exist inside the repo (at paths like `docs/notes/`, `notes/`, `docs/knowledge/`). Use `migrate`.
3. **Already current:** Vault exists at `~/vaults/<slug>/` — no migration needed.

---

## v2 → v3 Migration (Obsidian Vault)

This is the standard migration for users upgrading from v2 (centralized `~/.claude/repo_notes/`) to v3 (Obsidian vault at `~/vaults/`).

### Step 1: Preview

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault --dry-run
```

Review what will be migrated: file counts, naming changes (NN- prefix removal), link conversions.

### Step 2: Run Migration

For the current repo:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault
```

For all repos at once:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault --all
```

For a specific repo by ID:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault --repo-id anthropics--claude-code --dry-run
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault --repo-id anthropics--claude-code
```

The migration:
1. Creates `~/vaults/<slug>/` with `.obsidian/` configuration
2. Copies all `.md` and `.excalidraw` files preserving directory structure
3. Converts relative markdown links to Obsidian wikilinks
4. Removes `NN-` numeric prefixes from filenames and all internal references
5. Converts `![desc](./file.png)` image embeds to `![[file.excalidraw]]` where source exists
6. Removes navigation bar lines (`> **Navigation:**`, `> **Sub-topics:**`)
7. Creates `wiki/hot.md` with a blank session context template
8. Reports any links that couldn't be auto-converted (need manual attention)
9. Does NOT delete the original `~/.claude/repo_notes/<repo_id>/` directory

### Step 3: Scaffold Missing Structure

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold
```

### Step 4: Report

Tell the user:
- How many files were migrated
- Where the new vault lives (`~/vaults/<slug>/`)
- Any links that need manual attention
- That the original `~/.claude/repo_notes/<repo_id>/` was NOT deleted

---

## v1 → v2 Migration (Legacy In-Repo Notes)

For users migrating from v1 notes stored inside the repo (e.g., `docs/notes/`).

### Step 1: Detect v1 Notes

If `--from` was not specified, check common v1 locations:
- `docs/notes/`
- `notes/`
- `docs/knowledge/`

Look for a `00-overview.md` file as the marker.

If no v1 notes are found, tell the user and suggest `/codebase-notes:init` instead.

### Step 2: Run Migration

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate --from <path>
```

This will:
- Copy all `.md`, `.excalidraw`, `.png` files preserving directory structure to `~/.claude/repo_notes/<repo_id>/`
- Update internal links between notes
- Report any broken links that can't be auto-fixed
- NOT delete the source directory

### Step 3: Scaffold Missing Structure

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold
```

### Step 4: (Optional) Continue to v3

After v1→v2 migration, consider immediately migrating to v3 (Obsidian vault):

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault
```

### Step 5: Report

Tell the user:
- How many files were migrated
- Where the notes now live
- Any broken links that need manual attention
- That the original directory was NOT deleted (they can remove it when ready)
- Suggest adding the old notes path to `.gitignore` if it was tracked
