---
name: project
description: Brainstorm, plan, and track new projects within a codebase. Create project notes, explore ideas with files and URLs, ask questions against project knowledge, and track open questions.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch", "WebSearch"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/project/SKILL.md` → plugin root is `../../`.

# Project Notes

Manage project-level brainstorming and planning notes within a codebase. Project notes are repo-scoped and follow the same knowledge graph pattern as codebase notes.

## Subcommands

| Subcommand | Arguments | Description |
|------------|-----------|-------------|
| `new` | `"project-name"` (required) | Create and scaffold a new project |
| `brainstorm` | `"query"` (required), `--file PATH`, `--url URL`, `--project NAME` | Explore a topic and update project notes |
| `ask` | `"question"` (required), `--project NAME` | Answer from project notes only |
| `update` | `"prompt"` (required), `--project NAME` | Update notes based on prompt |
| `question` | `--project NAME` | List open questions across the project |

**Examples:**
- `/codebase-notes:project new "auth-redesign"`
- `/codebase-notes:project brainstorm "how should we handle OAuth flows?" --project auth-redesign`
- `/codebase-notes:project brainstorm "review this RFC" --file docs/rfc-auth.md --project auth-redesign`
- `/codebase-notes:project brainstorm "what does this propose?" --url https://example.com/article`
- `/codebase-notes:project ask "what are the current goals?" --project auth-redesign`
- `/codebase-notes:project update "add a new constraint about latency budgets" --project auth-redesign`
- `/codebase-notes:project question --project auth-redesign`

---

You are managing project-level brainstorming and planning notes. Project notes live in a dedicated `projects/` directory alongside codebase notes, and each project has its own self-contained knowledge graph.

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

## Step 0: Bootstrap and Resolve (ALL subcommands)

**MANDATORY** — always run this before doing anything:

```bash
cd <plugin_root> && test -d .venv || uv sync
```

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

Projects live at: `~/.claude/repo_notes/<repo_id>/projects/`

## Project Resolution

When a subcommand needs to know which project to operate on (all subcommands except `new`):

1. If `--project NAME` is provided, use that project name
2. If the `projects/` directory has exactly one project, use it automatically
3. If multiple projects exist and no `--project` was given, list all projects and ask the user which one

If the resolved `--project NAME` does not exist, tell the user and suggest `/codebase-notes:project new "NAME"` instead.

---

## Subcommand: `new`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"project-name"` | **Yes** | Name of the new project (used as directory name) |

### Flow

1. Run Step 0 to resolve the repo ID and projects path
2. Check if `projects/<project-name>/` already exists
   - If it exists, tell the user the project already exists and suggest `/codebase-notes:project brainstorm` or `/codebase-notes:project update` instead. **Do not overwrite.**
3. Ask the user guided questions to scaffold the project:
   - **What is this project?** — ask for a one-paragraph description
   - **Goals** — ask for the project's goals (bulleted list)
   - **Constraints** — ask if there are any constraints (optional)
   - **Initial scope** — what topics or areas should be explored first?
4. Create the `projects/` directory if it doesn't exist, then create `projects/<project-name>/`
5. Write `projects/<project-name>/index.md` with the following structure:

```markdown
---
project: <project-name>
created: <today's date YYYY-MM-DD>
last_updated: <today's date YYYY-MM-DD>
status: brainstorming
---
# <Project Name>

## What is this project?

<one paragraph from user's answer>

## Goals

- <goal 1>
- <goal 2>
- ...

## Constraints

- <constraint 1 if any>

## Knowledge Map

| # | Topic | Status | Description |
|---|-------|--------|-------------|

## Open Questions

- <initial questions based on the project description and scope>
```

6. List the initial open questions and suggest next steps (brainstorming specific topics)

**Note:** `new` intentionally has no `--file` or `--url` flags — it is a guided setup only.

---

## Subcommand: `brainstorm`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"query"` | **Yes** | The topic or question to explore |
| `--file PATH` | No | Path to a file to read and discuss |
| `--url URL` | No | URL to fetch and discuss |
| `--project NAME` | No | Project to brainstorm within (see Project Resolution) |

### Flow

1. Run Step 0 to resolve the repo ID and projects path
2. Resolve the project (see Project Resolution)
3. Read `projects/<project-name>/index.md` for full project context
4. Read existing topic notes to understand what's already been explored
5. Process the input source:

   **If `--file PATH` is provided:**
   - Read the file
   - Present the key points and themes from the file
   - Discuss relevance to the project with the user

   **If `--url URL` is provided:**
   - Use WebFetch to retrieve the URL content
   - Present key points and themes
   - Discuss relevance to the project with the user
   - Save the source material into the project's `research/` subdirectory following the research note pattern:
     ```
     projects/<project-name>/research/
     ├── index.md
     └── 01-source-name.md
     ```
   - Research source notes use this frontmatter:
     ```yaml
     ---
     source_url: https://...
     date_added: YYYY-MM-DD
     ---
     ```

   **If plain query (no --file or --url):**
   - Explore the topic conversationally with the user
   - Draw on existing project notes for context

6. After discussion, update project notes:
   - **New topic area:** Create a new numbered topic directory (`NN-topic-name/`) with an `index.md`. Scan existing directories to pick the next sequential number.
   - **Existing topic area:** Edit the relevant existing notes to incorporate new findings
   - Topic notes use minimal frontmatter:
     ```yaml
     ---
     last_updated: YYYY-MM-DD
     ---
     ```

7. Run the diagram verifier to check for missing diagrams:
   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams
   ```
   If any issues are reported for this project's notes, go back and create the missing diagrams before continuing.
8. Add any new open questions discovered during brainstorming to the project's `index.md` under `## Open Questions`
9. Update the Knowledge Map table in `index.md` if new topics were created or existing topics changed status
10. Update `last_updated` in the project `index.md` frontmatter

**Note:** Navigation links within a project are managed by Claude directly (same link format as codebase notes), not the `nav` script.

### Diagram Requirements

Every brainstorm session that creates or updates topic notes MUST produce at least one Excalidraw diagram. Project brainstorming is inherently visual — architecture ideas, flow concepts, and design alternatives are best captured as diagrams.

| Brainstorm Content | Diagram Type |
|-------------------|-------------|
| Architecture or system design | Layered architecture or component diagram |
| User flow or workflow | Sequence diagram or state machine |
| Decision with trade-offs | Comparison layout showing alternatives side-by-side |
| Data model or schema | Entity relationship or hierarchy diagram |
| Integration or API design | Data flow diagram showing connections and protocols |
| Project roadmap or phases | Timeline diagram with milestones |

After creating `.excalidraw` files, render them:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render --repo-id <repo_id>
```

View each rendered PNG with the Read tool to verify quality. Embed with `![description](./filename.png)` and always include a text description below.

---

## Subcommand: `ask`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"question"` | **Yes** | The question to answer |
| `--project NAME` | No | Project to query (see Project Resolution) |

### Flow

1. Run Step 0 to resolve the repo ID and projects path
2. Resolve the project (see Project Resolution)
3. Read all project notes:
   - `projects/<project-name>/index.md`
   - All topic `index.md` files and subtopic notes
   - Research notes if relevant
4. Answer the question **from project notes only** (including research notes within the project) — no code exploration, no web search
5. Cite which notes the answer draws from
6. If notes are insufficient to answer the question, say so explicitly and suggest `/codebase-notes:project brainstorm` to explore and fill the gap

---

## Subcommand: `update`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"prompt"` | **Yes** | Description of the update to make |
| `--project NAME` | No | Project to update (see Project Resolution) |

### Flow

1. Run Step 0 to resolve the repo ID and projects path
2. Resolve the project (see Project Resolution)
3. Read existing project notes to understand current state
4. Apply the update described in the prompt:
   - Edit existing notes to incorporate changes
   - Add new content (new topic directories, new subtopic notes)
   - Reorganize structure if the prompt calls for it
   - When creating new topic directories, scan existing directories and pick the next sequential number
5. Update `last_updated` in the frontmatter of every note that was modified
6. Update the Knowledge Map table in `index.md` if structure changed (topics added, removed, or reorganized)
7. Update navigation links in `index.md` if structure changed — managed by Claude directly, not the `nav` script

---

## Subcommand: `question`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--project NAME` | No | Project to scan (see Project Resolution) |

### Flow

1. Run Step 0 to resolve the repo ID and projects path
2. Resolve the project (see Project Resolution)
3. Read all project notes (index.md + all topic notes + research notes)
4. Collect **explicit** open questions:
   - Items listed under `## Open Questions` sections in `index.md` and all topic notes
5. Scan for **implicit** unresolved items across all project notes:
   - Lines containing `TBD`, `TODO`, `need to decide`, `open question` (case-insensitive)
   - Questions in context — sentences ending with `?` that aren't rhetorical
   - Items marked with `[ ]` that are decision-oriented (not routine task checkboxes)
6. Present a consolidated list grouped by topic/source:

   ```
   ## Open Questions

   ### From index.md
   - Question 1
   - Question 2

   ### From 01-topic-name
   - Question 3 (explicit)
   - "How should we handle X?" (implicit, from 01-subtopic.md)

   ### From 02-topic-name
   - TBD: decide on Y (implicit, from index.md)
   ```

7. If no open questions are found (explicit or implicit), tell the user the project has no unresolved items
8. Offer to brainstorm any of the listed questions with `/codebase-notes:project brainstorm`

**Note:** Implicit question detection is best-effort. False positives are acceptable — the user can dismiss irrelevant items.

---

## Note Frontmatter Reference

**Project index.md:**
```yaml
---
project: my-project
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
status: brainstorming | active | paused | completed
---
```

**Topic notes:**
```yaml
---
last_updated: YYYY-MM-DD
---
```

**Research source notes:**
```yaml
---
source_url: https://...
date_added: YYYY-MM-DD
---
```

## Naming and Numbering Convention

Project notes follow the same `NN-topic-name/` numbering as codebase notes. When creating a new topic directory, scan existing directories in the project and pick the next sequential number (e.g., if `01-auth/` and `02-api/` exist, the next is `03-`).

Content from `--url` during brainstorm goes into the project's `research/` subdirectory.

## Script Compatibility

The `nav` and `render` scripts operate on the `notes/` directory. Project notes at `projects/` are **independent** — navigation links within a project are managed by Claude directly (same link format, but no `nav` script automation). The `render` script can be pointed at a project directory with `--repo-id` if diagrams need rendering.
