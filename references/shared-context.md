# Shared Context for Codebase Notes Skills

This document contains shared patterns, rules, and protocols used by all codebase-notes skills. Each skill reads this file for common context.

---

## Resolving Plugin Root

Each skill's SKILL.md is located at `<plugin_root>/skills/<name>/SKILL.md`.
The plugin root is the directory containing `package.json`, `scripts/`, and `references/`.
When this shared context says `<plugin_root>`, substitute the actual resolved path.

---

## 1. Core Philosophy

**Notes are the primary context source.** When any agent (including you) needs to understand part of the codebase, notes should be read FIRST — before exploring code. Notes are pre-digested context that saves tokens and time. Code exploration is the fallback for when notes don't cover what's needed. Every time you learn something new from code, update the relevant note so the next agent doesn't have to re-explore.

**Notes are a knowledge graph, not a document dump.** Each note is a node with links to parent, siblings, and children. The user navigates by choosing what to explore next — you present options, they pick, you go deeper.

**Diagrams argue, text explains.** Every note gets at least one Excalidraw diagram, and every major section within a note that describes relationships or flows gets its own diagram. A note with architecture, data flow, and integration sections needs three diagrams. Text supplements with tables, schemas, and key file references. Never use ASCII art for diagrams — always Excalidraw.

**Text must stand alone.** Diagrams enhance but don't replace text. Every architecture section needs enough written description that a reader with broken images still understands the system. A diagram without a text summary below it is incomplete.

**Capture what code can't tell you.** Focus on architecture, data flow, integration points, and design decisions. Don't repeat what `git log` or reading the source would tell you directly. Notes should answer "why is it built this way?" and "how do the pieces fit together?"

**Self-contained skill.** All deterministic operations (repo ID resolution, scaffolding, staleness checking, navigation links, rendering, commit history, cron) are handled by Python scripts bundled with this plugin. Claude handles content writing, summarization, exploration decisions, and diagram JSON creation.

---

## 2. Script Invocation

All scripts are invoked with the same pattern. Set `REPO_ROOT` to the git root of the user's repo, then `cd` into the scripts directory and run via `uv`:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts <command> [args]
```

**Why `REPO_ROOT`?** The user may be in a subdirectory of their repo. `REPO_ROOT` ensures scripts always resolve the repo identity from the git root, not a subdirectory. The scripts also accept `REPO_CWD` (falls back to deriving the git root from it) and `os.getcwd()` as last resort.

### Command Reference

| Command | Description | Example |
|---------|-------------|---------|
| `repo-id` | Print the repo ID for the current git repo | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id` |
| `scaffold` | Create notes directory structure for current repo | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold` |
| `stale` | Check all notes for staleness | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale` |
| `stale --all-repos` | Check staleness across all repos | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --all-repos` |
| `stale --no-cache` | Force fresh staleness check (skip cache) | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --no-cache` |
| `nav` | Rebuild all navigation links in notes | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts nav` |
| `render` | Render all .excalidraw files to .png | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render` |
| `commits` | Generate commit history notes | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts commits --author "Name"` |
| `auto-update` | Run staleness check + Claude update | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts auto-update` |
| `auto-update --all-repos` | Auto-update all repos | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts auto-update --all-repos` |
| `cron --install` | Install cron auto-update schedule | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts cron --install` |
| `cron --uninstall` | Remove cron auto-update schedule | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts cron --uninstall` |
| `migrate` | Migrate v1 notes to v2 centralized location | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate --from docs/notes` |
| `verify-diagrams` | Check notes for missing diagram coverage | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams` |

---

## 3. Step 0: Auto-Setup and Notes Resolution

**This step is MANDATORY. Run it BEFORE doing anything else.** The skill must always know where notes live before any exploration, reading, or writing happens. Every conversation that activates this skill starts here.

### 0.1 Bootstrap Scripts

Ensure the Python environment is ready:

```bash
cd <plugin_root> && test -d .venv || uv sync
```

If `.venv` doesn't exist, `uv sync` will create it and install all dependencies (PyYAML, Pillow). This only needs to happen once, but always check.

### 0.2 Resolve Notes Path

Run the `repo-id` command to determine where notes are stored for this repo:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

This prints the repo ID (e.g., `anthropics--claude-code`). Notes for this repo live at:

```
~/.claude/repo_notes/<repo_id>/notes/
```

For example: `~/.claude/repo_notes/anthropics--claude-code/notes/`

The repo ID is derived from the git remote URL. All clones of the same repo share the same notes directory. If no git remote exists, a hash-based local ID is used.

**Store this path mentally — every subsequent operation reads from and writes to this location.**

### 0.3 Check for Existing Notes

After resolving the notes path, check if notes already exist:

**If the notes directory has content (contains .md files):** Run the staleness checker to see what's fresh and what needs updating:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale
```

This outputs a report showing FRESH, STALE, or NO_TRACKING for each note. Present the results to the user along with the Knowledge Map from `00-overview.md`. Ask what they want to do: explore more, update stale notes, add detail, etc.

**If the notes directory is empty or doesn't exist:** Run scaffold to create the initial structure:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold
```

This creates the notes directory with a skeleton `00-overview.md` and a `RULES.md` copied from the skill's template. Then proceed to Phase 1.

### 0.4 Check for v1 Notes

If no centralized notes exist, check whether this repo has v1 notes (stored inside the repo itself at paths like `docs/notes`, `notes`, or `docs/knowledge`). Look for a `00-overview.md` file in those locations.

**If v1 notes are found**, offer to migrate them:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate --from docs/notes
```

The migration copies all `.md`, `.excalidraw`, and `.png` files to the centralized location, preserving directory structure. It reports any broken links that pointed outside the notes directory. The original files are NOT deleted — the user can remove them manually.

After migration, re-run Step 0.3 to load the migrated notes.

---

## 4. Context Priming Protocol

Whenever you need to understand part of the codebase — whether for exploration, answering questions, debugging, or feature work — follow this order:

### 4.1 Read Notes First (cheap, pre-digested context)

After resolving the notes path in Step 0, read notes in this order:

1. Read `00-overview.md` in the notes directory to understand the full system map
2. Read the relevant topic's `index.md` to understand the subsystem
3. Read the specific note for the area you need

Notes contain architecture, data flow, schemas, config, key files, and diagrams. This is 10-100x cheaper than re-exploring source code and gives you the "why" that code alone can't.

### 4.2 Fall Back to Code Exploration (when notes are insufficient)

If notes don't cover what you need — a specific function signature, a recently added feature, an edge case — then explore the code. Use the Key Files tables in notes as starting points rather than grepping blindly.

### 4.3 Update Notes with What You Learned (pay it forward)

After learning something new from code exploration, update the relevant note:

- **Minor addition**: Edit the existing note to add the new information
- **New sub-topic**: Create a child note if the topic warrants its own page
- **Correction**: Fix any stale information in existing notes
- **New topic**: Create a new topic folder if the area isn't covered at all

This keeps notes as a living cache of codebase understanding. Every agent session that explores code should leave the notes better than it found them.

### When to Use This Protocol

- **Starting a new conversation**: Run Step 0, then read `00-overview.md`
- **Before exploring code**: Check if notes already cover it
- **After any code exploration**: Update notes with new findings
- **When answering questions about the codebase**: Cite notes, not just code
- **When debugging**: Read the relevant system's note first to understand architecture
- **Working on a feature or bug**: Read notes on the relevant area for context, then update notes if you learned something new

---

## 10. Note Structure

### Directory Layout

Notes are stored at `~/.claude/repo_notes/<repo_id>/`:

```
~/.claude/repo_notes/<repo_id>/
├── notes/
│   ├── 00-overview.md
│   ├── RULES.md
│   ├── 01-topic-name/
│   │   ├── index.md
│   │   ├── 01-subtopic.md
│   │   ├── 01-subtopic.excalidraw
│   │   ├── 01-subtopic.png
│   │   ├── 02-subtopic.md
│   │   └── 03-deep-topic/
│   │       ├── index.md
│   │       ├── 01-detail.md
│   │       └── ...
│   └── 02-topic-name/
│       └── ...
├── research/
│   ├── index.md
│   ├── 01-topic-name/
│   │   ├── index.md
│   │   └── 01-paper-or-article.md
│   └── ...
├── commits/
│   └── author-slug/
│       └── path-slug.md
├── projects/
│   └── project-name/
│       ├── index.md
│       └── ...
└── .repo_paths
```

**Naming:** Folders `NN-topic-name/`, files `NN-subtopic.md`. Each folder has `index.md`. Diagrams sit alongside notes with matching names. Multiple diagrams per note use suffixes: `01-thing-architecture.excalidraw`, `01-thing-dataflow.excalidraw`.

### Note Template

Every note follows this structure:

```markdown
---
git_tracked_paths:
  - path: relative/path/to/source/directory/
    commit: abc1234
last_updated: YYYY-MM-DD
---
# Title

> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)

## What is it?

One paragraph summary.

## Architecture / Overview

![Description](./note-name.png)

Text description of what the diagram shows — how components connect, data flow,
key relationships. This must stand alone without the image.

## [Main sections — tables, schemas, config, API surfaces]

## Key Files

| File | Purpose |
|------|---------|
| `path/to/file.py` | What it does |
```

### Frontmatter

The `git_tracked_paths` frontmatter links the note to the source code directories it documents. Multiple paths can be tracked per note. The `commit` is the short hash from `git log -1 --format=%h -- <path>` at the time the note was written or last updated.

### Navigation Bar

Every note starts with a navigation line after the frontmatter and title:

```markdown
> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)
```

Index files additionally have a Sub-topics line:

```markdown
> **Sub-topics:** [Child A](./01-child-a.md) | [Child B](./02-child-b.md)
```

All links are **relative paths**.

### Content Rules

- **Tables over prose** for structured data (config, endpoints, schemas)
- **Code snippets** only for schemas, key data structures, non-obvious patterns
- **No filler** — no "In this section we will..."
- **No ASCII art** for diagrams — always Excalidraw. ASCII is only acceptable for directory tree listings.
- **Text fallback** for every diagram — written description below that stands alone
- **Cross-referencing** — when a concept spans multiple code areas, define it once in the note matching the code location, cross-reference from others with relative links
- **Mirror codebase structure** — note hierarchy should reflect the source code organization

---

## 11. Diagrams

**Every note needs at least one Excalidraw diagram. Every major section or concept within a note should have its own diagram.** A note about a service with architecture, data flow, and integration sections should have three diagrams — not one. Diagrams are not decoration; they are the primary way readers understand structure and flow. Text explains the nuance; diagrams argue the shape.

### When to Create Diagrams

Create a diagram for each of these within a note:
- **Architecture section** — component layout, layers, boundaries
- **Data flow section** — how data enters, transforms, exits
- **Integration points** — connections to other systems, protocols
- **State or lifecycle** — states an entity moves through
- **Comparison or decision** — trade-offs shown side-by-side
- **Process or workflow** — steps in a sequence

**Rule of thumb:** If a section describes relationships between 2+ things, it needs a diagram. If you're writing "X connects to Y which sends to Z" in prose, that should be a diagram with a text description below.

### Creating Diagrams

1. Create `.excalidraw` JSON section-by-section (not all at once — large diagrams hit token limits)
2. Save the JSON file alongside the note with a matching name (e.g., `01-subtopic.excalidraw`)
3. Render all diagrams:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render
```

4. View the PNG with the Read tool to verify it looks correct
5. Fix issues and re-render until clean
6. Embed in the note with `![description](./filename.png)`

**The renderer outputs `filename.png` (NOT `filename.excalidraw.png`). Always reference `.png` only.**

The render command finds all `.excalidraw` files in the notes directory, skips any that already have an up-to-date `.png`, and renders the rest using a built-in Pillow-based renderer.

### Diagram Types

| Note Type | Diagram Style |
|-----------|--------------|
| Overview/Index | Hub-and-spoke or layered architecture |
| Service/Component | Data flow (request lifecycle, event pipeline) |
| Workflow/Process | State machine or timeline |
| Config/Reference | Hierarchy tree or ecosystem map |

### Style Rules

- `roughness: 0`, `fontFamily: 3`, `opacity: 100`
- Descriptive string IDs (`"backend_rect"`, `"arrow_to_mongo"`)
- Shapes need `boundElements` referencing text; text needs `containerId`
- Arrows need `startBinding`/`endBinding` with `{elementId, focus: 0, gap: 2}`
- Use semantic colors: blue for services, green for data stores, orange for external, purple for async
- Background: white (`#ffffff`)
- Stroke: `#1e1e1e` for borders, colored for arrows between systems

### Image Path Conflicts

Some markdown viewers (like md-serve with Next.js routing) can't serve images whose filename matches a page route. If a root-level image doesn't render, rename it (e.g., `00-overview.png` to `00-overview-architecture.png`).

---

## 12. Parallelization Patterns

### Multiple Topics

When the user asks to explore several topics at once:

```
Launch N Explore agents simultaneously (one per topic)
Write notes as results arrive — don't wait for all to complete
Run nav script after all agents finish to rebuild all links
```

### Batch Diagrams

When creating diagrams across multiple notes:

```
Launch N sub-agents (one per note group) to create .excalidraw JSON
After all complete, render everything in one pass:
```

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render
```

Sub-agents creating diagrams may lack bash permissions — always render centrally after they complete.

### Diving into All Sub-Topics

When the user says "explore everything under topic X":

```
Read the topic's index.md to identify sub-topics
Launch N Explore agents (one per sub-topic)
Write sub-topic notes as results arrive
Update parent index.md with links
Run nav script to fix all navigation
```

---

## 13. Knowledge Map

The Knowledge Map is a table in `00-overview.md` that tracks all topics and their exploration status.

### Format

```markdown
## Knowledge Map

| # | Topic | Status | Notes |
|---|-------|--------|-------|
| 1 | Authentication — login, OAuth, sessions | FRESH | [01-auth/](./01-auth/index.md) |
| 2 | API Layer — REST endpoints, middleware | STALE (5 files) | [02-api/](./02-api/index.md) |
| 3 | Database — models, migrations, queries | — | _not yet explored_ |
| 4 | Background Jobs — workers, queues | FRESH | [04-jobs/](./04-jobs/index.md) |
```

### Update Rules

- **New exploration**: Change `_not yet explored_` to a folder link with FRESH status
- **Staleness check**: Update status column with FRESH, STALE (N files), or NO_TRACKING
- **Sub-topics explored**: Optionally add indented rows with `  ↳ sub-topic`
- **New topics discovered**: Add new rows to the table
- **New topic folders**: Add link to Navigation bar at top of overview

### Generating the Map

After running the staleness checker, update the Knowledge Map to reflect current status. The staleness output gives you FRESH/STALE/NO_TRACKING for each note — map those to the Status column.

---

## 14. v1 to v2 Migration

### What Changed

| Aspect | v1 | v2 |
|--------|----|----|
| Storage location | Inside repo (e.g., `docs/notes`) | Centralized (`~/.claude/repo_notes/<repo_id>/notes/`) |
| Shared across clones | No | Yes — same repo ID, same notes |
| Staleness detection | Manual bash loops | Python script with caching |
| Navigation links | Manual management | Automated via `nav` script |
| Diagram rendering | External skill dependency | Built-in Pillow renderer |
| Commit history | Not supported | `commits` script with author/path grouping |
| Auto-updates | Not supported | Cron-based with Claude |
| Gitignore needed | Yes | No — notes are outside the repo |

### Migration Command

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate --from docs/notes
```

This will:
1. Resolve the repo ID for the current directory
2. Copy all `.md`, `.excalidraw`, and `.png` files preserving directory structure
3. Report any links that point outside the notes directory (need manual fixing)
4. Leave the original directory untouched

### Manual Migration

If the automated migration doesn't handle your case:

1. Run `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id` to get the repo ID
2. Run `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold` to create the target structure
3. Manually copy your notes to `~/.claude/repo_notes/<repo_id>/notes/`
4. Fix any relative links that now point to the wrong location
5. Run `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts nav` to rebuild navigation
6. Run `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render` to re-render diagrams
