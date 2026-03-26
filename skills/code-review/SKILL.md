---
name: code-review
description: Review PRs and feature branches with multi-persona analysis. Generates onboarding context and structured reviews from four perspectives: Systems Architect, Domain Expert, Standards Compliance, and Adversarial Path Tracer.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/code-review/SKILL.md` → plugin root is `../../`.

# Code Review

Review PRs and feature branches with structured, multi-persona analysis. Each review produces two artifacts:
- **context.md** — onboarding context a new engineer needs to understand the change
- **review.md** — structured review from four specialist personas

## Subcommands

| Subcommand | Arguments | Description |
|------------|-----------|-------------|
| `new` | `"identifier"` (required) | Create a new review for a PR or branch |
| `list` | (none) | List all reviews for the current repo |
| `view` | `"identifier"` (required) | Read and display an existing review |
| `update` | `"identifier"` (required), `--focus AREA` | Re-run or amend a review with updated diff or focused area |

**Identifier formats:**
- PR number: `#123`, `!456` (GitLab MR)
- Branch name: `feat/composition-embeddings`, `fix/auth-bug`
- Bare number: `123` (interpreted as PR/MR number)

**Examples:**
- `/codebase-notes:code-review new "#42"` — review PR #42 (quote the `#` to avoid shell comment)
- `/codebase-notes:code-review new "!89"` — review GitLab MR !89
- `/codebase-notes:code-review new "feat/new-agent"` — review branch
- `/codebase-notes:code-review list`
- `/codebase-notes:code-review view "feat/new-agent"`
- `/codebase-notes:code-review update "#42" --focus "error handling"`

**Note:** Always quote identifiers starting with `#` or `!` — these are shell special characters.

---

## Storage Structure

```
~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/
├── context.md    # Onboarding context — prereqs, motivation, scope, architecture impact
└── review.md     # Multi-persona review — four specialist perspectives
```

The `<slug>` is derived from the identifier:
- PR `#123` → `pr-123`
- MR `!456` → `mr-456`
- Branch `feat/composition-embeddings` → `feat-composition-embeddings`

---

## Step 0: Bootstrap and Resolve (ALL subcommands)

**MANDATORY** — always run this before doing anything:

```bash
cd <plugin_root> && test -d .venv || uv sync
```

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

Reviews live at: `~/.claude/repo_notes/<repo_id>/code-reviews/`

If the `code-reviews/` directory doesn't exist, create it:

```bash
mkdir -p ~/.claude/repo_notes/<repo_id>/code-reviews
```

## Step 0.5: Detect Git Forge CLI

Determine which CLI tool is available and which forge the repo uses:

```bash
git remote get-url origin
```

- If the remote contains `gitlab` or the repo has a `.gitlab-ci.yml`: use `glab`
- If the remote contains `github`: use `gh`
- Verify the chosen CLI is installed: `command -v glab` or `command -v gh`
- Store this choice as `FORGE_CLI` for subsequent steps

If neither CLI is available, the skill can still work with raw `git` commands (branch diff mode only — no PR metadata). **If a bare number is passed and no forge CLI is detected, error clearly:** "Cannot resolve numeric identifier without gh or glab CLI. Pass a branch name instead, or install the appropriate CLI."

---

## Subcommand: `new`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"identifier"` | **Yes** | PR/MR number (e.g., `#123`, `!456`) or branch name |

### Step 1: Resolve the Identifier

**Check for existing review first.** If `code-reviews/<slug>/` already exists, tell the user and suggest `/codebase-notes:code-review update` instead. Do not overwrite.

**If PR/MR number** (starts with `#`, `!`, or is a bare number):

```bash
# GitHub
gh pr view <number> --json title,body,baseRefName,headRefName,files,additions,deletions,commits

# GitLab — field names differ, map them:
# title → title, description → body, source_branch → headRefName, target_branch → baseRefName
glab mr view <number> --output json
```

| gh field | glab field | Purpose |
|----------|-----------|---------|
| `title` | `title` | PR/MR title |
| `body` | `description` | PR/MR description |
| `baseRefName` | `target_branch` | Base branch |
| `headRefName` | `source_branch` | Head branch |
| `files` | (use `git diff --stat`) | Changed files |

Extract: title, description, base branch, head branch, files changed.

**If branch name:**

```bash
# Ensure branch is available locally
git fetch origin <branch> 2>/dev/null || true

# Determine the base branch (usually main or master)
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main"
```

Use the detected base branch for all diffs.

### Step 2: Gather the Diff

Always use three-dot diff (`...`) — this shows only the changes introduced by the branch, excluding unrelated commits merged into the base since the branch diverged.

```bash
# For both PR and branch:
git log <base>...<head> --oneline
git diff <base>...<head> --stat
git diff <base>...<head>
```

**Large diff handling (>2000 lines):**
1. Start with `--stat` to get the file list and change counts
2. Prioritize reading files that have matching `git_tracked_paths` in existing codebase-notes (these are the best-understood areas)
3. Then read files with the largest change counts
4. Summarize remaining files from their `--stat` entry only

### Step 3: Gather Cross-Reference Context

This is what makes the review valuable. Read existing codebase-notes that cover the changed areas:

1. **Read the notes index:** `~/.claude/repo_notes/<repo_id>/notes/00-overview.md`
2. **Match changed files to notes:** For each changed file path, check which notes have matching `git_tracked_paths` in their frontmatter. Read those notes.
3. **Read the repo's CLAUDE.md and/or AGENTS.md** from the repo root — these define coding standards for the Standards Compliance persona.
4. **Read project notes** if the branch/PR relates to an active project in `projects/`.

Store the list of cross-referenced notes for inclusion in `context.md`.

### Step 4: Write context.md

Create `~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/context.md`:

```markdown
---
identifier: <original identifier>
type: pr | mr | branch
base_branch: <base>
head_branch: <head>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
status: review-in-progress
---
# <PR/MR title or branch description>

## Pre-requisites

What does a new engineer need to understand before reviewing this change?
Link to relevant codebase-notes sections that provide background.

- [Note title](../../notes/path/to/note.md) — why it's relevant
- [Note title](../../notes/path/to/note.md) — why it's relevant

## Why This Change

What motivated this change? Extract from PR description, commit messages,
and related project notes. What problem does it solve?

## What Changed

### Summary

<High-level summary: N files changed, M additions, K deletions>

### By Area

| Area | Files | Nature of Change |
|------|-------|-----------------|
| <component> | file1.py, file2.py | <what changed and why> |

### Architecture Impact

Does this change affect the system architecture? If yes, include a diagram
showing which components are touched and how data flow changes.

## How It Works

Walk through the implementation approach. What's the core logic?
What patterns does it follow or introduce?

## Related Notes

| Note | Relevance | May Need Update |
|------|-----------|-----------------|
| notes/path/to/note.md | Covers the modified component | Yes/No |
```

If the change touches architectural boundaries (crosses between major components visible in the overview diagram), include an Excalidraw diagram showing the impact. Otherwise, skip diagrams for context.md.

### Step 5: Write review.md

Create `~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/review.md`:

```markdown
---
identifier: <original identifier>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
status: reviewed
---
# Review: <title>

## 1. Senior Systems Architect

**Focus:** Code quality, design patterns, scalability, maintainability, separation of concerns.

Review the change through the lens of a senior systems architect who has worked
on large-scale distributed systems. Consider:

- Does the change follow established patterns in the codebase?
- Are abstractions at the right level?
- Will this scale? Are there performance implications?
- Is the separation of concerns clean?
- Are there better design alternatives?

### Findings

<Structured findings — each with severity (critical/suggestion/nit) and specific file:line references>

### Verdict

<Overall assessment from this persona>

---

## 2. Domain Expert

**Focus:** Domain correctness — does this change make sense in the problem domain?

Read the repo's README, CLAUDE.md, and relevant domain-specific notes to understand
what domain this repo operates in. Review the change for domain-specific correctness:

- Are domain concepts used correctly?
- Do naming conventions match domain terminology?
- Are domain invariants preserved?
- Would a domain expert find the implementation sensible?

**Note:** The domain is inferred from the repo's documentation and existing codebase-notes.
For a materials science repo, this means checking units, physical constraints, experiment
terminology, etc. For a web app, this means checking business logic, user flows, etc.

### Findings

<Structured findings with domain-specific concerns>

### Verdict

<Overall assessment from this persona>

---

## 3. CLAUDE.md / Coding Standards Compliance

**Focus:** Adherence to the repo's own stated standards and conventions.

Read the repo's `CLAUDE.md`, `AGENTS.md`, `.editorconfig`, linter configs,
and any `CONTRIBUTING.md`. Check the change against these standards:

- Does the code follow the repo's stated conventions?
- Are there violations of rules in CLAUDE.md or AGENTS.md?
- Does commit style match the repo's convention?
- Are imports, naming, and file organization consistent with stated standards?

### Standards Referenced

| Source | Key Rules |
|--------|-----------|
| CLAUDE.md | <relevant rules extracted> |
| AGENTS.md | <relevant rules extracted> |
| Other | <linter configs, .editorconfig, etc.> |

### Findings

<Structured findings — each citing the specific standard violated>

### Verdict

<Overall assessment from this persona>

---

## 4. Adversarial Path Tracer

**Focus:** Runtime edge cases, error propagation, correctness under unusual inputs.

Trace through the code paths introduced or modified by this change and look for:

- What happens with nil/null/None/empty inputs?
- Are error paths handled? Do errors propagate correctly?
- Are there race conditions or concurrency issues?
- What happens at boundary values (0, max_int, empty list, huge input)?
- Are there implicit assumptions that could break?
- Does the change handle partial failures gracefully?

### Traced Paths

For each significant code path in the change:

| Path | Input Condition | Expected Behavior | Actual Behavior | Issue? |
|------|----------------|-------------------|-----------------|--------|
| <function/endpoint> | <edge case> | <what should happen> | <what the code does> | <yes/no + details> |

### Findings

<Structured findings — each with a concrete scenario that triggers the issue>

### Verdict

<Overall assessment from this persona>

---

## Summary

| Persona | Verdict | Critical Issues | Suggestions |
|---------|---------|----------------|-------------|
| Systems Architect | <pass/concerns/block> | <count> | <count> |
| Domain Expert | <pass/concerns/block> | <count> | <count> |
| Standards Compliance | <pass/concerns/block> | <count> | <count> |
| Adversarial Path Tracer | <pass/concerns/block> | <count> | <count> |

## Recommended Actions

<Prioritized list of actions, most critical first>
```

### Step 6: Render Diagrams (if any)

If any Excalidraw diagrams were created in the review:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render --repo-id <repo_id>
```

### Step 7: Flag Stale Notes

If the review identified codebase-notes that may need updating based on the changes in this PR/branch, list them:

```
The following notes may become stale after this change merges:
- notes/03-agents/index.md — new agent consumer pattern not documented
- notes/05-infrastructure/02-dagster.md — new job types added
```

Offer to update them with `/codebase-notes:update`.

### Step 8: Present Summary

Show the summary table from review.md and offer:
- View full review details for any persona
- Update the review with a focused area
- Update stale notes identified during review

---

## Subcommand: `list`

### Arguments

None.

### Flow

1. Run Step 0 to resolve the repo ID and code-reviews path
2. List all subdirectories in `code-reviews/`
3. For each review directory, read `context.md` frontmatter for metadata
4. Present as a table:

```
## Code Reviews

| # | Identifier | Type | Base | Created | Status |
|---|-----------|------|------|---------|--------|
| 1 | pr-123 | PR | main | 2026-03-20 | reviewed |
| 2 | feat-new-agent | branch | main | 2026-03-25 | review-in-progress |
```

5. If no reviews exist, suggest `/codebase-notes:code-review new "identifier"` to get started

---

## Subcommand: `view`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"identifier"` | **Yes** | The review identifier (original or slug form) |

### Flow

1. Run Step 0 to resolve the repo ID and code-reviews path
2. Resolve the identifier to a slug. Check both the slug form and scan directory names for partial matches.
3. Read and display `context.md` — summarize the onboarding context
4. Read and display `review.md` — show the summary table first, then offer to expand individual persona sections
5. If the review doesn't exist, suggest `/codebase-notes:code-review new`

---

## Subcommand: `update`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"identifier"` | **Yes** | The review identifier |
| `--focus AREA` | No | Focus the re-review on a specific area (e.g., "error handling", "performance") |

### Flow

1. Run Step 0 to resolve the repo ID and code-reviews path
2. Verify the review exists — if not, suggest `new`
3. Re-gather the diff (it may have changed if new commits were pushed)
4. Read existing review.md for prior findings
5. If `--focus` is provided, re-run only the relevant personas with attention to that area
6. If no `--focus`, re-run all four personas with the updated diff
7. Update both `context.md` and `review.md` with new findings
8. Update `last_updated` and `status` in frontmatter
9. Show a diff summary of what changed in the review (new findings, resolved findings)

---

## Identifier Slug Resolution

Convert identifiers to filesystem-safe slugs:

| Input | Slug |
|-------|------|
| `#123` | `pr-123` |
| `!456` | `mr-456` |
| `123` | `pr-123` (GitHub) or `mr-123` (GitLab) |
| `feat/composition-embeddings` | `feat-composition-embeddings` |
| `fix/auth-bug` | `fix-auth-bug` |

Rule: replace `/` with `-`, strip `#` and `!` prefixes, prepend `pr-` or `mr-` for numeric identifiers.

**Collision handling:** Before creating a directory, check if the slug already exists. If it does and belongs to a different identifier type (e.g., branch `pr/123` colliding with PR `#123`), append the type: `branch-pr-123` vs `pr-123`.

When resolving for `view` or `update`, also check for partial matches — `123` should find `pr-123` or `mr-123`.

## Retroactive Setup

When this skill runs on a repo that already has codebase-notes but no `code-reviews/` directory, create it automatically in Step 0. No migration needed — the directory is simply added.

## Cross-Referencing Protocol

The skill MUST cross-reference existing codebase-notes during review:

1. **Before writing context.md:** Read `notes/00-overview.md` to understand repo architecture. For each changed file, grep `git_tracked_paths` across all note frontmatter to find covering notes. Read those notes for domain context.
2. **During review.md:** Each persona should reference relevant notes when making findings. The Domain Expert especially should draw on existing domain notes.
3. **After review.md:** Flag notes that the change may make stale (new patterns not documented, modified components, changed APIs).

This cross-referencing is what distinguishes this skill from a generic code review — it leverages the accumulated knowledge in codebase-notes to produce reviews that understand the repo's architecture and domain.
