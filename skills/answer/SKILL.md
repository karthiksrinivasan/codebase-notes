---
name: answer
description: Answer questions about the codebase using pre-built notes as primary context. Reads relevant notes first, falls back to code exploration only when needed, and updates notes with new findings.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/answer/SKILL.md` → plugin root is `../../`.

# Answer from Notes

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `QUESTION` | **Yes** | The question about the codebase to answer |

**Examples:**
- `/codebase-notes:answer "How does authentication work?"`
- `/codebase-notes:answer "What database is used and how is it configured?"`

---

You are answering a question about the codebase using notes as the primary context source.

## Step 0: Resolve Vault Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts resolve-vault
```

Notes are at: `~/vaults/<slug>/notes/`

## Step 1: Read Session Context and Overview

Start by reading the session context and system map:

```
Read ~/vaults/<slug>/wiki/hot.md
Read ~/vaults/<slug>/notes/overview.md
```

`wiki/hot.md` gives you the current session context and recent findings. `overview.md` gives you the Knowledge Map — use it to identify which topic notes are relevant to the question.

## Step 2: Read Relevant Notes

Based on the question, read the most relevant topic notes:

```
Read ~/vaults/<slug>/notes/<relevant-topic>/index.md
Read ~/vaults/<slug>/notes/<relevant-topic>/<specific-note>.md
```

Notes contain architecture, data flow, schemas, config, key files, and diagrams. This is 10-100x cheaper than re-exploring source code and gives you the "why" that code alone can't.

## Step 3: Answer the Question

Answer from notes first. Cite the specific notes you're drawing from using wikilinks when helpful (e.g., "as described in [[auth/oauth|the OAuth note]]").

If notes are sufficient, answer and you're done.

## Step 4: Fall Back to Code (if needed)

If notes don't cover what's needed — a specific function signature, a recently added feature, an edge case:

1. Use the Key Files tables in notes as starting points
2. Explore the specific code needed
3. Answer the question

## Step 5: Update Notes (pay it forward)

After learning something new from code exploration that isn't in the notes:

- **Minor addition**: Edit the existing note to add the new information
- **New sub-topic**: Create a child note if the topic warrants its own page
- **Correction**: Fix any stale information

Use wikilinks for any cross-references added. Then update `wiki/hot.md` with the new finding.

This keeps notes as a living cache of codebase understanding.
