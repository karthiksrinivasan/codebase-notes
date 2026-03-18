# Project Skill Design

## What is it?

A new skill for the codebase-notes plugin that manages project-level brainstorming and planning notes. Project notes are repo-scoped, stored at `~/.claude/repo_notes/<repo_id>/projects/<project-name>/`, and follow the same knowledge graph pattern as codebase notes.

## Goals

- Provide a structured place to brainstorm, plan, and track new projects within a codebase
- Support multiple input modes: freeform conversation, file/URL ingestion, guided setup
- Track open questions explicitly and implicitly across all project notes
- Reuse existing codebase-notes patterns (knowledge graph, navigation, diagrams)

## Storage Structure

```
~/.claude/repo_notes/<repo_id>/projects/<project-name>/
├── index.md              # Project overview, goals, open questions, knowledge map
├── 01-topic/
│   ├── index.md
│   ├── 01-subtopic.md
│   └── *.excalidraw / *.png
├── 02-topic/
│   └── ...
└── research/             # External material gathered during brainstorm
    ├── index.md
    └── 01-source.md
```

### index.md Frontmatter

```yaml
---
project: my-project
created: 2026-03-18
last_updated: 2026-03-18
status: brainstorming | active | paused | completed
---
```

### index.md Required Sections

1. **What is this project?** — one paragraph
2. **Goals** — bulleted list
3. **Constraints** — if any
4. **Knowledge Map** — table of topics with status (same pattern as codebase notes)
5. **Open Questions** — explicitly tracked questions with optional context

## SKILL.md Frontmatter

```yaml
---
name: project
description: Brainstorm, plan, and track new projects within a codebase. Create project notes, explore ideas with files and URLs, ask questions against project knowledge, and track open questions.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch", "WebSearch"]
---
```

The SKILL.md must include the standard shared context preamble referencing `references/shared-context.md` and explaining `<plugin_root>` resolution.

## Step 0: Bootstrap and Resolve (all subcommands)

Every subcommand starts with:

1. Bootstrap scripts: `cd <plugin_root> && test -d .venv || uv sync`
2. Resolve repo ID: `REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts repo-id`
3. Derive projects path: `~/.claude/repo_notes/<repo_id>/projects/`

## Shared Arguments

All subcommands except `new` accept `--project NAME` to specify which project to operate on. See "Project Resolution" section below.

## Note Frontmatter

Project notes use a **different frontmatter** from codebase notes. No `git_tracked_paths` (projects aren't tracking code changes). Instead:

```yaml
---
project: my-project
created: 2026-03-18
last_updated: 2026-03-18
status: brainstorming | active | paused | completed
---
```

Topic notes within a project use minimal frontmatter:

```yaml
---
last_updated: 2026-03-18
---
```

## Script Compatibility

The `nav` and `render` scripts currently operate on the `notes/` directory. Project notes at `projects/` are **independent** — navigation links within a project are managed by Claude directly (same link format, but no `nav` script automation). The `render` script can be pointed at a project directory with `--repo-id` if diagrams need rendering.

## Subcommands

The skill handles 5 subcommands via its first positional argument.

### `new "project-name"`

**Purpose:** Create a new project and scaffold initial notes.

**Flow:**
1. Resolve repo ID and notes path
2. Create `projects/<project-name>/` directory
3. Ask guided questions: What is this project? Goals? Constraints? Initial scope?
4. Write `index.md` from answers
5. List initial open questions to explore

**Input:** Project name (required)

**Edge case:** If a project with that name already exists, tell the user and suggest `/codebase-notes:project brainstorm` or `/codebase-notes:project update` instead. Do not overwrite.

### `brainstorm "query or topic" [--file path] [--url URL] [--project NAME]`

**Purpose:** Explore a topic and update project notes with findings.

**Flow:**
1. Resolve project path (if only one project exists, use it; otherwise ask which)
2. Read existing project notes for context
3. Process input:
   - `--file path`: Read the file, present key points, discuss with user
   - `--url URL`: WebFetch the URL, present key points, discuss with user
   - Plain query: Explore the topic conversationally with the user
4. After discussion, update relevant project notes:
   - Create new topic notes if the area isn't covered
   - Edit existing notes if adding to a known topic
5. Add any new open questions discovered during brainstorming
6. Rebuild navigation

**Input:** Query/topic (required), optional `--file` and `--url` flags (can combine)

### `ask "question" [--project NAME]`

**Purpose:** Answer a question purely from project notes.

**Flow:**
1. Resolve project path
2. Read all project notes (index.md + all topic notes)
3. Answer from notes only — no code exploration, no web search
4. If notes are insufficient, say so and suggest `/codebase-notes:project brainstorm` to fill the gap

**Input:** Question (required)

### `update "prompt" [--project NAME]`

**Purpose:** Update project notes based on a prompt.

**Flow:**
1. Resolve project path
2. Read existing notes
3. Apply the update described in the prompt (edit existing notes, add new content, reorganize)
4. Update `last_updated` in frontmatter
5. Rebuild navigation

**Input:** Prompt describing what to change (required)

### `question [--project NAME]`

**Purpose:** List all open questions across the project.

**Flow:**
1. Resolve project path
2. Read explicit `## Open Questions` sections from index.md and all topic notes
3. Scan all project notes for implicit unresolved items:
   - Lines containing TBD, TODO, "need to decide", "open question"
   - Questions in context (sentences ending with `?` that aren't rhetorical)
   - Items marked with `[ ]` that are decision-oriented (not task checkboxes)
4. Present consolidated list grouped by topic/source
5. Offer to brainstorm any of them

**Note:** Implicit question detection is best-effort. False positives are acceptable — the user can dismiss irrelevant items.

**Input:** None required

## Project Resolution

When a subcommand needs to know which project to operate on:

1. If a `--project NAME` flag is provided, use that
2. If the `projects/` directory has exactly one project, use it
3. If multiple projects exist, list them and ask the user

## Implementation Notes

- **No new Python scripts** — this is purely Claude-driven (Read/Write/Edit for notes, WebFetch for URLs)
- **One skill file** at `skills/project/SKILL.md` handling all 5 subcommands
- References `shared-context.md` for note structure patterns, diagram guidelines, navigation conventions
- Uses the same `REPO_CWD` + `<plugin_root>` pattern for script invocations (repo-id, nav, render)
- The `research/` subdirectory within a project follows the same pattern as the research skill's notes

## What's NOT in scope

- No project-level staleness tracking (projects are manually maintained, not git-tracked)
- No cron auto-updates for projects
- No cross-project linking (each project is independent)
- No Python scripts for project management
