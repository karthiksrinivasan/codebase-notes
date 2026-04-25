---
name: diagram
description: Add or update Excalidraw architecture diagrams for codebase notes. Creates diagrams with proper styling and embeds them for native rendering in Obsidian.
allowed-tools: ["Read", "Write", "Bash", "Glob", "Agent"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/diagram/SKILL.md` → plugin root is `../../`.

# Add/Update Diagrams

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `NOTE` | No | Path to the specific note to add a diagram to (e.g., `api/index.md`) |
| `--type TYPE` | No | Diagram type: `architecture`, `dataflow`, `state`, `sequence`, `hierarchy` |
| `--all-missing` | No | Find all notes without diagrams and create them |

**Examples:**
- `/codebase-notes:diagram api/index.md --type architecture`
- `/codebase-notes:diagram --all-missing`

---

You are adding or updating Excalidraw diagrams for codebase notes.

## Step 0: Resolve Vault Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts resolve-vault
```

Notes are at: `~/vaults/<slug>/notes/`

## Step 1: Read the Target Note

Read the note that needs a diagram. Understand:
- What system/component it describes
- What relationships and flows exist
- What would benefit most from visual representation

If no specific `NOTE` was given, check which notes lack diagrams. If `--all-missing` was specified, find all notes without diagrams and create them in batch.

## Step 2: Determine Diagram Type

Based on the note content and `--type` argument:

| Note Type | Diagram Style |
|-----------|--------------|
| Overview/Index | Hub-and-spoke or layered architecture |
| Service/Component | Data flow (request lifecycle, pipeline) |
| Workflow/Process | State machine or timeline |
| Config/Reference | Hierarchy tree or ecosystem map |

## Step 3: Create the Diagram

Create `.excalidraw` JSON with these style rules:
- `roughness: 0` (clean/modern), `fontFamily: 3`, `opacity: 100`
- Descriptive string IDs (`"backend_rect"`, `"arrow_to_mongo"`)
- Shapes need `boundElements` for text; text needs `containerId`
- Arrows need `startBinding`/`endBinding` with `{elementId, focus: 0, gap: 2}`
- Clear flow direction (left-to-right or top-to-bottom)
- Hero element gets the most whitespace

Build diagrams section-by-section (not all at once — large diagrams hit token limits).

Name the file: `<note-name>-<type>.excalidraw` (e.g., `api-architecture.excalidraw`)

Save the `.excalidraw` file alongside the note in the same directory.

## Step 4: Embed in Note

Add to the note's markdown:

```markdown
![[diagram-name.excalidraw]]

Text description of what the diagram shows — how components connect, data flow,
key relationships. This must stand alone without the image.
```

Obsidian renders `.excalidraw` files natively via the Excalidraw plugin. No render script or PNG export needed.

Every diagram MUST have a text description below it.

## Step 5: Verify Diagram Coverage

Run the diagram verifier to confirm coverage is complete:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams
```

If any HIGH or MEDIUM issues remain, go back and create the missing diagrams.
