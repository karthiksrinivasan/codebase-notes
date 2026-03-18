---
description: Initialize codebase notes for the current repository. Bootstraps scripts, resolves repo identity, scaffolds the notes directory, and writes the initial overview.
argument-hint: "[--force]"
allowed-tools: ["Read", "Write", "Edit", "Bash(cd ~/.claude/*)", "Bash(uv run*)", "Bash(git *)", "Bash(find *)", "Bash(ls *)", "Glob", "Grep", "Agent"]
---

# Initialize Codebase Notes

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--force` | No | Reinitialize even if notes already exist. Destroys existing notes and starts fresh. |

No positional arguments needed.

**Examples:**
- `/codebase-notes:init` — Initialize notes for the current repo
- `/codebase-notes:init --force` — Reinitialize, replacing any existing notes

---

You are initializing codebase notes for the current repository. Follow these steps exactly.

## Step 0: Bootstrap and Resolve

1. **Bootstrap scripts** — ensure the virtual environment exists:

```bash
cd ~/.claude/skills/codebase-notes && test -d .venv || uv sync
```

2. **Resolve repo identity**:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

Save this repo ID — it determines where notes are stored: `~/.claude/repo_notes/<repo_id>/`

3. **Check for existing notes**:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale 2>/dev/null
```

If notes already exist, tell the user and show the staleness report. Ask if they want to:
- Explore more topics
- Update stale notes
- Start fresh (requires `--force`)

If `--force` was NOT passed and notes exist, do NOT reinitialize. Instead, present the knowledge map.

4. **Check for v1 notes** in the repo (`docs/notes/`, `notes/`, `docs/knowledge/`). If found, offer migration:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts migrate --from <path>
```

## Step 1: Scaffold

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts scaffold
```

## Step 2: Explore the Repository

Before writing anything, understand the repo:

- Read README.md, CLAUDE.md, any onboarding docs
- Check `ls` at root for top-level structure
- Identify languages, build tools, major systems/packages
- Use an Explore agent (subagent_type: "Explore") for a "very thorough" initial scan

## Step 3: Write the Overview

Read the RULES.md that was copied into the notes directory. Then write `00-overview.md` with:

1. **"What is this?"** — one paragraph describing the repo
2. **Architecture section** — Excalidraw diagram + text description
3. **Languages & Build Tools** — what's used and how
4. **Top-Level Packages** — table of directories, purposes, languages
5. **Knowledge Map** — table of all topics with exploration status

## Step 4: Present Topics

Show the Knowledge Map as numbered options. Let the user choose what to explore next.

After creating diagrams, render them:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render
```

After writing notes, rebuild navigation:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav
```
