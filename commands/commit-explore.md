---
description: Explore recent commit history and generate structured commit notes grouped by author and code area. Useful for understanding what changed recently, onboarding, or preparing release notes.
argument-hint: "--author AUTHOR [--since TIMERANGE] [--path PATH]"
---

# Explore Commit History

You are generating structured notes from git commit history.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

## Step 1: Generate Commit Notes

Run the commits command with the provided arguments:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts commits --author "AUTHOR" --since "4w" --path ""
```

Adjust `--since` (default: 4w) and `--path` based on user input.

If no `--author` is specified, ask the user. Common patterns:
- Specific person: `--author "Jane Doe"` or `--author "jane@example.com"`
- Everyone: run `git log --format='%an' --since=4w | sort -u` first to list authors

## Step 2: Review Generated Notes

The command generates markdown files in `~/.claude/repo_notes/<repo_id>/notes/commits/` grouped by author.

Read the generated files and present a summary to the user:
- Number of commits per author
- Most active code areas
- Key changes and patterns

## Step 3: Summarize (Optional)

If the user wants a summary, read the generated commit note files and write a high-level summary section covering:

- Major features or changes
- Active areas of the codebase
- Patterns (refactoring trends, new modules, etc.)
- Potential areas that may need documentation updates

## Step 4: Cross-Reference with Notes

Check if any heavily-modified code areas have stale notes:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale --no-cache
```

Flag notes that cover the same areas as recent commits — they may need updating.
