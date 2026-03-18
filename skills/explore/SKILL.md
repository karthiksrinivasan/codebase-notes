---
name: explore
description: Explore a codebase topic in depth and write structured notes with architecture diagrams. Dispatches Explore agents, writes notes following the capture matrix, and presents options for deeper exploration.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/explore/SKILL.md` → plugin root is `../../`.

# Explore Topic

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `TOPIC` | **Yes** | The topic to explore (e.g., "authentication", "API layer", "data pipeline") |
| `--path PATH` | No | Specific source code path to focus on (e.g., `src/api/`, `lib/auth/`) |
| `--deep` | No | Do a deeper exploration (reads more files, traces more paths) |
| `--parallel TOPICS...` | No | Explore multiple topics simultaneously |

**Examples:**
- `/codebase-notes:explore authentication`
- `/codebase-notes:explore "API layer" --path src/api/`
- `/codebase-notes:explore --parallel auth models config`

---

You are exploring a topic in the codebase and writing structured notes.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

Notes are at: `~/.claude/repo_notes/<repo_id>/notes/`

Read `00-overview.md` to understand current coverage. Check if this topic already has notes.

## Step 1: Read Existing Notes

If notes exist for this topic, read them first. Check staleness:

```bash
export REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts stale
```

If the topic's notes are FRESH, tell the user and ask what specifically they want to go deeper on.

## Step 2: Dispatch Explore Agent

For the topic, dispatch an Explore agent with a detailed prompt. If `--path` was specified, scope the exploration to that path. If `--deep` was specified, increase thoroughness.

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
export REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts nav
export REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts render
```

Update `00-overview.md` Knowledge Map.

## Step 5: Present Options

Always present navigation options:

- Dive into sub-topics discovered during exploration
- Go back to overview
- Explore a different top-level topic
- Go deeper on specific areas mentioned in the notes
