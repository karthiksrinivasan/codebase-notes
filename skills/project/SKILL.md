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
| `list` | (none) | List all projects and show which is active |
| `use` | `"project-name"` (required) | Set the active project (avoids needing `--project` every time) |
| `new` | `"project-name"` (required) | Create and scaffold a new project |
| `brainstorm` | `"query"` (required), `--file PATH`, `--url URL`, `--project NAME` | Explore a topic and update project notes |
| `ask` | `"question"` (required), `--project NAME` | Answer from project notes only |
| `update` | `"prompt"` (required), `--file PATH`, `--url URL`, `--project NAME` | Update notes based on prompt, optionally informed by a file or URL |
| `question` | `--project NAME` | List open questions across the project |

**Examples:**
- `/codebase-notes:project list` — show all projects, highlights active one
- `/codebase-notes:project use "auth-redesign"` — sets active project, no need for `--project` after this
- `/codebase-notes:project new "auth-redesign"`
- `/codebase-notes:project brainstorm "how should we handle OAuth flows?"` — uses active project
- `/codebase-notes:project brainstorm "review this RFC" --file docs/rfc-auth.md --project auth-redesign`
- `/codebase-notes:project brainstorm "what does this propose?" --url https://example.com/article`
- `/codebase-notes:project ask "what are the current goals?" --project auth-redesign`
- `/codebase-notes:project update "add a new constraint about latency budgets" --project auth-redesign`
- `/codebase-notes:project update "incorporate findings and add diagrams" --file docs/proposal.md --project auth-redesign`
- `/codebase-notes:project question --project auth-redesign`

---

You are managing project-level brainstorming and planning notes. Project notes live in a dedicated `projects/` directory alongside codebase notes, and each project has its own self-contained knowledge graph.

## Storage Structure

```
~/vaults/<slug>/projects/<project-name>/
├── index.md              # Project overview, goals, open questions, knowledge map
├── topic/
│   ├── index.md
│   ├── subtopic.md
│   └── *.excalidraw
├── another-topic/
│   └── ...
└── research/             # External material gathered during brainstorm
    ├── index.md
    └── source.md
```

No numeric prefixes on directories or files. Use frontmatter `order:` if explicit ordering is needed.

## Step 0: Bootstrap and Resolve (ALL subcommands)

**MANDATORY** — always run this before doing anything:

```bash
cd <plugin_root> && test -d .venv || uv sync
```

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts resolve-vault
```

Projects live at: `~/vaults/<slug>/projects/`

## Project Resolution

When a subcommand needs to know which project to operate on (all subcommands except `new` and `use`):

1. If `--project NAME` is provided, use that project name
2. If `projects/.active-project` exists, read the project name from it
3. If the `projects/` directory has exactly one project, use it automatically
4. If multiple projects exist and none of the above resolved, list all projects and ask the user which one

If the resolved project does not exist, tell the user and suggest `/codebase-notes:project new "NAME"` instead.

**Note:** The `new` subcommand automatically sets the newly created project as active.

---

## Subcommand: `list`

### Arguments

None.

### Flow

1. Run Step 0 to resolve the vault path and projects path
2. List all subdirectories in `projects/` (excluding `research/` and `.active-project`)
3. Read `projects/.active-project` if it exists to determine the active project
4. For each project, read its `index.md` frontmatter to get `status` and `last_updated`
5. Present as a table:

   ```
   ## Projects

   | # | Project          | Status       | Last Updated | Active |
   |---|------------------|--------------|--------------|--------|
   | 1 | auth-redesign    | brainstorming| 2026-03-15   | *      |
   | 2 | api-v2           | active       | 2026-03-10   |        |
   ```

6. If no projects exist, suggest `/codebase-notes:project new "name"` to get started

---

## Subcommand: `use`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"project-name"` | **Yes** | Name of the project to set as active |

### Flow

1. Run Step 0 to resolve the vault path and projects path
2. Verify `projects/<project-name>/` exists — if not, tell the user and suggest `new`
3. Write the project name to `projects/.active-project` (plain text, just the name)
4. Confirm to the user: "Active project set to **<project-name>**. All subsequent commands will use this project by default."

---

## Subcommand: `new`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"project-name"` | **Yes** | Name of the new project (used as directory name) |

### Flow

1. Run Step 0 to resolve the vault path and projects path
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
tags: [project]
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

6. Write the project name to `projects/.active-project` to set it as the active project
7. List the initial open questions and suggest next steps (brainstorming specific topics)

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

1. Run Step 0 to resolve the vault path and projects path
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
     └── source-name.md
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
   - **New topic area:** Create a new topic directory (`topic-name/`) with an `index.md`. Use descriptive names without numeric prefixes; set `order:` frontmatter if ordering matters.
   - **Existing topic area:** Edit the relevant existing notes to incorporate new findings
   - Topic notes use minimal frontmatter:
     ```yaml
     ---
     last_updated: YYYY-MM-DD
     ---
     ```
   - Use wikilinks for cross-references: `[[other-topic/index|Other Topic]]`

7. Run the diagram verifier to check for missing diagrams:
   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams
   ```
   If any issues are reported for this project's notes, go back and create the missing diagrams before continuing.
8. Add any new open questions discovered during brainstorming to the project's `index.md` under `## Open Questions`
9. Update the Knowledge Map table in `index.md` if new topics were created or existing topics changed status
10. Update `last_updated` in the project `index.md` frontmatter

**Note:** Navigation within a project is handled by Obsidian backlinks and wikilinks — no `nav` script needed.

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

After creating `.excalidraw` files, embed them in the notes with `![[filename.excalidraw]]` — Obsidian renders them natively. Always include a text description below each diagram.

---

## Subcommand: `ask`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"question"` | **Yes** | The question to answer |
| `--project NAME` | No | Project to query (see Project Resolution) |

### Flow

1. Run Step 0 to resolve the vault path and projects path
2. Resolve the project (see Project Resolution)
3. Read all project notes:
   - `projects/<project-name>/index.md`
   - All topic `index.md` files and subtopic notes
   - Research notes if relevant
4. Answer the question **from project notes only** (including research notes within the project) — no code exploration, no web search
5. Cite which notes the answer draws from (use wikilinks: `[[project/topic/note|Note Name]]`)
6. If notes are insufficient to answer the question, say so explicitly and suggest `/codebase-notes:project brainstorm` to explore and fill the gap

---

## Subcommand: `update`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"prompt"` | **Yes** | Description of the update to make |
| `--file PATH` | No | Path to a file to read as input — its content informs the update to project notes (the file itself is NOT modified) |
| `--url URL` | No | URL to fetch as input — its content informs the update to project notes |
| `--project NAME` | No | Project to update (see Project Resolution) |

### Flow

1. Run Step 0 to resolve the vault path and projects path
2. Resolve the project (see Project Resolution)
3. Read existing project notes to understand current state
4. If `--file PATH`, `--url URL`, or a file path appears inline in the prompt, read the source material first — this is **input context** that informs the update to project notes. **Never modify the source file/URL itself.**
5. Apply the update described in the prompt:
   - Edit existing notes to incorporate changes
   - Add new content (new topic directories, new subtopic notes)
   - Reorganize structure if the prompt calls for it
   - When creating new topic directories, use descriptive names without numeric prefixes
6. Update `last_updated` in the frontmatter of every note that was modified
7. Update the Knowledge Map table in `index.md` if structure changed (topics added, removed, or reorganized)
8. Update wikilinks in `index.md` if structure changed — managed by Claude directly

---

## Subcommand: `question`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--project NAME` | No | Project to scan (see Project Resolution) |

### Flow

1. Run Step 0 to resolve the vault path and projects path
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

   ### From topic-name
   - Question 3 (explicit)
   - "How should we handle X?" (implicit, from subtopic.md)

   ### From another-topic
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
tags: [project]
---
```

**Topic notes:**
```yaml
---
last_updated: YYYY-MM-DD
order: 1
---
```

**Research source notes:**
```yaml
---
source_url: https://...
date_added: YYYY-MM-DD
---
```

## Naming Convention

Project notes use descriptive directory and file names without numeric prefixes (e.g., `auth-flow/`, `data-model.md`). Use `order:` frontmatter for explicit sort order when needed.

Content from `--url` during brainstorm goes into the project's `research/` subdirectory.

## Script Compatibility

The `render` and `nav` scripts are not used for project notes. Project notes at `projects/` are **independent** — navigation is handled by Obsidian backlinks and wikilinks, and Excalidraw files render natively without a render script.
