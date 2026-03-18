---
name: commits
description: Explore recent git commit history and generate structured notes grouped by author and code area. Useful for understanding what changed recently, onboarding, or release notes.
allowed-tools: ["Read", "Write", "Bash", "Glob"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/commits/SKILL.md` → plugin root is `../../`.

# Explore Commit History

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--author AUTHOR` | No | Author name or email to filter commits. If omitted, lists available authors and asks. |
| `--since TIMERANGE` | No | Time range (default: `4w`). Examples: `1w`, `2m`, `6m` |
| `--path PATH` | No | Path filter for commits (e.g., `src/api/`) |
| `--topic TOPIC` | No | Analyze commits related to a specific implementation area |

**Examples:**
- `/codebase-notes:commits --author "Jane" --since 2w`
- `/codebase-notes:commits --topic "authentication changes"`
- `/codebase-notes:commits --path src/models/`

---

You are generating structured notes from git commit history.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

## Step 1: Generate Commit Notes

Run the commits command with the provided arguments:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts commits --author "AUTHOR" --since "4w" --path ""
```

Adjust `--since` and `--path` based on user input.

If no `--author` is specified, list available authors:

```bash
git log --format='%an' --since=4w | sort -u
```

If `--topic` was specified, filter and analyze commits related to that area.

## Step 2: Review Generated Notes

The command generates markdown files in `~/.claude/repo_notes/<repo_id>/commits/` grouped by author.

Read the generated files and present a summary:
- Number of commits per author
- Most active code areas
- Key changes and patterns

## Step 3: Create Diagrams

Commit notes MUST include at least one Excalidraw diagram to visualize change patterns. Choose the most appropriate diagram type:

| Commit Pattern | Diagram Type |
|---------------|-------------|
| Changes across multiple areas | Architecture diagram highlighting affected components |
| Feature development over time | Timeline or sequence diagram showing progression |
| Refactoring or migration | Before/after data flow comparison |
| Multiple contributors to same area | Component diagram showing ownership/activity zones |
| Cross-cutting changes | Dependency graph showing which systems were touched and why |

For the overall commit summary, create a high-level diagram showing which parts of the codebase were most active and how changes relate to each other.

Build diagrams section-by-section. After creating all `.excalidraw` files:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render
```

View each rendered PNG with the Read tool to verify quality. Fix and re-render until clean. Embed in the relevant commit note with `![description](./filename.png)` and always include a text description below that stands alone without the image.

## Step 4: Summarize (Optional)

If the user wants a summary, write a high-level narrative covering:
- Major features or changes
- Active areas of the codebase
- Patterns (refactoring trends, new modules, etc.)
- Areas that may need documentation updates

## Step 5: Verify Diagram Coverage

**MANDATORY** — run the diagram verifier after creating commit notes:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams
```

If any HIGH or MEDIUM issues are reported, go back and create the missing diagrams. Do not skip this step.

## Step 6: Cross-Reference with Notes

Check if heavily-modified code areas have stale notes:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts stale --no-cache
```

Flag notes that cover the same areas as recent commits.
