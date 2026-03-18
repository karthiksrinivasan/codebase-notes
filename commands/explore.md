---
description: Explore a codebase topic and write structured notes. Dispatches an Explore agent, writes notes following the capture matrix, updates navigation, and presents options for deeper exploration.
argument-hint: "TOPIC [--deep] [--parallel TOPIC2 TOPIC3...]"
---

# Explore Topic

You are exploring a topic in the codebase and writing structured notes.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

Notes are at: `~/.claude/repo_notes/<repo_id>/notes/`

Read `00-overview.md` to understand current coverage. Check if this topic already has notes.

## Step 1: Read Existing Notes

If notes exist for this topic, read them first. Check staleness:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale
```

If the topic's notes are FRESH, tell the user and ask what specifically they want to go deeper on.

## Step 2: Dispatch Explore Agent

For the topic, dispatch an Explore agent with a detailed prompt:

```
Very thoroughly explore <path>. I need a deep understanding of:

1. **What is it?** Read any README, pyproject.toml, and top-level files.
2. **Architecture**: Main modules/packages, how it's structured.
3. **Core logic**: Key classes, functions, data structures.
4. **Data flow**: How does data enter, transform, and exit?
5. **Integration points**: How does it connect to other parts?
6. **Configuration**: Env vars, config files, defaults.
7. **API surface**: Endpoints, services, tools, CLI commands.
8. **Schemas**: Database models, type definitions.

Read ALL key source files. Give specifics — function signatures, class names, actual logic.
```

Use `subagent_type: "Explore"` with thoroughness "very thorough".

If `--parallel` was specified with multiple topics, dispatch multiple Explore agents simultaneously.

## Step 3: Write Notes

Follow the RULES.md capture matrix. For each note:

1. Lead with "What is it?" paragraph
2. Use the appropriate capture lenses (What+Why, What+How, What+Where, etc.)
3. Prefer tables for structured data
4. Include a Key Files table
5. Add YAML frontmatter with `git_tracked_paths`
6. Create at least one Excalidraw diagram

## Step 4: Update Parents and Navigation

After writing notes:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render
```

Update `00-overview.md` Knowledge Map.

## Step 5: Present Options

Always present navigation options:

- Dive into sub-topics discovered during exploration
- Go back to overview
- Explore a different top-level topic
- Go deeper on specific areas mentioned in the notes
