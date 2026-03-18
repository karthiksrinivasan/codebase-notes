---
description: Conduct deep research on a specific codebase topic, tracing execution paths, mapping dependencies, and producing comprehensive notes. More thorough than explore — reads every relevant file.
argument-hint: "TOPIC [--scope PATH] [--depth deep|exhaustive]"
---

# Deep Research

You are conducting deep research on a specific topic in the codebase. This is more thorough than a standard explore — you will trace execution paths, map all dependencies, and document edge cases.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

Notes are at: `~/.claude/repo_notes/<repo_id>/notes/`

Read `00-overview.md` and any existing notes on the topic first.

## Step 1: Scope the Research

Identify:
- The specific code paths/modules to investigate
- What questions need answering
- What depth is needed (default: deep)

If `--scope` is provided, focus on that path. Otherwise, use the topic to determine scope from the overview.

## Step 2: Dispatch Multiple Explore Agents

For deep research, use multiple parallel Explore agents:

- **Agent 1**: Core module structure, classes, and interfaces
- **Agent 2**: Data flow — trace how data enters, transforms, and exits
- **Agent 3**: Integration points — how this connects to other systems
- **Agent 4**: Edge cases — error handling, fallbacks, retry logic

Use `subagent_type: "Explore"` with thoroughness "very thorough" for each.

If `--depth exhaustive` was specified, add:
- **Agent 5**: Test coverage — what's tested, key fixtures, test patterns
- **Agent 6**: Configuration — all env vars, config files, feature flags
- **Agent 7**: History — recent changes via git log, evolution of the module

## Step 3: Synthesize Findings

Combine all agent results into comprehensive notes:

1. **Architecture note** (index.md) — overall structure, key decisions, diagrams
2. **Implementation notes** — one per major subsystem using capture matrix lenses
3. **Data flow note** — how data moves through the system
4. **Integration note** — how it connects to other parts

Follow the RULES.md capture matrix — apply multiple lenses per note where appropriate.

## Step 4: Create Diagrams

Create at least:
- Architecture diagram (hub-and-spoke or layered)
- Data flow diagram (request lifecycle or pipeline)
- Any state machines or lifecycle diagrams discovered

Render them:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render
```

## Step 5: Finalize

Update navigation, overview, and present findings:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav
```

Present a summary of what was discovered and suggest areas for even deeper investigation.
