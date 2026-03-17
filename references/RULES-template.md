# Notes Generation Rules

Rules for how exploration notes in this directory should be created and maintained.

## Structure

- **Hierarchical folders** — each topic gets a folder with `index.md` + children. Nest deeper as subtopics are explored.
- **`00-overview.md`** is the root. It links to all top-level topic folders and tracks exploration status.
- **`index.md`** in each folder serves as the topic overview and links to all children.
- **Numbering**: folders use `NN-topic-name/`, files use `NN-subtopic.md` (01, 02, 03...).

## Navigation

Every note must have a navigation bar at the top:

```markdown
> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)
```

- **Up** — always points to parent `index.md` (or `../00-overview.md` for top-level folders)
- **Prev/Next** — link to sibling notes for linear reading within a folder
- **Sub-topics** (on index.md only) — links to children when they exist
- All links are **relative paths**, never absolute

## Content

- **Lead with "What is it?"** — one-paragraph summary at the top of every note
- **Prefer tables and diagrams** over prose for structured data (config fields, API endpoints, database schemas, etc.)
- **Include key file paths** — a "Key Files" table at the bottom mapping files to their purpose
- **Code snippets** — use sparingly, only for schemas, key data structures, or non-obvious patterns
- **No filler** — no "In this section we will..." intros. Get to the point.
- **Text fallback for diagrams** — every diagram must have a written description below it that conveys the same information. Readers with broken images should still understand the architecture.
- **Architecture diagrams** — every note MUST include Excalidraw diagrams (see Diagrams section). **NEVER use ASCII art** for architecture, data flow, or state machine diagrams. ASCII art is ONLY acceptable for directory tree listings.

## What to capture

- Architecture and data flow (how pieces connect)
- Schemas and data models (database, protobuf, type definitions)
- API surfaces (endpoints, gRPC services, MCP tools)
- Configuration (env vars, config structs, defaults)
- Key design decisions and non-obvious patterns
- Integration points between systems

## What NOT to capture

- Line-by-line code walkthroughs (the code is the source of truth)
- Obvious implementation details derivable from reading the code
- Temporary debugging notes or TODOs
- Duplicated content across notes — link to the canonical note instead

## Diagrams (Excalidraw)

Every note MUST include at least one Excalidraw diagram.

### Requirements

- **Multiple diagrams per note** — use more than one when covering distinct concepts (e.g., architecture overview + data flow + state machine).
- **File format**: `.excalidraw` JSON files stored alongside the note. For multiple: `01-name-architecture.excalidraw`, `01-name-dataflow.excalidraw`
- **Embedded in markdown**: `![Diagram description](./filename.png)` — the renderer outputs `.png` (NOT `.excalidraw.png`)
- **PNG rendering**: `cd ~/.claude/skills/excalidraw-diagram/references && uv run python render_excalidraw.py <path>`
- **Render-view-fix loop**: Render, view PNG, fix issues, re-render. Mandatory.
- **Subagent rendering**: Sub-agents may lack bash permissions. Parent session renders centrally after they create JSON.

### Style

- `roughness: 0` (clean/modern), `fontFamily: 3`, `opacity: 100`
- Diagrams should ARGUE visually — show relationships and flow, not just labeled boxes
- Use shape variety: fan-out, convergence, timelines, cycles
- Clear flow direction (left→right or top→bottom)
- Hero element (most important) gets the most whitespace

## Git Freshness Tracking

Every note MUST include YAML frontmatter linking it to the source code it documents:

```yaml
---
git_tracked_paths:
  - path: agent/src/agent/agents/ac/
    commit: a1b2c3d
  - path: agent/src/agent/core/
    commit: a1b2c3d
last_updated: 2026-03-16
---
```

- **`path`**: Relative path to the source directory this note covers
- **`commit`**: Short hash from `git log -1 --format=%h -- <path>` when the note was written/updated
- **`last_updated`**: Date the note content was last revised
- Multiple paths can be tracked per note (for notes covering multiple source areas)

### Checking Freshness

```bash
git diff --name-only <commit> HEAD -- <path>
```

- **No changes** → note is fresh
- **Minor changes** → note likely accurate, verify specifics
- **Major changes** → note needs updating

### Updating

When updating a note, always update both the `commit` hash and `last_updated` date in frontmatter.

## Maintenance

- When exploring a new topic, update `00-overview.md` to link the new folder
- When adding a child note, update the parent `index.md` sub-topics list and sibling nav links
- When information becomes stale, update or delete — don't leave outdated notes
- Prefer updating existing notes over creating new ones for the same topic
- After any code exploration that reveals new information, update the relevant note and its git tracking
