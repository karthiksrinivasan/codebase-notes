---
name: code-review
description: Review PRs and feature branches with multi-persona analysis. Generates onboarding context and structured reviews from five perspectives: Systems Architect, Domain Expert, Standards Compliance, Adversarial Path Tracer, and Build & Runtime Verifier.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/code-review/SKILL.md` → plugin root is `../../`.

# Code Review

Review PRs and feature branches with structured, multi-persona analysis. Each review produces two artifacts:
- **context.md** — onboarding context a new engineer needs to understand the change
- **review.md** — structured review from five specialist personas

## Subcommands

| Subcommand | Arguments | Description |
|------------|-----------|-------------|
| `new` | `"identifier"` (required), `--base BRANCH` | Create a new review for a PR or branch |
| `list` | (none) | List all reviews for the current repo |
| `view` | `"identifier"` (required) | Read and display an existing review |
| `update` | `"identifier"` (required), `--focus AREA` | Re-run or amend a review with updated diff or focused area |
| `fix` | `"identifier"` (required), `--scope SCOPE`, `--include-deferred` | Fix findings from the review and update review docs |

**Identifier formats:**
- PR number: `#123`, `!456` (GitLab MR)
- Branch name: `feat/composition-embeddings`, `fix/auth-bug`
- Bare number: `123` (interpreted as PR/MR number)

**Examples:**
- `/codebase-notes:code-review new "#42"` — review PR #42 (quote the `#` to avoid shell comment)
- `/codebase-notes:code-review new "!89"` — review GitLab MR !89
- `/codebase-notes:code-review new "feat/new-agent"` — review branch
- `/codebase-notes:code-review new "feat/new-agent" --base "develop"` — review branch against develop
- `/codebase-notes:code-review list`
- `/codebase-notes:code-review view "feat/new-agent"`
- `/codebase-notes:code-review update "#42" --focus "error handling"`
- `/codebase-notes:code-review fix "#42"` — fix critical+suggestion findings from PR #42's review (default scope)
- `/codebase-notes:code-review fix "#42" --scope critical` — fix only critical findings
- `/codebase-notes:code-review fix "#42" --scope all` — fix everything including nits

**Note:** Always quote identifiers starting with `#` or `!` — these are shell special characters.

---

## Storage Structure

```
~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/
├── context.md     # Onboarding context — prereqs, motivation, scope, architecture impact
├── review.md      # Multi-persona review — five specialist perspectives, versioned
└── fix-plan.md    # Fix execution plan — clusters, ordering, conflict resolution
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
| `--base BRANCH` | No | Override base branch detection (default: auto-detect from PR metadata or `git symbolic-ref`) |

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

After extracting the head branch, fetch the latest commits:

```bash
git fetch origin <head_branch> 2>/dev/null || true
```

**If branch name:**

```bash
# Ensure branch is available locally
git fetch origin <branch> 2>/dev/null || true

# Determine the base branch (usually main or master)
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main"
```

Use the detected base branch for all diffs.

If `--base` was provided, use it instead of auto-detection. This is important for branches that diverged from non-default branches (e.g., `feat/x` branched from `develop`, not `main`).

### Step 2: Gather the Diff

Compute the merge base to get only changes introduced by the branch, excluding unrelated commits merged into the base since the branch diverged.

```bash
# Compute the common ancestor
MERGE_BASE=$(git merge-base <base> <head>)

# Capture SHAs for version tracking
HEAD_SHA=$(git rev-parse --short <head>)
MERGE_BASE_SHA=$(git rev-parse --short $MERGE_BASE)

# Log: two-dot shows commits on head not on base
git log $MERGE_BASE..<head> --oneline --no-merges

# Diff: from merge-base to head shows only the branch's changes
git diff $MERGE_BASE <head> --stat
git diff $MERGE_BASE <head>
```

**Note:** `git log` uses two-dot (`..`) for "commits reachable from head but not base." `git diff` takes two refs directly (from merge-base to head). Do NOT use three-dot (`...`) — it has different semantics for `git log` vs `git diff` and can produce incorrect results.

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

**Branch-mode context enrichment** (when no PR metadata is available):

1. Read full commit bodies (not just oneline): `git log --format="%B" $MERGE_BASE..<head>`
2. Check if a PR already exists for this branch: `gh pr list --head <branch> --json number,title,body --limit 1`
   - If found, pull its metadata and use it as if this were a PR review
3. If commit messages are insufficient (all single-line, no descriptive bodies), prompt the user: "No PR description available. What is this branch trying to accomplish? (one sentence, or press Enter to skip)"
4. Store the user's response in context.md under "Why This Change"

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

**Severity definitions** used across all personas:

| Severity | Meaning | Action |
|----------|---------|--------|
| `critical` | Blocks merge — correctness bug, data loss risk, security issue | Must fix before merge |
| `suggestion` | Should address — design concern, maintainability issue, missing test | Address before merge if feasible |
| `nit` | Optional improvement — style, naming, minor cleanup | Fix if convenient, skip if not |

**Document-level status values** (hyphenated compounds — separate vocabulary from finding-level):

| Status | Set by | Meaning |
|--------|--------|---------|
| `review-in-progress` | `new` (initial) | Review being written |
| `reviewed` | `new` (final) | Initial review complete |
| `review-updated` | `update` | Progressive review performed |
| `fixes-applied` | `fix` | Fixes committed, awaiting re-review |
| `merged` | `update` (lifecycle) | PR was merged |
| `abandoned` | `update` (lifecycle) | PR was closed without merging |

**Finding-level status values** (single words — separate vocabulary from document-level):

| Status | Set by | Meaning |
|--------|--------|---------|
| `new` | `new`, `update` | First appearance |
| `persists` | `update` | Was found before, code not fixed yet |
| `resolved` | `update` | Previously found, no longer applies |
| `missed` | `update` | Found on code that existed in prior version — **requires reasoning** |
| `regressed` | `update` | Was resolved or fixed, came back |
| `fixed` | `fix` | Addressed by fix command |
| `deferred` | `fix` | User chose not to fix |

**Finding ID prefixes:**

| Persona | Prefix |
|---------|--------|
| Senior Systems Architect | `SA` |
| Domain Expert | `DE` |
| Standards Compliance | `SC` |
| Adversarial Path Tracer | `APT` |
| Build & Runtime Verifier | `BRV` |

Create `~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/review.md`:

```markdown
---
identifier: <original identifier>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
status: reviewed
current_version: 1
head_sha: <HEAD_SHA>
merge_base_sha: <MERGE_BASE_SHA>
last_fix_sha: null
---
# Review: <title>

## Review History

| Version | Date | Head SHA | Trigger | New | Resolved | Persists | Missed | Regressed |
|---------|------|----------|---------|-----|----------|----------|--------|-----------|
| v1 | YYYY-MM-DD | `<HEAD_SHA>` | new | <count> | — | — | — | — |

---

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

#### SA-1 (severity) — Title
**File:** path/to/file.py:line-range
**Status:** new
<Description of the finding with specific details>

### Verdict

<Overall assessment from this persona>

---

## 2. Domain Expert

**Focus:** Domain correctness AND cross-layer semantic reasoning — does the data mean what it should at every stage?

Read the repo's README, CLAUDE.md, and relevant domain-specific notes to understand
what domain this repo operates in. Review the change at two levels:

**Surface-level domain checks:**
- Are domain concepts used correctly?
- Do naming conventions match domain terminology?
- Are domain invariants preserved?
- Would a domain expert find the implementation sensible?

**Cross-layer semantic reasoning (critical — this catches bugs static analysis cannot):**
- Trace data as it flows between layers (API → service → storage → output). At each boundary, ask: *does this transformation preserve the data's domain meaning?*
- Flag normalization, aggregation, or projection steps that destroy domain-meaningful information (e.g., L2-normalizing physics embeddings destroys magnitude, averaging compositions loses phase data)
- Check that filters, scopes, and thresholds match the actual domain of the data (e.g., "novelty vs. literature" scope ≠ "novelty vs. all embeddings" scope)
- Verify that labels, descriptions, and user-facing text accurately describe what the code does (e.g., if the prompt says "literature" but the code queries all data)
- When data has provenance (who produced it, in what order), check that operations preserve or explicitly discard provenance — silent provenance loss is a bug

**Note:** The domain is inferred from the repo's documentation and existing codebase-notes.
For a materials science repo, this means checking units, physical constraints, experiment
terminology, phase data, composition semantics, etc. For a web app, this means checking
business logic, user flows, authorization scope, etc.

### Findings

#### DE-1 (severity) — Title
**File:** path/to/file.py:line-range
**Status:** new
<Description with domain-specific concerns — cross-layer findings should include the specific layer boundary where meaning is lost>

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

#### SC-1 (severity) — Title
**File:** path/to/file.py:line-range
**Status:** new
<Description citing the specific standard violated>

### Verdict

<Overall assessment from this persona>

---

## 4. Adversarial Path Tracer

**Focus:** Runtime edge cases, error propagation, correctness under unusual inputs, behavioral side effects on existing code, and order-of-operations hazards.

Trace through the code paths introduced or modified by this change. Check three categories:

**A. Edge cases and error propagation (standard):**
- What happens with nil/null/None/empty inputs?
- Are error paths handled? Do errors propagate correctly?
- What happens at boundary values (0, max_int, empty list, huge input)?
- Are there implicit assumptions that could break?
- Does the change handle partial failures gracefully?

**B. Behavioral side effects on existing code (critical — this catches the bugs that "it works in isolation" testing misses):**
- Find every caller/consumer of functions modified by this change. Read them. Ask: *does the behavior change break any caller's assumptions?*
- If a function's return type, side effects, or error behavior changed, trace every call site
- If a new feature auto-activates (e.g., a flag defaults to true, a new hook runs unconditionally), check what it does to existing workflows
- If a public API endpoint or tool is added, verify it actually works end-to-end — not just that the code exists, but that the wiring (routes, registrations, deps) is complete
- Check for "silent activation" — features that activate with empty/default inputs when the user expects them to be inert

**C. Order-of-operations and timing hazards (critical — these cause intermittent, hard-to-reproduce bugs):**
- Does the code write before acquiring a lock?
- Does the code read state that might be stale (cached values, on-disk artifacts from a previous version)?
- Does the code advance a cursor/pointer/offset before confirming the current operation succeeded?
- Does the code write to storage before ensuring prerequisite structures (indexes, directories, schemas) exist?
- Are there race conditions between concurrent readers/writers?

### Traced Paths

For each significant code path in the change:

| Path | Input Condition | Expected Behavior | Potential Behavior | Issue? |
|------|----------------|-------------------|--------------------|--------|
| <function/endpoint> | <edge case> | <what should happen> | <what the code might do> | <yes/no + details> |

### Caller Impact

For each modified function with external callers:

| Modified Function | Caller | Assumption That May Break | Severity |
|------------------|--------|--------------------------|----------|
| <function> | <caller file:line> | <what the caller assumes> | <critical/suggestion> |

### Findings

#### APT-1 (severity) — Title
**File:** path/to/file.py:line-range
**Status:** new
<Description with a concrete scenario that triggers the issue>

### Verdict

<Overall assessment from this persona>

---

## 5. Build & Runtime Verifier

**Focus:** Does this code actually run? Verify by executing — not by reading.

This persona catches the class of bugs that are invisible to static analysis:
missing dependencies, broken imports, failing tests, type-checker errors, and
linter violations. **You MUST run commands, not just read code.**

**Step 1: Dependency check**
- Read `pyproject.toml`, `requirements.txt`, `package.json`, `Cargo.toml`, or equivalent
- For every new import in the diff, verify the package is declared as a dependency
- Run: `uv run python -c "import <new_module>"` (or equivalent) to confirm imports resolve
- Check for packages in `[optional-dependencies]` that should be in `[dependencies]` (or vice versa)

**Step 2: Type-checker / linter pass**
- Identify the repo's configured linters from CI config, `pyproject.toml`, `package.json` scripts, or `pre-commit-config.yaml`
- Run the linter on changed files only:
  ```bash
  # Python example — adapt to repo's actual toolchain
  uv run ruff check <changed_files>
  uv run ty check <changed_files>  # or mypy/pyright
  ```
- Report any errors or warnings. Flag unused `type: ignore` / `noqa` comments that suppress warnings for issues no longer present.

**Step 3: Test execution**
- Run tests related to the changed code:
  ```bash
  # Find and run relevant tests
  uv run pytest <test_files_matching_changed_code> -x -v
  ```
- If tests pass, check: do they actually test the new behavior, or are they testing something else and passing coincidentally?
- If tests fail, report the failure with full traceback
- Check for tests that contradict the implementation (test asserts X, code does Y, test still passes because of mocking)

**Step 4: Build / artifact verification**
- If the change adds CLI commands, run them with `--help` to verify they're wired up
- If the change modifies build configuration, run the build
- If the change adds API endpoints or tools, verify they're registered (not just defined)

### Execution Results

| Check | Command | Result | Issues |
|-------|---------|--------|--------|
| Dependency resolution | `uv run python -c "import X"` | pass/fail | <details> |
| Type checker | `uv run ty check file.py` | pass/fail | <details> |
| Linter | `uv run ruff check file.py` | pass/fail | <details> |
| Tests | `uv run pytest test_file.py` | pass/fail | <details> |
| Build / wiring | `<command>` | pass/fail | <details> |

### Findings

#### BRV-1 (severity) — Title
**File:** path/to/file.py:line-range
**Status:** new
<Description with the exact command that revealed the issue and its output>

### Verdict

<Overall assessment from this persona>

---

## Fix Log

_No fixes applied yet. Use `/codebase-notes:code-review fix "<identifier>"` to address findings._

<!--
After fixes are applied, this table is regenerated from per-finding **Status:** fields.
Use: export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path> --action regenerate-fixlog

| Finding | Severity | Status | Fix Summary | Applied In |
|---------|----------|--------|-------------|------------|
| SA-1 | critical | fixed | Added error propagation with typed exception | v2 |
| DE-2 | suggestion | deferred | Requires API change — user chose to defer | — |

IMPORTANT: The per-finding **Status:** field is the single source of truth.
This table is regenerated from those statuses — never edit it independently.
-->

## Summary

| Persona | Verdict | Critical Issues | Suggestions |
|---------|---------|----------------|-------------|
| Systems Architect | <pass/concerns/block> | <count> | <count> |
| Domain Expert | <pass/concerns/block> | <count> | <count> |
| Standards Compliance | <pass/concerns/block> | <count> | <count> |
| Adversarial Path Tracer | <pass/concerns/block> | <count> | <count> |
| Build & Runtime Verifier | <pass/concerns/block> | <count> | <count> |

## Recommended Actions

<Prioritized list of actions, most critical first>
```

After writing review.md, assign finding IDs using the script:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path_to_review.md> --action assign-ids
```

Then update the Review History row counts:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path_to_review.md> --action regenerate-history-row --version 1 --trigger new --head-sha <HEAD_SHA>
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

## Finding Status Transitions

When `update` runs, each finding from the previous version must be reclassified. Use this matrix — the prior status (row) determines valid next statuses (columns):

| Prior Status | new | persists | resolved | missed | regressed | fixed | deferred |
|--------------|-----|----------|----------|--------|-----------|-------|----------|
| `new` | — | if still present | if gone | — | — | — | — |
| `persists` | — | if still present | if gone | — | — | — | — |
| `resolved` | — | — | stays resolved | — | if reappears | — | — |
| `missed` | — | if still present | if gone | — | — | — | — |
| `regressed` | — | if still present | if gone | — | — | — | — |
| `fixed` | — | — | if still gone | — | if reappears | stays fixed | — |
| `deferred` | — | still present (preserve reason) | if gone | — | — | — | stays deferred |

**Key rules:**
- `fixed` → `regressed`: The fix didn't hold. Note "(was fixed in v<N>)" on the finding.
- `deferred` → `persists`: Finding still exists but was intentionally deferred. Preserve the deferred reason as a note.
- `deferred` → `resolved`: Code changed and the deferred issue went away naturally.
- Findings with status `new` or `missed` from the CURRENT version are newly discovered — they don't have a "prior status."

Validate transitions via script:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path> --action validate-transition --from <status> --to <status>
```

### Finding Matching Across Versions

To determine if a finding from v(N) still exists in v(N+1), match using this priority:

1. **Exact file:line match** — same file, same or overlapping line range (within 10 lines of drift)
2. **Same function/class match** — same function or class name in a different file (code was moved). Use `git log --follow` or grep to trace renames.
3. **Semantic match** — same root cause described differently due to refactoring. Keep the original finding ID, update file references and description, mark as `persists (refactored)`.
4. **No match found** — if uncertain whether a new finding is related to a resolved one, classify as `new` and add a note: "Possibly related to resolved finding <ID>."

**Never** match solely by file:line — code moves. **Never** create a duplicate finding for the same root cause — update the existing one.

---

## Subcommand: `list`

### Arguments

None.

### Flow

1. Run Step 0 to resolve the repo ID and code-reviews path
2. List all subdirectories in `code-reviews/`
3. For each review directory, read `context.md` frontmatter for metadata. Also read `review.md` frontmatter for `current_version` and `status`:

   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-frontmatter --path <path_to_review.md> --action read
   ```

4. Present as a table:

```
## Code Reviews

| # | Identifier | Type | Base | Created | Status | Version |
|---|-----------|------|------|---------|--------|---------|
| 1 | pr-123 | PR | main | 2026-03-20 | reviewed | v1 |
| 2 | feat-new-agent | branch | main | 2026-03-25 | fixes-applied | v3 |
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
4. Read and display `review.md`:
   - Show the **Review History** table first (version audit trail)
   - Show the **Summary** table (persona verdicts and counts)
   - Show the **Fix Log** if any fixes have been applied
   - Offer to expand individual persona sections for detail
5. If the review doesn't exist, suggest `/codebase-notes:code-review new`

---

## Subcommand: `update`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"identifier"` | **Yes** | The review identifier |
| `--focus AREA` | No | Focus the re-review on a specific area (e.g., "error handling", "performance") |

### Flow

#### Pre-flight

1. Run Step 0 to resolve the repo ID and code-reviews path
2. Verify the review exists — if not, suggest `new`
3. **Working tree check:**

   ```bash
   git status --porcelain
   ```

   If any tracked files are modified, warn: "Your working tree has uncommitted changes. The review will analyze committed code only, but linter/test checks (Build & Runtime Verifier) will run against your working tree. Consider committing or stashing first for accurate results." Proceed after warning — this is not a hard block for `update` (unlike `fix`).

4. Run pre-flight checks via script:

   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-preflight --review-dir <path_to_review_dir>
   ```

   This returns JSON with: `clean_tree`, `branch_match`, `old_head_valid`, `remote_exists`, `forge_cli`, `pr_state`.

5. Read existing `review.md` — extract via script:

   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-frontmatter --path <path_to_review.md> --action read
   ```

   Extract:
   - `current_version` (N)
   - `head_sha` (OLD_HEAD) from frontmatter
   - `last_fix_sha` from frontmatter (may be null)
   - All findings with their IDs and statuses

#### Fetch and Validate

6. Re-fetch and validate refs:

   ```bash
   git fetch origin <head_branch> 2>/dev/null || true
   ```

   **Validate remote branch exists:**
   ```bash
   git ls-remote origin <head_branch>
   ```
   If empty, the remote branch no longer exists. Check PR lifecycle state (see below).

   **If remote branch is gone and identifier is a PR/MR:**

   Check PR state via forge CLI:
   ```bash
   gh pr view <number> --json state
   # or: glab mr view <number> --output json
   ```

   | PR State | Action |
   |----------|--------|
   | `MERGED` | Update review.md status to `merged` via `review-frontmatter --action update --set status=merged`, add final Review History row with trigger `merged`, report: "PR #N has been merged. Review is complete." |
   | `CLOSED` | Update review.md status to `abandoned`, report: "PR #N was closed without merging." |
   | (unknown) | Error: "Remote branch `<head_branch>` no longer exists. The PR may have been merged or the branch deleted." |

   This ensures `list` shows accurate lifecycle state for completed PRs.

   **Validate OLD_HEAD still exists:**
   ```bash
   git cat-file -t <OLD_HEAD> 2>/dev/null
   ```
   If this fails, OLD_HEAD has been garbage-collected (typically after force-push + 2 weeks). Skip delta diff, perform full re-review with message: "Previous review head `<OLD_HEAD>` has been garbage-collected. Performing full re-review."

   Compute new refs:
   ```bash
   NEW_HEAD_SHA=$(git rev-parse --short <head>)
   MERGE_BASE_SHA=$(git rev-parse --short $(git merge-base <base> <head>))
   ```

   **Determine diff base:** If `last_fix_sha` is set and valid (not null, passes `git cat-file -t`), use it instead of OLD_HEAD for the delta. This ensures fix-introduced changes are excluded from the delta:
   ```
   DIFF_BASE = last_fix_sha if set and valid, else OLD_HEAD (head_sha)
   ```

#### Compute Delta (tree-content comparison)

7. **Tree-content delta** (rebase-proof — compares tree contents, not commit ancestry):

   Use the script for deterministic delta computation:

   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-delta --old-head <DIFF_BASE> --new-head <NEW_HEAD_SHA> --merge-base <MERGE_BASE_SHA> --old-merge-base <OLD_MERGE_BASE_SHA>
   ```

   Where `<OLD_MERGE_BASE_SHA>` is the `merge_base_sha` read from existing review.md frontmatter in step 4.

   The script returns JSON with: `tree_identical`, `history_rewritten`, `old_head_gc`, `merge_base_drift`, `changed_files`.

   **If `tree_identical` is true:** No code changes between versions. Report: "No code changes since last review. Nothing to update." and exit.

   **If `old_head_gc` is true** (OLD_HEAD garbage-collected):
   - Cannot compute tree diff — fall back to full re-review
   - Note in Review History: `update (full re-review — prior ref GC'd)`
   - Classify all findings as `new` (fresh start, no `missed` since we can't compare)

   **If `history_rewritten` is true:**
   - Note in Review History: `update (history rewritten)` in the trigger column
   - Log: "Branch history was rewritten (rebase, amend, or squash) since last review. Using tree-content comparison for accurate delta."
   - **Do NOT nuke prior findings** — the tree diff provides accurate content changes regardless of history rewriting

   **If `merge_base_drift` is true:** Base branch has advanced. Log: "Base branch has advanced (merge-base moved). Integration issues may have appeared." This triggers a full persona re-run even if `--focus` was specified.

   Parse the delta to get changed file:line ranges for classification. Also gather the full branch diff (total scope, same as `new`):

   ```bash
   git diff $MERGE_BASE_SHA <NEW_HEAD_SHA> --stat
   git diff $MERGE_BASE_SHA <NEW_HEAD_SHA>
   ```

   **Note on base branch merges:** If the developer merged the base branch into their feature branch between reviews, the tree delta will include those changes. This is a known limitation. The delta may overcount "new code" regions, which means some findings that would be `missed` get classified as `new` instead — a safe direction to err.

#### Re-run Personas

8. **Re-run personas** (all five, or subset if `--focus` provided — see focus mapping table below. If merge-base drifted, run all five regardless of `--focus`.)

   If `--focus` is provided, re-run the relevant personas with extra attention to that area:

   | Focus Area | Primary Personas | Secondary |
   |-----------|-----------------|-----------|
   | error handling, edge cases | Adversarial Path Tracer | Systems Architect |
   | performance, scalability | Systems Architect | Adversarial Path Tracer |
   | standards, style, conventions | Standards Compliance | Build & Runtime Verifier |
   | domain logic, correctness | Domain Expert | Adversarial Path Tracer |
   | architecture, design | Systems Architect | Domain Expert |
   | security | Adversarial Path Tracer | Standards Compliance |
   | dependencies, imports, build | Build & Runtime Verifier | Standards Compliance |
   | tests, regressions | Build & Runtime Verifier | Adversarial Path Tracer |

   Always run the primary persona(s). Run secondary if the focus area overlaps.

   If no `--focus`, re-run all five personas with the updated diff.

   For each persona, review the full branch diff but with awareness of the delta. Each finding must be classified:

   **Classification rules:**

   | Finding in v(N+1) | Was in v(N)? | In tree delta? | Classification |
   |-------------------|-------------|----------------|----------------|
   | Yes | No | Yes | `new` — normal new finding on new code |
   | Yes | No | No | `missed` — **MUST include reasoning** |
   | Yes | Yes (same) | — | `persists` — not yet addressed |
   | No | Yes | — | `resolved` — finding no longer applies |
   | Yes | Yes (was resolved/fixed) | — | `regressed` — was resolved or fixed, came back |

   **For findings with prior status `fixed` or `deferred`, use the state transition matrix from the Finding Status Transitions section.**

   **Missed finding reasoning (MANDATORY for `missed` classification):**

   When a finding is on code that existed in the previous review version but wasn't flagged, append a `**Missed in v<N> because:**` line. Valid reasons:

   - "Cross-layer interaction: the new code in `<file>` made the coupling between `<A>` and `<B>` visible — this couldn't be traced without seeing both sides"
   - "Context expansion: domain notes on `<topic>` were read this time, revealing that `<assumption>` is incorrect"
   - "Pattern contrast: the new approach in `<file>` highlights that the old code in `<other_file>` has the same class of bug"
   - "Persona overlap: `<other persona>`'s finding `<ID>` in this version drew attention to this related issue"
   - "Genuine oversight: this should have been caught in v<N> — the code path was in scope and the issue is straightforward"

   Be honest. "Genuine oversight" is a valid reason and builds trust.

   **Use the finding matching heuristics from the Finding Matching Across Versions section** to determine if a finding "was in v(N)."

#### Update Documents

9. **Update finding statuses in review.md:**

   - Use the state transition matrix for findings with prior statuses
   - New findings: add with next available ID and `**Status:** new` or `**Status:** missed`
   - Do NOT delete resolved findings — keep them with `resolved` status for audit trail
   - **Regenerate the Fix Log table** from per-finding statuses:

     ```bash
     export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path> --action regenerate-fixlog
     ```

10. **Update Review History table** (single source of truth for version audit):

    Add a new row and regenerate counts:

    ```bash
    export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path> --action regenerate-history-row --version <N+1> --trigger "update" --head-sha <NEW_HEAD_SHA>
    ```

    If history was rewritten, the trigger reads `update (history rewritten)`.
    If OLD_HEAD was GC'd, the trigger reads `update (full re-review — prior ref GC'd)`.

11. **Update frontmatter** (flat keys only):

    ```bash
    export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-frontmatter --path <path> --action update --set current_version=<N+1> --set last_updated=YYYY-MM-DD --set status=review-updated --set head_sha=<NEW_HEAD_SHA> --set merge_base_sha=<MERGE_BASE_SHA>
    ```

    Note: `last_fix_sha` stays unchanged — only the `fix` command updates it.

12. **Update context.md** if the scope changed (new files, different summary)

13. **Present a version diff summary:**

    ```
    ## Review v<N> → v<N+1>

    **Delta:** N files changed, M additions, K deletions (tree-content comparison)

    | Category | Count | Details |
    |----------|-------|---------|
    | New findings | 2 | APT-4 (critical), BRV-3 (suggestion) |
    | Resolved | 5 | SA-1, SA-2, DE-1, SC-1, APT-1 |
    | Persists | 1 | DE-2 (suggestion) |
    | Missed | 1 | APT-5 (critical) — cross-layer interaction |
    | Regressed | 0 | — |
    ```

    Offer: view full updated review, run fix command, view specific findings

### Backward Compatibility: Pre-Versioned Reviews

When `update` or `fix` encounters a review.md without version tracking (no `current_version` in frontmatter):

1. **Treat it as v1** — add flat version keys to frontmatter:
   - `current_version: 1`
   - `head_sha: ???????` (unknown — cannot compute delta for first update)
   - `merge_base_sha: ???????`
   - `last_fix_sha: null`
2. **Assign finding IDs retroactively** — scan existing findings and assign IDs using the persona prefix scheme (SA-1, DE-1, etc.). Set all statuses to `new`:

   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path> --action assign-ids
   ```

3. **Add the Review History table** (with v1 row, head SHA as `???????`) and Fix Log placeholder section
4. **Proceed normally** with the update or fix flow. Since `head_sha` is unknown, the first `update` after migration will fall back to full re-review (same as GC'd OLD_HEAD path).

This migration happens in-place — the review.md is rewritten with the new structure. The original content is preserved; only structure is added.

---

## Subcommand: `fix`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"identifier"` | **Yes** | The review identifier |
| `--scope SCOPE` | No | Which severity threshold to fix: `critical` (critical only), `default` (critical + suggestion, **the default**), `all` (everything including nits) |
| `--include-deferred` | No | Re-include previously deferred findings in the fix plan |

### Flow

#### Phase 0: Pre-flight Checks

1. Run Step 0 to resolve the repo ID and code-reviews path
2. Verify the review exists — if not, suggest `new`
3. **Mandatory branch validation** (HARD BLOCK):

   ```bash
   CURRENT_BRANCH=$(git branch --show-current)
   ```

   Read `head_branch` from `context.md` frontmatter. If `CURRENT_BRANCH` does not match `head_branch`, hard-block: "Fix targets branch `<head_branch>` but you are on `<CURRENT_BRANCH>`. Run `git checkout <head_branch>` first."

   **Do not proceed if branches don't match.** This prevents fixing code on the wrong branch (especially dangerous in PR mode where you might be on `main`).

4. **Mandatory working tree check** (HARD BLOCK):

   ```bash
   git status --porcelain
   ```

   If ANY tracked files are modified or staged, error: "Working tree has uncommitted changes. Please commit or stash your changes before running fix. The fix command auto-commits and your in-progress work would be incorporated into the fix commit."

   **Do not proceed until the working tree is clean.**

   Run pre-flight checks via script for comprehensive validation:

   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-preflight --review-dir <path_to_review_dir> --check-fix
   ```

5. **Check for existing fix-plan.md:**

   If `fix-plan.md` exists in the review directory:
   - Read its frontmatter: `review_version` and `status`
   - If `review_version` does not match `current_version` in review.md, the plan is stale: "A fix plan exists from a previous review version (v<old> vs current v<new>). Creating a new plan."
   - If `status` is `partial`, ask: "A partially completed fix plan exists. Resume it, or create a new one?"
   - If `status` is `planned`, ask: "An unapplied fix plan exists from YYYY-MM-DD. Resume it, or create a new one?"
   - If `status` is `completed`, proceed to create a new plan (previous fixes are done)

#### Phase 1: Gather and Analyze Findings

6. Read `review.md` — extract ALL findings across all personas via script:

   ```bash
   export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path_to_review.md> --action list-findings
   ```

   This returns all findings with: finding ID, severity, status, file references, description.

7. Filter by `--scope`:
   - `critical`: only `critical` severity
   - `default` (default): `critical` + `suggestion`
   - `all`: all severities including `nit`

8. Skip findings with status `resolved` or `fixed`. Also skip `deferred` unless `--include-deferred` is set.

9. If no findings match, report: "No actionable findings to fix at this scope." If deferred findings exist, suggest: "N findings were previously deferred. Run with `--include-deferred` to revisit them." Otherwise suggest `/codebase-notes:code-review update "<identifier>"` to re-review for new findings, or `--scope all` if only nits remain.

#### Phase 2: Plan Fixes

10. **Impact analysis** (discover ALL files that must change):

    For each finding, identify ALL files that must change — not just the file referenced in the finding:
    - If the fix involves renaming: grep for all usages across the codebase
    - If the fix changes a function signature: find all callers
    - If the fix changes a type: find all consumers
    - If the fix requires more than 5 files outside the original review scope, flag: "This fix has broad impact (N files beyond the review scope). Confirm before proceeding."

    Add all impacted files to the finding's file manifest.

11. **Group findings into fix clusters:**

    A fix cluster is a set of findings that touch overlapping code regions (same file within 20 lines of each other, or same function, or shared impacted files from step 10). Findings in a cluster MUST be fixed together because changing one affects the others.

    ```
    Cluster 1: [SA-1, APT-3] — both touch src/config.py:40-60
    Cluster 2: [DE-2] — isolated in src/domain/models.py:15 (+ 8 caller files)
    Cluster 3: [SC-1, SC-2] — both in src/handlers.py naming conventions
    Cluster 4: [BRV-1] — missing dependency in pyproject.toml
    ```

12. **Detect conflicts within and across clusters:**

    Only check for conflicts between findings that (a) touch the same file:line range AND (b) come from different personas. Findings in different files are unlikely to conflict.

    A conflict exists when two findings recommend contradictory changes:
    - Persona A says "extract to helper" vs Persona B says "keep inline"
    - Persona A says "add validation" vs Persona B says "trust internal callers"
    - Persona A says "rename to X" vs Persona B says "rename to Y"

    **Batch conflict resolution** (avoids decision fatigue):

    If 4+ conflicts exist, present ALL conflicts in a summary table first:
    ```
    | # | Finding A | Finding B | Quick Choice |
    |---|-----------|-----------|-------------|
    | 1 | SA-2 (extract helper) | SC-1 (keep inline) | A / B / defer |
    | 2 | DE-3 (add validation) | APT-2 (trust callers) | A / B / defer |
    ```
    Let the user make quick choices, then show full details only for conflicts they want to examine.

    If 1-3 conflicts: present each with full reasoning and ask individually.

    Record decisions in the fix plan. Mark deferred findings as `deferred` with reason.

13. **Determine fix ordering across clusters:**

    Order clusters by:
    1. **Dependencies first** — if Cluster A's fix changes a type/interface that Cluster B depends on, fix A first
    2. **Build/dependency fixes first** — BRV findings (missing deps, broken imports) before code changes
    3. **Critical severity first** within same priority level
    4. **Isolated clusters before coupled clusters** — less risk of cascading issues

14. **Write `fix-plan.md`:**

    Create `~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/fix-plan.md`:

    ```markdown
    ---
    identifier: <original identifier>
    review_version: <current_version from review.md>
    created: YYYY-MM-DD
    last_updated: YYYY-MM-DD
    scope: default
    status: planned
    pre_fix_sha: null
    ---
    # Fix Plan: <title>

    **Review version:** v<N>
    **Scope:** <scope> — <count> findings to address
    **Conflicts resolved:** <count> (see Conflict Resolution below)
    **Deferred:** <count>

    ## Conflict Resolution

    _Decisions made about conflicting findings:_

    | Conflict | Finding A | Finding B | Decision | Reason |
    |----------|-----------|-----------|----------|--------|
    | 1 | SA-2 (extract helper) | SC-1 (keep inline) | SA-2 | User: "prefer DRY here" |

    ## Fix Clusters

    ### Cluster 1: <description> [finding IDs]
    **Files:** <primary files>
    **Impacted files:** <additional files discovered in impact analysis>
    **Order:** 1 (reason)
    **Approach:**
    - <finding ID>: <description of fix approach>

    **Verification:**
    - Run the repo's configured linter on changed files
    - Run the repo's test runner on relevant test files

    ### Deferred Findings

    | Finding | Severity | Reason |
    |---------|----------|--------|
    | SC-3 | nit | Out of scope (--scope default) |
    | DE-4 | suggestion | User deferred: "requires API migration" |

    ## Execution Checklist

    - [ ] Cluster 1: <description>
    - [ ] Post-fix verification (full linter + test suite)
    - [ ] Squash commits
    - [ ] Update review.md with fix status
    ```

15. **Present fix plan to user for approval:**

    Show a summary:
    ```
    ## Fix Plan for <identifier>

    **Scope:** <scope> — N findings to fix
    **Clusters:** N (details of overlapping findings)
    **Conflicts:** N resolved (details)
    **Deferred:** N (reasons)
    **Impact:** N files total (M in review scope, K additional callers/consumers)

    Execution order:
    1. Cluster 1: <description> [finding IDs] — N files
    2. Cluster 2: <description> [finding IDs] — N files

    Full plan saved to: fix-plan.md

    Proceed with fixes? (yes / review plan first / adjust)
    ```

    Wait for user confirmation before proceeding.

#### Phase 3: Execute Fixes

16. **Record pre-fix anchor** (anchored SHA instead of fragile `HEAD~N`):

    ```bash
    PRE_FIX_SHA=$(git rev-parse HEAD)
    ```

    Store this in `fix-plan.md` frontmatter:

    ```bash
    export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-frontmatter --path <path_to_fix-plan.md> --action update --set pre_fix_sha=$PRE_FIX_SHA --set status=in-progress
    ```

17. **Execute cluster by cluster with per-cluster commits:**

    For each cluster, in order:

    a. **Re-validate targets:** Before applying, verify that the code regions referenced in the fix plan still exist and match the expected state. If a previous cluster materially changed this cluster's target, pause and re-plan this cluster based on current code.
    b. Read the current state of all files in the cluster (including impacted files from step 10)
    c. Apply the fix — make the code changes
    d. Run the cluster's verification commands (repo's configured linter + relevant tests on touched files — uses same detection as Build & Runtime Verifier)
    e. **If verification fails:**
       - Do NOT proceed to the next cluster
       - Report the failure with full output
       - Ask the user: "Cluster N verification failed. Options: (1) I'll attempt to fix the verification failure, (2) revert this cluster and skip it, (3) stop here"
       - If reverting: `git checkout -- <files in cluster>`
    f. **If verification passes:** create an intermediate commit and mark the cluster as done:
       ```bash
       git add <files in cluster>
       git commit -m "fix(review): cluster N — <cluster description>"
       ```
       Update fix-plan.md checklist, move to next cluster.

18. **Post-fix full verification:**

    After all clusters are applied:

    ```bash
    # Run full linter on all touched files (using repo's configured linter)
    <repo_linter> <all_files_touched_across_clusters>

    # Run full test suite for affected areas (using repo's configured test runner)
    <repo_test_runner> <test_files_matching_touched_code>
    ```

    If this fails and per-cluster verification passed, the failure is likely from cluster interaction. Use per-cluster commits to identify which cluster combination caused it.

19. **Squash into single commit** (uses anchored SHA from step 16):

    After all verification passes, squash the per-cluster commits into one:

    ```bash
    git reset --soft $PRE_FIX_SHA
    git commit -m "$(cat <<'EOF'
    fix: address code review findings from v<N> review

    Fixes applied:
    - <finding ID>: <summary>
    - <finding ID>: <summary>

    Deferred:
    - <finding ID> (severity): <reason>

    Review: <slug>/review.md
    EOF
    )"
    ```

#### Phase 4: Update Review Documents

20. **Update each finding's status in review.md:**

    For each finding that was fixed, update its entry:

    ```markdown
    #### SA-1 (critical) — Missing error propagation in `parse_config`
    **File:** src/config.py:45-52
    **Status:** fixed
    **Fix:** Added explicit error handling with typed ParseConfigError. Callers updated to catch.
    <Original description remains unchanged>
    ```

    For deferred findings:

    ```markdown
    **Status:** deferred
    **Reason:** Requires API migration — user chose to handle in separate PR
    ```

21. **Regenerate the Fix Log table** from per-finding statuses:

    ```bash
    export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-status --review-path <path> --action regenerate-fixlog
    ```

22. **Update fix-plan.md:**

    ```bash
    export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-frontmatter --path <path_to_fix-plan.md> --action update --set status=completed --set last_updated=YYYY-MM-DD
    ```

    Check off completed clusters in the Execution Checklist.

23. **Update review.md frontmatter:**

    ```bash
    export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts review-frontmatter --path <path_to_review.md> --action update --set last_updated=YYYY-MM-DD --set status=fixes-applied --set last_fix_sha=<SHORT_SHA>
    ```

    Note: `current_version` stays unchanged — only `update` increments it.

24. **Present fix summary:**

    ```
    ## Fixes Applied for <identifier>

    | Finding | Status | Verification |
    |---------|--------|-------------|
    | SA-1 | fixed | linter pass, tests pass |
    | APT-3 | fixed | linter pass, tests pass |

    **Committed:** `<sha>` — "fix: address code review findings from v<N> review"
    **Deferred:** N findings (IDs)

    Next steps:
    - Push the commit and update the PR
    - Run `/codebase-notes:code-review update "<identifier>"` for a follow-up review (v<N+1>)
    ```

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

When resolving for `view`, `update`, or `fix`, also check for partial matches — `123` should find `pr-123` or `mr-123`.

### Disambiguation

When resolving an identifier for `view`, `update`, or `fix`, if multiple slug matches are found:

1. Present all matches with metadata:
   ```
   Multiple reviews match "42":
     1. pr-42 — PR: "Fix auth middleware" (reviewed, v2)
     2. 42 — branch: "42" (review-in-progress, v1)
   Which one? (1/2)
   ```
2. Never silently pick one — ambiguity must be resolved by the user.
3. For `fix`, this is especially important since applying fixes to the wrong review's findings could modify the wrong code.

## Retroactive Setup

When this skill runs on a repo that already has codebase-notes but no `code-reviews/` directory, create it automatically in Step 0. No migration needed — the directory is simply added.

## Cross-Referencing Protocol

The skill MUST cross-reference existing codebase-notes during review:

1. **Before writing context.md:** Read `notes/00-overview.md` to understand repo architecture. For each changed file, grep `git_tracked_paths` across all note frontmatter to find covering notes. Read those notes for domain context.
2. **During review.md:** Each persona should reference relevant notes when making findings. The Domain Expert especially should draw on existing domain notes.
3. **After review.md:** Flag notes that the change may make stale (new patterns not documented, modified components, changed APIs).

This cross-referencing is what distinguishes this skill from a generic code review — it leverages the accumulated knowledge in codebase-notes to produce reviews that understand the repo's architecture and domain.
