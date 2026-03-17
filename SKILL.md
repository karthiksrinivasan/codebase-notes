---
name: codebase-notes
description: Generate, explore, and maintain a hierarchical knowledge base of structured notes for any codebase. Notes serve as the PRIMARY context source — read notes before exploring code, update notes after learning from code. Use this skill when the user wants to understand a codebase, create documentation notes, explore a repo progressively, build a knowledge graph of a project, or asks to "learn about this codebase", "create notes", "explore this repo", "document this project", or "help me understand this code". Also triggers for requests to update existing notes, add diagrams, dive deeper into specific areas, or when any agent needs codebase context and notes exist. If a docs/notes directory exists in the repo, always read 00-overview.md first to prime context before any code exploration.
---

# Codebase Notes

Build and maintain a hierarchical knowledge base that helps humans progressively understand a codebase. Notes are structured as an explorable knowledge graph — start broad, dive deep on demand, always navigable.

## When to Use

- User wants to understand or learn about a codebase
- User asks to create documentation or exploration notes
- User wants to dive deeper into specific parts of an existing notes directory
- User asks to update notes after code changes
- User wants diagrams added to existing notes

## Core Philosophy

**Notes are the primary context source.** When any agent (including you) needs to understand part of the codebase, the notes should be read FIRST — before exploring code. Notes are pre-digested context that saves tokens and time. Code exploration is the fallback for when notes don't cover what's needed. This makes notes a living investment: every time you learn something new from code, update the relevant note so the next agent doesn't have to re-explore.

**Notes are a knowledge graph, not a document dump.** Each note is a node with links to parent, siblings, and children. The user navigates by choosing what to explore next — you present options, they pick, you go deeper.

**Diagrams argue, text explains.** Every note gets at least one Excalidraw diagram showing architecture or data flow. Text supplements with tables, schemas, and key file references. Never use ASCII art for diagrams — always Excalidraw.

**Text must stand alone.** Diagrams enhance but don't replace text. Every architecture section needs enough written description that a reader with broken images still understands the system. A diagram without a text summary below it is incomplete.

**Capture what code can't tell you.** Focus on architecture, data flow, integration points, and design decisions. Don't repeat what `git log` or reading the source would tell you directly.

---

## Context Priming Protocol

Whenever you need to understand part of the codebase — whether for exploration, answering questions, debugging, or feature work — follow this order:

### 1. Read notes first (cheap, pre-digested context)

```
Read {notes_dir}/00-overview.md → understand the full system map
Read {notes_dir}/{relevant-topic}/index.md → understand the subsystem
Read {notes_dir}/{relevant-topic}/{specific-note}.md → get the details
```

Notes contain architecture, data flow, schemas, config, key files, and diagrams. This is 10-100x cheaper than re-exploring source code and gives you the "why" that code alone can't.

### 2. Fall back to code exploration (when notes are insufficient)

If notes don't cover what you need — a specific function signature, a recently added feature, an edge case — then explore the code. Use the Key Files tables in notes as starting points rather than grepping blindly.

### 3. Update notes with what you learned (pay it forward)

After learning something new from code exploration, update the relevant note:

- **Minor addition**: Edit the existing note to add the new information
- **New sub-topic**: Create a child note if the topic warrants its own page
- **Correction**: Fix any stale information in existing notes
- **New topic**: Create a new topic folder if the area isn't covered at all

This keeps notes as a living cache of codebase understanding. Every agent session that explores code should leave the notes better than it found them.

### When to use this protocol

- **Starting a new conversation**: Read `00-overview.md` to prime your context
- **Before exploring code**: Check if notes already cover it
- **After any code exploration**: Update notes with new findings
- **When answering questions about the codebase**: Cite notes, not just code
- **When debugging**: Read the relevant system's note first to understand architecture before diving into stack traces

---

## Step 0: Check for Existing Notes

Before doing anything, check if notes already exist:

```
find {repo_root}/docs/notes -name "*.md" 2>/dev/null
```

Also check common alternative locations: `notes/`, `docs/knowledge/`, or ask the user.

**If notes exist:** Read `00-overview.md` to understand current state. Present the Knowledge Map showing explored vs unexplored topics. Ask the user what they want to do (explore more, update existing, add detail).

**If notes don't exist:** Proceed to Phase 1.

---

## Phase 1: Initialize

When starting fresh (no notes directory exists), create the foundation.

### 1.1 Explore the Repository

Before writing anything, understand the repo:

- Read README.md, CLAUDE.md, any onboarding docs
- Check `ls` at root for top-level structure
- Identify languages (pyproject.toml, Cargo.toml, go.mod, package.json)
- Identify build tools (justfile, Makefile, mise.toml, docker-compose)
- Identify the major systems/packages

### 1.2 Create the Notes Directory

Default location: `docs/notes/`. Let the user choose if they prefer somewhere else.

Check if the path is gitignored — notes are typically personal/ephemeral and shouldn't be committed. If not gitignored, mention this to the user.

```
{notes_dir}/
├── 00-overview.md      # Root node — links to everything
└── RULES.md            # Copy from references/RULES-template.md, adapt examples
```

When copying RULES-template.md, replace any repo-specific examples with ones relevant to the current codebase.

### 1.3 Write the Overview

The overview (`00-overview.md`) must contain:

1. **Navigation bar** at top linking to all topic folders created so far
2. **"What is this?"** — one paragraph describing the repo
3. **Architecture section** — Excalidraw diagram + text description of how major systems connect. The text description is mandatory even if the diagram renders perfectly — it serves as fallback and adds detail the diagram can't.
4. **Languages & Build Tools** — what's used and how
5. **Top-Level Packages** — table of directories, what they do, primary language
6. **Knowledge Map** — table of all topics with exploration status and links

### 1.4 Present Topics

After writing the overview, present the Knowledge Map to the user as numbered options. Let them choose what to explore. This is the interactive loop.

**Topic numbers in the Knowledge Map (1, 2, 3...) don't need to match folder numbers (01-, 02-, 03-).** Folders are numbered in the order they're created. The Knowledge Map orders topics by logical grouping.

---

## Phase 2: Explore (The Core Loop)

The user picks a topic, you explore it, write notes, and present new options.

### 2.1 Dispatch Explore Agent

For each topic, dispatch a sub-agent with a detailed prompt. The quality of notes depends heavily on the explore prompt being specific. Use this template:

```
Very thoroughly explore {path}. I need a deep understanding of:

1. **What is it?** Read any README, pyproject.toml, and top-level files.
2. **Architecture**: Main modules/packages, how it's structured.
3. **Core logic**: Key classes, functions, data structures. What does each do?
4. **Data flow**: How does data enter, transform, and exit?
5. **Integration points**: How does it connect to other parts of the monorepo?
6. **Configuration**: Env vars, config files, defaults.
7. **API surface**: Endpoints, gRPC services, MCP tools, CLI commands.
8. **Schemas**: Database models, protobuf definitions, Pydantic models.
9. **Testing**: How is it tested? Key fixtures?
10. **Deployment**: How is it deployed?

Read ALL key source files. Give me specifics — function signatures, class names,
config fields, actual processing logic — not just labels.
```

Use `subagent_type: "Explore"` for the Agent tool.

### 2.2 Write Notes from Results

Follow the note structure (see Note Structure section). Key rules:
- Lead with "What is it?" paragraph
- Prefer tables for structured data
- Include a Key Files table at the bottom
- Create Excalidraw diagram(s)
- Add text description for every diagram

### 2.3 Update Parents

After writing a note:
- Add link in parent `index.md` sub-topics list
- Update sibling Prev/Next navigation links
- Update `00-overview.md` Knowledge Map and navigation bar

### 2.4 Present Options

Always present navigation options after writing notes:

```
Where to next?
- Dive into sub-topic X, Y, or Z
- Go back to overview
- Explore a different top-level topic (1-10)
- Go deeper on [specific thing mentioned in the notes]
```

The user's choices determine what gets explored. Never explore everything unprompted.

### 2.5 Parallel Exploration

When the user asks to explore multiple topics at once, dispatch multiple Explore agents simultaneously. Write notes as results arrive — don't wait for all to complete.

For diagram creation in batch: dispatch sub-agents to create `.excalidraw` JSON, then render all centrally (sub-agents typically can't run bash for rendering).

---

## Git Freshness Tracking

Every note tracks which git commit it was last updated against. This lets you detect stale notes and know exactly what changed since the note was written.

### How It Works

Each note includes a YAML frontmatter block with the git commit hash of the source directories it covers:

```markdown
---
git_tracked_paths:
  - path: agent/src/agent/agents/ac/
    commit: a1b2c3d4e5f6
  - path: agent/src/agent/core/
    commit: a1b2c3d4e5f6
last_updated: 2026-03-16
---
# Title
...
```

### When Writing a Note

After writing or updating a note, add/update the frontmatter with the current HEAD commit for each tracked path:

```bash
# Get current short commit hash
git rev-parse --short HEAD
# Or for a specific path's last commit:
git log -1 --format=%h -- agent/src/agent/agents/ac/
```

### When Reading a Note (Staleness Check)

Before trusting a note's content, check if the tracked paths have changed:

```bash
# Check if any tracked path has changes since the note's commit
git diff --name-only <note_commit> HEAD -- <tracked_path>
```

If files changed, the note may be stale. The three responses:

1. **No changes** → note is fresh, trust it fully
2. **Minor changes** (a few files, no new modules) → note is likely still accurate, use it but verify specifics in code
3. **Major changes** (new files, restructured, many modifications) → note needs updating before it can be trusted

### Staleness Report

When checking existing notes (Step 0), generate a staleness report:

```bash
# For each note with frontmatter, check freshness
for note in $(find {notes_dir} -name "*.md"); do
  # Extract tracked paths and commits from frontmatter
  # Compare against current HEAD
  # Report: FRESH / POSSIBLY_STALE / STALE
done
```

Present stale notes to the user so they can decide what to update.

### Automation Helper

Add this to Step 0 when notes exist — after reading `00-overview.md`, run a quick freshness scan:

```bash
# Quick staleness check for all notes
find {notes_dir} -name "*.md" -exec grep -l "git_tracked_paths" {} \; | while read note; do
  paths=$(grep "path:" "$note" | awk '{print $3}')
  commit=$(grep "commit:" "$note" | head -1 | awk '{print $2}')
  if [ -n "$commit" ]; then
    changes=$(git diff --name-only "$commit" HEAD -- $paths 2>/dev/null | wc -l)
    if [ "$changes" -gt 0 ]; then
      echo "STALE ($changes files changed): $(basename $note)"
    fi
  fi
done
```

---

## Phase 3: Update & Maintain

### 3.1 Detect What Changed

Use the git freshness tracking to identify stale notes:

```bash
# For each note, check its tracked paths against current HEAD
# See "Git Freshness Tracking" section above
```

Focus on: new files/modules, changed APIs, renamed functions, new integrations.

### 3.2 Update In-Place

- Prefer updating existing notes over creating new ones
- Update the `git_tracked_paths` commit hashes in frontmatter after updating
- Update diagrams if architecture changed
- Update Knowledge Map status in `00-overview.md`
- Fix broken navigation links

### 3.3 Add Detail

When the user asks to go deeper:
- Read the existing note to understand current coverage
- Explore code for the specific area they want
- Either expand the existing note or create a child note in a subfolder
- Always update parent links and git tracking frontmatter

---

## Note Structure

### Directory Layout

```
{notes_dir}/
├── 00-overview.md
├── RULES.md
├── 01-{topic}/
│   ├── index.md
│   ├── 01-{subtopic}.md
│   ├── 01-{subtopic}.excalidraw
│   ├── 01-{subtopic}.png
│   ├── 02-{subtopic}.md
│   └── 03-{subtopic}/
│       ├── index.md
│       ├── 01-{detail}.md
│       └── ...
├── 02-{topic}/
│   └── ...
```

**Naming:** Folders `NN-topic-name/`, files `NN-subtopic.md`. Each folder has `index.md`. Diagrams sit alongside notes with matching names. Multiple diagrams per note use suffixes: `01-thing-architecture.excalidraw`, `01-thing-dataflow.excalidraw`.

### Navigation Bar

Every note starts with:

```markdown
> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)
```

Index files additionally have a Sub-topics line:

```markdown
> **Sub-topics:** [Child A](./01-child-a.md) | [Child B](./02-child-b.md)
```

All links are **relative paths**.

### Note Template

```markdown
---
git_tracked_paths:
  - path: relative/path/to/source/directory/
    commit: abc1234
last_updated: YYYY-MM-DD
---
# Title

> **Navigation:** Up: [...] | Prev: [...] | Next: [...]

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

The `git_tracked_paths` frontmatter links the note to the source code directories it documents. Multiple paths can be tracked per note. The `commit` is the short hash from `git log -1 --format=%h -- <path>` at the time the note was written or last updated.

### Content Rules

- **Tables over prose** for structured data (config, endpoints, schemas)
- **Code snippets** only for schemas, key data structures, non-obvious patterns
- **No filler** — no "In this section we will..."
- **No ASCII art** for diagrams — always Excalidraw. ASCII is only acceptable for directory tree listings.
- **Text fallback** for every diagram — written description below that stands alone
- **Cross-referencing** — when a concept spans multiple code areas, define it once in the note matching the code location, cross-reference from others with relative links
- **Mirror codebase structure** — note hierarchy should reflect the source code organization. If code is in `agent/api/routers/mcp/`, the note goes under `02-agent/03-framework/`

---

## Diagrams

Every note needs at least one Excalidraw diagram. Notes covering multiple concepts should have multiple.

### Creating Diagrams

Use the `excalidraw-diagram` skill if available. If not, create JSON directly:

1. Create `.excalidraw` JSON section-by-section (not all at once — large diagrams hit token limits)
2. Render: `cd ~/.claude/skills/excalidraw-diagram/references && uv run python render_excalidraw.py <path>`
3. View the PNG with Read tool
4. Fix issues and re-render until clean
5. Embed with `![description](./filename.png)`

**The renderer outputs `filename.png` (NOT `filename.excalidraw.png`). Always reference `.png` only.**

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
- Shapes need `boundElements` → text; text needs `containerId`
- Arrows need `startBinding`/`endBinding` with `{elementId, focus: 0, gap: 2}`
- Use semantic colors from excalidraw-diagram skill palette if available

### Batch Rendering

Sub-agents creating diagrams may lack bash permissions. After they complete:

```bash
cd ~/.claude/skills/excalidraw-diagram/references
find {notes_dir} -name "*.excalidraw" | while read f; do
  png="${f%.excalidraw}.png"
  if [ ! -f "$png" ] || [ "$f" -nt "$png" ]; then
    uv run python render_excalidraw.py "$f"
  fi
done
```

### Image Path Conflicts

Some markdown viewers (like md-serve with Next.js routing) can't serve images whose filename matches a page route. If a root-level image doesn't render, rename it (e.g., `00-overview.png` → `00-overview-architecture.png`).

---

## Parallelization Patterns

### Multiple Topics

```
Launch N Explore agents simultaneously (one per topic)
Write notes as results arrive
Update parent links after each
```

### Batch Diagrams

```
Launch N sub-agents (one per note group) to create .excalidraw JSON
After all complete: render centrally, embed PNGs
```

### Diving into All Sub-Topics

```
Launch N Explore agents (one per sub-topic)
Write sub-topic notes as results arrive
Update parent index.md with links
```

---

## Knowledge Map

The table in `00-overview.md` tracking all topics:

```markdown
| # | Topic | Notes |
|---|-------|-------|
| 1 | Topic Name — brief description | [01-topic/](./01-topic/index.md) |
| 2 | Another Topic | _not yet explored_ |
```

**Update rules:**
- New exploration: change `_not yet explored_` to folder link
- Sub-topics explored: optionally add indented `↳` rows
- New topics: add to Navigation bar at top of overview

---

## Quick Reference

| User Says | Action |
|-----------|--------|
| "Help me understand this repo" | Check for existing notes → Phase 1 or resume |
| "Explore topic X" | Read existing notes on X first → Dispatch Explore agent for gaps → write/update notes |
| "Dive into X, Y, Z in parallel" | Dispatch multiple agents simultaneously |
| "Go back to overview" | Present Knowledge Map with current status |
| "Update the notes" | Phase 3: detect changes, update in-place |
| "Add diagrams" | Create Excalidraw diagrams for notes lacking them |
| "Go deeper on X" | Read existing note → explore code for gaps → create child note or expand |
| "Add more detail" | Re-explore with deeper focus, expand note |
| _(any task needing codebase context)_ | Read `00-overview.md` + relevant topic notes first, then code |
| "Fix bug in X" / "Add feature to Y" | Read notes on X/Y for architecture context → work on code → update notes if you learned something new |
| "How does X work?" | Read notes on X → answer from notes → if insufficient, explore code and update notes |
