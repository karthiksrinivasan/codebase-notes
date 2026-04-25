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

**Notes are a knowledge graph, not a document dump.** Each note is a node. Navigation happens via Obsidian's backlinks and graph view — not manual navigation bars. Use wikilinks (`[[note]]`, `[[note|alias]]`) to cross-reference notes.

**Diagrams argue, text explains.** Every note gets at least one Excalidraw diagram, and every major section within a note that describes relationships or flows gets its own diagram. A note with architecture, data flow, and integration sections needs three diagrams. Text supplements with tables, schemas, and key file references. Never use ASCII art for diagrams — always Excalidraw. Obsidian renders `.excalidraw` files natively via the Excalidraw plugin — no PNG rendering step needed.

**Text must stand alone.** Diagrams enhance but don't replace text. Every architecture section needs enough written description that a reader with broken images still understands the system. A diagram without a text summary below it is incomplete.

**Capture what code can't tell you.** Focus on architecture, data flow, integration points, and design decisions. Don't repeat what `git log` or reading the source would tell you directly. Notes should answer "why is it built this way?" and "how do the pieces fit together?"

**Self-contained skill.** All deterministic operations (vault resolution, scaffolding, staleness checking, commit history, cron) are handled by Python scripts bundled with this plugin. Claude handles content writing, summarization, exploration decisions, and diagram JSON creation.

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
| `resolve-vault` | Resolve (or create) the Obsidian vault for the current repo; prints vault path | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts resolve-vault` |
| `list-vaults` | List all known vaults under `~/vaults/` | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts list-vaults` |
| `migrate-to-vault` | Migrate v2 notes from `~/.claude/repo_notes/` to an Obsidian vault | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault` |
| `scaffold` | Create vault directory structure for current repo | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold` |
| `stale` | Check all notes for staleness | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale` |
| `stale --all-repos` | Check staleness across all vaults | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --all-repos` |
| `stale --no-cache` | Force fresh staleness check (skip cache) | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --no-cache` |
| `commits` | Generate commit history notes | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts commits --author "Name"` |
| `auto-update` | Run staleness check + Claude update | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts auto-update` |
| `auto-update --all-repos` | Auto-update all vaults | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts auto-update --all-repos` |
| `cron --install` | Install cron auto-update schedule | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts cron --install` |
| `cron --uninstall` | Remove cron auto-update schedule | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts cron --uninstall` |
| `verify-diagrams` | Check notes for missing diagram coverage | `export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams` |

---

## 3. Step 0: Auto-Setup and Vault Resolution

**This step is MANDATORY. Run it BEFORE doing anything else.** The skill must always know where notes live before any exploration, reading, or writing happens. Every conversation that activates this skill starts here.

### 0.1 Bootstrap Scripts

Ensure the Python environment is ready:

```bash
cd <plugin_root> && test -d .venv || uv sync
```

If `.venv` doesn't exist, `uv sync` will create it and install all dependencies. This only needs to happen once, but always check.

### 0.2 Resolve Vault Path

Run `resolve-vault` to determine where notes are stored for this repo:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts resolve-vault
```

This prints the vault slug and full vault path. For example:
- Slug: `anthropics--claude-code`
- Vault path: `~/vaults/anthropics--claude-code/`

Notes for this repo live at:

```
~/vaults/<slug>/notes/
```

For example: `~/vaults/anthropics--claude-code/notes/`

The vault path is also recorded in `~/vaults/.active-vault` for quick reference by subsequent commands.

**Store this path mentally — every subsequent operation reads from and writes to this location.**

### 0.3 Check for Existing Notes

After resolving the vault path, check if notes already exist:

**If the notes directory has content (contains .md files):** Read `meta/staleness-report.md` if it exists for a cached staleness summary, or run a fresh check:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale
```

This outputs a report showing FRESH, STALE, or NO_TRACKING for each note. Present the results to the user along with the Knowledge Map from `overview.md`. Ask what they want to do: explore more, update stale notes, add detail, etc.

**If the notes directory is empty or doesn't exist:** Run scaffold to create the initial structure:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts scaffold
```

This creates the vault with `.obsidian/` config, a skeleton `overview.md`, and a `wiki/hot.md` file. Then proceed to Phase 1.

### 0.4 Check for v2 Notes to Migrate

If no vault exists at `~/vaults/<slug>/`, check whether this repo has v2 notes at `~/.claude/repo_notes/<repo_id>/`. If found, offer migration:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault
```

Use `--dry-run` first to preview, then run without `--dry-run` to execute. After migration, re-run Step 0.2 to load the vault path.

---

## 4. Context Priming Protocol

Whenever you need to understand part of the codebase — whether for exploration, answering questions, debugging, or feature work — follow this order.

### 4.0 Session Context via wiki/hot.md

Each vault has a `wiki/hot.md` file that captures the most recently active context for the repo. It is loaded at session start (SessionStart hook) and updated at session end (Stop hook).

**Read `wiki/hot.md` first.** It contains:
- Currently active topics and their notes paths
- Recent findings and decisions
- Areas that are stale or need attention
- Open questions from the last session

After significant exploration or changes during a session, update `wiki/hot.md` to reflect the current state. This ensures the next session (or next agent) picks up immediately where you left off.

### 4.1 Read Notes First (cheap, pre-digested context)

After resolving the vault path in Step 0, read notes in this order:

1. Read `wiki/hot.md` to understand current session context
2. Read `overview.md` in the notes directory to understand the full system map
3. Read the relevant topic's `index.md` to understand the subsystem
4. Read the specific note for the area you need

Notes contain architecture, data flow, schemas, config, key files, and diagrams. This is 10-100x cheaper than re-exploring source code and gives you the "why" that code alone can't.

### 4.2 Fall Back to Code Exploration (when notes are insufficient)

If notes don't cover what you need — a specific function signature, a recently added feature, an edge case — then explore the code. Use the Key Files tables in notes as starting points rather than grepping blindly.

### 4.3 Update Notes with What You Learned (pay it forward)

After learning something new from code exploration, update the relevant note:

- **Minor addition**: Edit the existing note to add the new information
- **New sub-topic**: Create a child note if the topic warrants its own page
- **Correction**: Fix any stale information in existing notes
- **New topic**: Create a new topic folder if the area isn't covered at all

After significant work, update `wiki/hot.md` to capture the session's findings and state.

This keeps notes as a living cache of codebase understanding. Every agent session that explores code should leave the notes better than it found them.

### When to Use This Protocol

- **Starting a new conversation**: Run Step 0, then read `wiki/hot.md` and `overview.md`
- **Before exploring code**: Check if notes already cover it
- **After any code exploration**: Update notes with new findings; update `wiki/hot.md`
- **When answering questions about the codebase**: Cite notes, not just code
- **When debugging**: Read the relevant system's note first to understand architecture
- **Working on a feature or bug**: Read notes on the relevant area for context, then update notes if you learned something new

---

## 10. Note Structure

### Directory Layout

Notes are stored at `~/vaults/<slug>/`:

```
~/vaults/<slug>/
├── .obsidian/               # Obsidian config (plugins, settings)
├── notes/
│   ├── overview.md
│   ├── RULES.md
│   ├── topic-name/
│   │   ├── index.md
│   │   ├── subtopic.md
│   │   ├── subtopic.excalidraw
│   │   └── deep-topic/
│   │       ├── index.md
│   │       ├── detail.md
│   │       └── ...
│   └── another-topic/
│       └── ...
├── research/
│   ├── index.md
│   ├── topic-name/
│   │   ├── index.md
│   │   └── paper-or-article.md
│   └── ...
├── commits/
│   └── author-slug/
│       └── path-slug.md
├── projects/
│   └── project-name/
│       ├── index.md
│       └── ...
├── code-reviews/
│   └── <slug>/
│       ├── context.md
│       ├── review.md
│       └── fix-plan.md
├── meta/
│   └── staleness-report.md
├── wiki/
│   └── hot.md
└── .repo_paths
```

**Naming:** Folders `topic-name/`, files `subtopic.md` — no `NN-` numeric prefixes. Use frontmatter `order:` if explicit ordering is needed. Each folder has `index.md`. Diagrams sit alongside notes with matching names. Multiple diagrams per note use suffixes: `thing-architecture.excalidraw`, `thing-dataflow.excalidraw`.

### Note Template

Every note follows this structure:

```markdown
---
git_tracked_paths:
  - path: relative/path/to/source/directory/
    commit: abc1234
last_updated: YYYY-MM-DD
tags: [optional-tag]
---
# Title

## What is it?

One paragraph summary.

## Architecture / Overview

![[note-name.excalidraw]]

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

Optional frontmatter fields:
- `order: N` — integer for explicit sort order within a folder (replaces NN- prefix)
- `tags: [tag1, tag2]` — Obsidian tags for filtering and grouping
- `aliases: [Alternate Name]` — alternate names for the note (enables wikilink lookup by alias)

### Navigation

Navigation is handled by Obsidian via backlinks, graph view, and the file explorer. **Do not add manual navigation bars** to notes. Use wikilinks for cross-references:

- `[[note-name]]` — link to a note by filename (no extension)
- `[[note-name|Display Text]]` — link with custom display text
- `[[folder/note-name]]` — link with path when disambiguation needed

Index files list their children with wikilinks:

```markdown
## Sub-topics

- [[subtopic-a|Subtopic A — description]]
- [[subtopic-b|Subtopic B — description]]
```

### Content Rules

- **Tables over prose** for structured data (config, endpoints, schemas)
- **Code snippets** only for schemas, key data structures, non-obvious patterns
- **No filler** — no "In this section we will..."
- **No ASCII art** for diagrams — always Excalidraw. ASCII is only acceptable for directory tree listings.
- **Text fallback** for every diagram — written description below that stands alone
- **Cross-referencing** — when a concept spans multiple code areas, define it once in the note matching the code location, cross-reference from others with wikilinks
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
2. Save the JSON file alongside the note with a matching name (e.g., `subtopic-architecture.excalidraw`)
3. Embed in the note with `![[filename.excalidraw]]` — Obsidian renders it natively via the Excalidraw plugin. No render script, no PNG files.
4. Add a text description below the embed that stands alone without the image.

**No render step required.** Obsidian's Excalidraw plugin renders `.excalidraw` files directly. Just create the JSON and embed it.

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

---

## 12. Parallelization Patterns

### Multiple Topics

When the user asks to explore several topics at once:

```
Launch N Explore agents simultaneously (one per topic)
Write notes as results arrive — don't wait for all to complete
Update overview.md Knowledge Map after all agents finish
```

### Batch Diagrams

When creating diagrams across multiple notes:

```
Launch N sub-agents (one per note group) to create .excalidraw JSON
After all complete, embed each with ![[filename.excalidraw]] in the relevant notes
```

No central render pass needed — Obsidian renders `.excalidraw` files on open.

### Diving into All Sub-Topics

When the user says "explore everything under topic X":

```
Read the topic's index.md to identify sub-topics
Launch N Explore agents (one per sub-topic)
Write sub-topic notes as results arrive
Update parent index.md with wikilinks to new notes
```

---

## 13. Knowledge Map

The Knowledge Map is a Dataview query in `overview.md` that automatically tracks all topics and their exploration status.

### Format

```markdown
## Knowledge Map

```dataview
TABLE last_updated, tags, file.size as "Size"
FROM "notes"
WHERE file.name != "overview"
SORT file.folder ASC, order ASC, file.name ASC
```
```

For contexts where Dataview is not available (e.g., non-Obsidian readers), maintain a fallback static table below the query block:

```markdown
<!-- Static fallback (update when adding new topics) -->
| Topic | Last Updated | Notes |
|-------|-------------|-------|
| [[auth/index\|Authentication]] | 2026-04-01 | Login, OAuth, sessions |
| [[api/index\|API Layer]] | 2026-03-28 | REST endpoints, middleware |
```

### Update Rules

- **New exploration**: Add a row to the static fallback; Dataview handles live data automatically
- **New topics discovered**: Create the topic folder with `index.md`; Dataview picks it up

---

## 14. v2 to v3 Migration (Obsidian Vault Migration)

### What Changed

| Aspect | v2 | v3 |
|--------|----|----|
| Storage location | `~/.claude/repo_notes/<repo_id>/notes/` | `~/vaults/<slug>/notes/` |
| Obsidian integration | None | Full — `.obsidian/` config, Excalidraw plugin, Dataview |
| Navigation links | Relative markdown links + `nav` script | Obsidian wikilinks, backlinks, graph view |
| Diagram rendering | `render` script → PNG | Obsidian Excalidraw plugin renders natively |
| Context priming | Hook-based `context-index` injection | `wiki/hot.md` read at session start |
| File naming | `NN-topic.md`, `NN-topic/` prefixes | `topic.md`, `topic/` — no numeric prefixes |
| Knowledge Map | Manual markdown table | Dataview query |

### Migration Command

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts migrate-to-vault
```

Options:
- `--all` — migrate all repos in `~/.claude/repo_notes/` at once
- `--dry-run` — preview without writing
- `--repo-id X` — migrate a specific repo ID

Examples:
```bash
# Preview migration for current repo
uv run python -m scripts migrate-to-vault --dry-run

# Migrate current repo
uv run python -m scripts migrate-to-vault

# Migrate all repos
uv run python -m scripts migrate-to-vault --all

# Migrate specific repo (by ID)
uv run python -m scripts migrate-to-vault --repo-id anthropics--claude-code --dry-run
```

The migration:
1. Resolves the vault slug for the repo
2. Creates `~/vaults/<slug>/` with `.obsidian/` config
3. Copies all `.md` and `.excalidraw` files preserving directory structure
4. Converts relative markdown links to wikilinks
5. Removes `NN-` numeric prefixes from filenames and references
6. Converts `![desc](./file.png)` embeds to `![[file.excalidraw]]` where source exists
7. Removes navigation bar lines (`> **Navigation:**`)
8. Reports any links that couldn't be auto-converted

The original `~/.claude/repo_notes/<repo_id>/` directory is NOT deleted.

### Manual Migration Steps

If the automated migration doesn't handle your case:

1. Run `resolve-vault` to create the vault
2. Run `scaffold` to create the vault structure
3. Manually copy notes to `~/vaults/<slug>/notes/`
4. Convert relative links to wikilinks
5. Remove `NN-` prefixes if desired
6. Create `wiki/hot.md` with current session context

---

## 15. Obsidian Conventions

### Wikilinks

Always use Obsidian wikilinks for cross-references between notes:

```markdown
[[note-name]]                  # link to note by filename (no extension)
[[note-name|Display Text]]     # link with alias
[[folder/note-name]]           # disambiguate when filename not unique
![[diagram.excalidraw]]        # embed Excalidraw diagram (renders natively)
![[image.png]]                 # embed image
```

Never use relative markdown links (`[text](../path/file.md)`) in vault notes. Obsidian resolves wikilinks by filename — no path prefix needed unless there's a collision.

### Frontmatter Properties

Obsidian reads YAML frontmatter as note properties. Use these standard fields:

```yaml
---
tags: [architecture, auth]          # searchable tags
aliases: [Authentication, Login]    # alternate names for wikilink lookup
order: 1                            # sort order within a folder
last_updated: YYYY-MM-DD
git_tracked_paths:
  - path: src/auth/
    commit: abc1234
---
```

### Dataview Queries

Use Dataview queries in `overview.md` and index files to generate dynamic tables:

```markdown
```dataview
TABLE last_updated, tags
FROM "notes/auth"
SORT order ASC
```
```

### Excalidraw Embedding

Obsidian's Excalidraw plugin renders `.excalidraw` files directly in reading view. Just embed them:

```markdown
![[diagram-architecture.excalidraw]]
```

The plugin renders the JSON into a visual diagram. No PNG export, no render script, no external tool needed. To create or edit a diagram, write the `.excalidraw` JSON file and Obsidian will display it.

### wiki/hot.md

The `wiki/hot.md` file is the session context file. It is read at session start (SessionStart hook) and updated at session end (Stop hook). Keep it concise — it should orient the next session quickly:

```markdown
---
last_updated: YYYY-MM-DD
---
# Hot Context

## Currently Active

- Working on: [[auth/oauth|OAuth flow]] — implementing PKCE
- Last explored: [[api/middleware|API middleware]]

## Recent Findings

- Auth module uses session tokens stored in Redis (see [[auth/sessions]])
- API layer has undocumented rate limiting in [[api/middleware]]

## Stale / Needs Attention

- [[models/user]] — user schema changed in last 3 commits
- [[config/env-vars]] — new vars added, note outdated

## Open Questions

- How does token refresh interact with concurrent requests?
```
