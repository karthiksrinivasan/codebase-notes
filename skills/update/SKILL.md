---
name: update
description: Update stale codebase notes by detecting code changes since last update, re-exploring affected areas, and refreshing note content in-place.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/update/SKILL.md` → plugin root is `../../`.

# Update Stale Notes

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `TOPIC` | No | Specific topic to update. If omitted, shows all stale notes and asks which to update. |
| `--all` | No | Update all stale notes without prompting |
| `--force` | No | Re-explore even for fresh notes |

**Examples:**
- `/codebase-notes:update authentication` — Update notes for the authentication topic
- `/codebase-notes:update --all` — Update all stale notes without prompting

---

You are updating codebase notes that have become stale due to code changes.

## Step 0: Resolve Vault Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts resolve-vault
```

Notes are at: `~/vaults/<slug>/notes/`

## Step 1: Check Staleness

Read `meta/staleness-report.md` if it exists for a recent cached report. For a fresh check:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --no-cache
```

This shows which notes are FRESH, STALE, or NO_TRACKING, along with the specific files that changed.

If a specific `TOPIC` was provided, focus on that topic's notes only. If `--all` was passed, update all stale notes. If `--force` was passed, re-explore and update even notes that are currently FRESH.

## Step 2: Prioritize Updates

For each STALE note, examine the changed files:

- **Minor changes** (a few files, no new modules) — verify specifics in code, make targeted edits
- **Major changes** (new files, restructured, many modifications) — re-explore the area

Present the stale notes to the user with change summaries. Let them prioritize unless `--all` was specified.

## Step 3: Update Notes

For each note being updated:

1. Read the existing note to understand current coverage
2. Read the changed files to understand what's different
3. Update the note in-place — prefer editing over rewriting
4. Update the `git_tracked_paths` commit hashes in frontmatter
5. Update `last_updated` date
6. Check every section for diagram coverage — each section describing relationships or flows MUST have a diagram. Add missing diagrams (embed with `![[filename.png]]`), update stale ones.
7. Ensure cross-references use wikilinks (`[[note-name]]`), not relative markdown links.

## Step 4: Verify Diagram Coverage

**MANDATORY** — run the diagram verifier after updating notes:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams
```

If any HIGH or MEDIUM issues are reported for the updated notes, go back and create the missing diagrams before reporting to the user.

## Step 5: Update wiki/hot.md

After completing updates, refresh `wiki/hot.md`:

- Update the "Stale / Needs Attention" section to remove notes that were just updated
- Add any new findings to "Recent Findings"
- Update `last_updated` date

## Step 6: Report

Show the user what was updated and present options for further exploration.
