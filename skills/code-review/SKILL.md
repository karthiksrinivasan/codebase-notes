---
name: code-review
description: Review PRs and feature branches with multi-persona analysis. Generates onboarding context and structured reviews from five perspectives: Systems Architect, Domain Expert, Standards Compliance, Adversarial Path Tracer, and Build & Runtime Verifier.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch"]
---

**Shared context:** Read `${CLAUDE_PLUGIN_ROOT}/references/shared-context.md` for note structure rules and diagram guidelines.

**Script shorthand:** All scripts invoked via:
```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts <command> [args]
```
Abbreviated as `run-script <command> [args]` below. Always set `REPO_ROOT` first.

# Code Review

Multi-persona review producing two artifacts per review:
- **context.md** — onboarding context for understanding the change
- **review.md** — structured review from five specialist personas

## Subcommands

| Subcommand | Arguments | Description |
|------------|-----------|-------------|
| `new` | `"identifier"` (required), `--base BRANCH` | Create a new review for a PR or branch |
| `list` | (none) | List all reviews for the current repo |
| `view` | `"identifier"` (required) | Read and display an existing review |
| `update` | `"identifier"` (required), `--focus AREA` | Re-run or amend review with updated diff or focused area |
| `fix` | `"identifier"` (required), `--scope SCOPE`, `--include-deferred` | Fix findings and update review docs |
| `loop` | `"branch1" ...` or `--stack BASE`, `--project`, `--max-cycles`, `--auto-approve`, `--dry-run`, `--resume` | Automated review→fix→update cycle across branches |

**Identifier formats:** PR number (`#123`, `!456` for GitLab), branch name (`feat/composition-embeddings`), bare number (`123` = PR/MR number).

**Examples:**
```
/codebase-notes:code-review new "#42"              # review PR #42
/codebase-notes:code-review new "!89"              # review GitLab MR !89
/codebase-notes:code-review new "feat/new-agent"   # review branch
/codebase-notes:code-review new "feat/x" --base "develop"  # custom base
/codebase-notes:code-review list
/codebase-notes:code-review view "feat/new-agent"
/codebase-notes:code-review update "#42" --focus "error handling"
/codebase-notes:code-review fix "#42"                        # default scope (critical+suggestion)
/codebase-notes:code-review fix "#42" --scope critical       # critical only
/codebase-notes:code-review fix "#42" --scope all            # everything including nits
/codebase-notes:code-review fix "#42" --include-deferred     # re-include deferred findings
/codebase-notes:code-review loop "feat/auth" "feat/api"                     # review two branches
/codebase-notes:code-review loop --stack "feat/vertical-slice"              # discover and review stack
/codebase-notes:code-review loop --stack "feat/vertical-slice" --project "projects/comp-embeddings" --auto-approve
/codebase-notes:code-review loop --resume                                   # resume interrupted loop
/codebase-notes:code-review loop --stack "feat/vertical-slice" --dry-run    # preview without executing
```

**Note:** Always quote identifiers starting with `#` or `!` — shell special characters.

---

## Storage Structure

```
~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/
├── context.md     # Onboarding context
├── review.md      # Multi-persona review, versioned
└── fix-plan.md    # Fix execution plan
```

## Identifier Slug Resolution

| Input | Slug |
|-------|------|
| `#123` | `pr-123` |
| `!456` | `mr-456` |
| `123` | `pr-123` (GitHub) or `mr-123` (GitLab) |
| `feat/composition-embeddings` | `feat-composition-embeddings` |

Rule: replace `/` with `-`, strip `#`/`!` prefixes, prepend `pr-`/`mr-` for numeric. Collision handling: append type suffix if slug collides across identifier types (e.g., `branch-pr-123` vs `pr-123`).

### Disambiguation

When resolving for `view`/`update`/`fix`, if multiple slug matches found — present all with metadata and ask user to choose. Never silently pick one. Especially critical for `fix` (wrong review = wrong code changes). Also check partial matches: `123` should find `pr-123` or `mr-123`.

---

## Step 0: Bootstrap + Forge Detection (ALL subcommands)

**MANDATORY** — run before anything else:

```bash
cd ${CLAUDE_PLUGIN_ROOT} && test -d .venv || uv sync
```

```bash
run-script repo-id
```

Reviews live at: `~/.claude/repo_notes/<repo_id>/code-reviews/`. Create `code-reviews/` dir if missing.

**Forge detection:** `run-script review-forge` → returns JSON with `forge`, `cli`, `cli_available`, `cli_authenticated`, `cli_usable`. Use `cli_usable` to determine if PR/MR metadata is available. If `cli_usable` is false, fall back to branch-diff-only mode. If bare number passed without usable forge CLI, error: "Cannot resolve numeric identifier without gh or glab CLI."

---

## Severity Definitions

| Severity | Meaning | Action |
|----------|---------|--------|
| `critical` | Blocks merge — correctness bug, data loss, security | Must fix before merge |
| `suggestion` | Should address — design concern, maintainability, missing test | Address before merge if feasible |
| `nit` | Optional — style, naming, minor cleanup | Fix if convenient |

## Document-Level Status Values (hyphenated)

| Status | Set by | Meaning |
|--------|--------|---------|
| `review-in-progress` | `new` (initial) | Review being written |
| `reviewed` | `new` (final) | Initial review complete |
| `review-updated` | `update` | Progressive review performed |
| `fixes-applied` | `fix` | Fixes committed |
| `merged` | `update` (lifecycle) | PR was merged |
| `abandoned` | `update` (lifecycle) | PR closed without merge |

## Finding-Level Status Values (single words)

| Status | Set by | Meaning |
|--------|--------|---------|
| `new` | `new`, `update` | First appearance |
| `persists` | `update` | Found before, not fixed |
| `resolved` | `update` | Previously found, no longer applies |
| `missed` | `update` | Found on code from prior version — **requires reasoning** |
| `regressed` | `update` | Was resolved/fixed, came back |
| `fixed` | `fix` | Addressed by fix command |
| `deferred` | `fix` | User chose not to fix |

## Finding Status Transition Matrix

Prior status (row) → valid next status (columns):

| Prior | new | persists | resolved | missed | regressed | fixed | deferred |
|-------|-----|----------|----------|--------|-----------|-------|----------|
| `new` | — | if still present | if gone | — | — | — | — |
| `persists` | — | if still present | if gone | — | — | — | — |
| `resolved` | — | — | stays resolved | — | if reappears | — | — |
| `missed` | — | if still present | if gone | — | — | — | — |
| `regressed` | — | if still present | if gone | — | — | — | — |
| `fixed` | — | — | if still gone | — | if reappears | stays fixed | — |
| `deferred` | — | still present (preserve reason) | if gone | — | — | — | stays deferred |

**Key:** `fixed` → `regressed` means fix didn't hold — note "(was fixed in v<N>)". `deferred` → `persists` preserves deferred reason. `deferred` → `resolved` means issue went away naturally.

Validate via: `run-script review-status --review-path <path> --action validate-transition --from <status> --to <status>`

## Finding Matching Across Versions

To determine if a finding from v(N) exists in v(N+1), match by priority:

1. **Exact file:line** — same file, overlapping line range (within 10 lines drift)
2. **Same function/class** — function/class name in different file (code moved). Use `git log --follow` or grep.
3. **Semantic match** — same root cause, different description due to refactoring. Keep original ID, update refs, mark `persists (refactored)`.
4. **No match** — classify as `new`. Add note if possibly related to a resolved finding.

**Never** match solely by file:line (code moves). **Never** create duplicate for same root cause.

---

## Subcommand: `new`

### Step 1: Resolve the Identifier

Check if `code-reviews/<slug>/` exists — if so, suggest `update` instead.

**If PR/MR number:** Fetch metadata via forge CLI:
```bash
gh pr view <number> --json title,body,baseRefName,headRefName,files,additions,deletions,commits
# GitLab: glab mr view <number> --output json
```

| gh field | glab field | Purpose |
|----------|-----------|---------|
| `title` | `title` | PR/MR title |
| `body` | `description` | Description |
| `baseRefName` | `target_branch` | Base branch |
| `headRefName` | `source_branch` | Head branch |

After extracting head branch: `git fetch origin <head_branch> 2>/dev/null || true`

**If branch:** Fetch and detect base:
```bash
git fetch origin <branch> 2>/dev/null || true
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main"
```

If `--base` provided, use it instead of auto-detection.

### Step 2: Gather the Diff

```bash
MERGE_BASE=$(git merge-base <base> <head>)
HEAD_SHA=$(git rev-parse --short <head>)
MERGE_BASE_SHA=$(git rev-parse --short $MERGE_BASE)
git log $MERGE_BASE..<head> --oneline --no-merges
git diff $MERGE_BASE <head> --stat
git diff $MERGE_BASE <head>
```

**Note:** `git log` uses two-dot (`..`) for "commits reachable from head but not base." `git diff` takes two refs directly (from merge-base to head). Do NOT use three-dot (`...`) — it has different semantics for log vs diff and can produce incorrect results.

**Large diff handling (>2000 lines):**
1. Start with `--stat` to get file list and change counts
2. Prioritize reading files that have matching `git_tracked_paths` in existing codebase-notes (best-understood areas)
3. Then read files with the largest change counts
4. Summarize remaining files from their `--stat` entry only

### Step 3: Gather Cross-Reference Context

1. Read notes index: `~/.claude/repo_notes/<repo_id>/notes/00-overview.md`
2. Match changed files to notes via `git_tracked_paths` frontmatter. Read matching notes.
3. Read repo's `CLAUDE.md` and/or `AGENTS.md` for Standards Compliance persona.
4. If branch/PR relates to an active project, read ONLY `projects/<name>/context.md` — not other project files.

**Branch-mode enrichment** (no PR metadata):
1. Read full commit bodies: `git log --format="%B" $MERGE_BASE..<head>`
2. Check for existing PR: `gh pr list --head <branch> --json number,title,body --limit 1`
3. If commits insufficient, prompt user for one-sentence motivation
4. Store in context.md "Why This Change"

### Step 4: Write context.md

Read template at `${CLAUDE_PLUGIN_ROOT}/skills/code-review/templates/context.md`. Fill placeholders: `{identifier}`, `{type}`, `{base}`, `{head}`, `{date}`, `{title}`, `{prerequisites}`, `{motivation}`, `{change_summary}`, `{area_rows}`, `{architecture_impact}`, `{implementation_approach}`, `{related_notes}`.

Write to `~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/context.md`. Set status to `review-in-progress` initially.

If the change touches architectural boundaries (crosses between major components visible in the overview diagram), include an Excalidraw diagram showing the impact. Otherwise, skip diagrams for context.md.

### Step 5: Write review.md — Multi-Persona Review

Read the persona reference files at `${CLAUDE_PLUGIN_ROOT}/skills/code-review/personas/`.

For each of the four inline personas, in this order:
1. **Systems Architect** — read `personas/systems-architect.md`, review diff through SA lens
2. **Domain Expert** — read `personas/domain-expert.md`, review with cross-layer reasoning
3. **Standards Compliance** — read `personas/standards-compliance.md`, check against repo standards
4. **Adversarial Path Tracer** — read `personas/adversarial-path-tracer.md`, trace paths (runs LAST — benefits from seeing other personas' findings)

These run sequentially in the current context for cross-persona synergy. Each persona writes its section with findings using its ID prefix (SA, DE, SC, APT).

**Finding ID prefixes:** SA (Systems Architect), DE (Domain Expert), SC (Standards Compliance), APT (Adversarial Path Tracer), BRV (Build & Runtime Verifier).

After the four inline personas, dispatch Build & Runtime Verifier as a sub-agent:

Use the Agent tool with:
- subagent_type: `codebase-notes:review-build-runtime-verifier`
- prompt: Include changed files list with stat summary, finding ID prefix BRV, and repo toolchain info from codebase notes if available

The BRV agent reads files itself and runs commands — do NOT include the full diff in its prompt. Insert BRV's returned section as "## 5. Build & Runtime Verifier" in review.md.

**Assemble review.md:** Read template at `${CLAUDE_PLUGIN_ROOT}/skills/code-review/templates/review.md`. Fill placeholders: `{identifier}`, `{date}`, `{title}`, `{head_sha}`, `{merge_base_sha}`, `{new_count}`, `{persona_sections}`, `{summary_rows}`, `{recommended_actions}`.

Write to `~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/review.md`.

**Fix Log:** The review.md includes a Fix Log section. The per-finding `**Status:**` field is the single source of truth — the Fix Log table is regenerated from those statuses. Never edit the Fix Log independently.

**Post-write scripts:**
```bash
run-script review-status --review-path <path> --action assign-ids
run-script review-status --review-path <path> --action regenerate-history-row --version 1 --trigger new --head-sha <HEAD_SHA>
```

### Step 6: Render Diagrams (if any)

```bash
run-script render --repo-id <repo_id>
```

### Step 7: Flag Stale Notes

List notes that may become stale after the change merges. Offer to update with `/codebase-notes:update`.

### Step 8: Present Summary

Show summary table. Offer: view persona details, update review, update stale notes.

---

## Subcommand: `update`

### Pre-flight

1. Run Step 0
2. Verify review exists — if not, suggest `new`
3. **Working tree check:** `git status --porcelain` — warn (not block) if uncommitted changes
4. Run pre-flight script: `run-script review-preflight --review-dir <path>` → returns JSON: `clean_tree`, `branch_match`, `old_head_valid`, `remote_exists`, `forge_cli`, `pr_state`
5. Read review.md frontmatter: `run-script review-frontmatter --path <path> --action read` → extract `current_version` (N), `head_sha` (OLD_HEAD), `last_fix_sha`, `merge_base_sha` (OLD_MERGE_BASE), all findings

### Fetch and Validate

6. Fetch: `git fetch origin <head_branch> 2>/dev/null || true`

**Validate remote branch:** `git ls-remote origin <head_branch>` — if empty, check PR lifecycle:

| PR State | Action |
|----------|--------|
| `MERGED` | Set status=`merged` via `review-frontmatter --action update --set status=merged`, add history row with trigger `merged` |
| `CLOSED` | Set status=`abandoned` |

**Validate OLD_HEAD:** `git cat-file -t <OLD_HEAD> 2>/dev/null` — if fails, skip delta, full re-review.

**Determine diff base:** `DIFF_BASE = last_fix_sha if set and valid, else OLD_HEAD`

### Compute Delta (tree-content comparison)

7. Run delta script:
```bash
run-script review-delta --old-head <DIFF_BASE> --new-head <NEW_HEAD_SHA> --merge-base <MERGE_BASE_SHA> --old-merge-base <OLD_MERGE_BASE_SHA>
```

Returns JSON: `tree_identical`, `history_rewritten`, `old_head_gc`, `merge_base_drift`, `changed_files`.

| Result | Action |
|--------|--------|
| `tree_identical` | "No code changes since last review." Exit. |
| `old_head_gc` | Full re-review. Trigger: `update (full re-review — prior ref GC'd)`. All findings = `new`. |
| `history_rewritten` | Trigger: `update (history rewritten)`. Do NOT nuke findings — tree diff is accurate. |
| `merge_base_drift` | "Base branch advanced — integration issues may have appeared." Force full persona re-run even with `--focus`. |

**Note on base branch merges:** If the developer merged the base branch into their feature branch between reviews, the tree delta will include those changes. The delta may overcount "new code" regions, meaning some findings that would be `missed` get classified as `new` instead — a safe direction to err.

Gather full branch diff (total scope, same as `new`):
```bash
git diff $MERGE_BASE_SHA <NEW_HEAD_SHA> --stat
git diff $MERGE_BASE_SHA <NEW_HEAD_SHA>
```

### Re-run Personas

8. Run all five personas (or subset if `--focus` — override to all if merge-base drifted).

**Focus mapping:**

| Focus Area | Primary Personas | Secondary |
|-----------|-----------------|-----------|
| error handling, edge cases | APT | SA |
| performance, scalability | SA | APT |
| standards, style, conventions | SC | BRV |
| domain logic, correctness | DE | APT |
| architecture, design | SA | DE |
| security | APT | SC |
| dependencies, imports, build | BRV | SC |
| tests, regressions | BRV | APT |

For inline personas (SA, DE, SC, APT): read persona reference files from `${CLAUDE_PLUGIN_ROOT}/skills/code-review/personas/`, review full branch diff with delta awareness. For BRV: dispatch sub-agent `codebase-notes:review-build-runtime-verifier` as in `new` (stat summary + changed files, no full diff).

**Classification rules for each finding:**

| In v(N+1)? | Was in v(N)? | In tree delta? | Classification |
|------------|-------------|----------------|----------------|
| Yes | No | Yes | `new` |
| Yes | No | No | `missed` — **MUST include reasoning** |
| Yes | Yes (same) | — | `persists` |
| No | Yes | — | `resolved` |
| Yes | Yes (was resolved/fixed) | — | `regressed` |

For `fixed`/`deferred` prior statuses, use the state transition matrix above.

**Missed finding reasoning (MANDATORY):** Append `**Missed in v<N> because:**` with one of:
- "Cross-layer interaction: new code made coupling visible"
- "Context expansion: domain notes read this time revealed incorrect assumption"
- "Pattern contrast: new approach highlights same bug class in old code"
- "Persona overlap: another persona's finding drew attention to this"
- "Genuine oversight: should have been caught — straightforward issue"

### Update Documents

9. Update finding statuses in review.md. Do NOT delete resolved — keep for audit trail.
10. Regenerate Fix Log: `run-script review-status --review-path <path> --action regenerate-fixlog`
11. Add Review History row: `run-script review-status --review-path <path> --action regenerate-history-row --version <N+1> --trigger "update" --head-sha <NEW_HEAD_SHA>`
12. Update frontmatter: `run-script review-frontmatter --path <path> --action update --set current_version=<N+1> --set last_updated=YYYY-MM-DD --set status=review-updated --set head_sha=<NEW_HEAD_SHA> --set merge_base_sha=<MERGE_BASE_SHA>` (leave `last_fix_sha` unchanged)
13. Update context.md if scope changed
14. Present version diff summary with category counts. Offer: view full review, run fix, view specific findings.

---

## Subcommand: `fix`

### Phase 0: Pre-flight Checks

1. Run Step 0, verify review exists
2. **Branch validation (HARD BLOCK):**
   ```bash
   CURRENT_BRANCH=$(git branch --show-current)
   ```
   Read `head_branch` from context.md frontmatter. If `CURRENT_BRANCH` does not match `head_branch`, hard-block: "Fix targets branch `<head_branch>` but you are on `<CURRENT_BRANCH>`. Run `git checkout <head_branch>` first."
   **Do not proceed if branches don't match.** This prevents fixing code on the wrong branch (especially dangerous in PR mode where you might be on `main`).

3. **Working tree check (HARD BLOCK):**
   ```bash
   git status --porcelain
   ```
   If ANY tracked files modified or staged, error: "Working tree has uncommitted changes. Please commit or stash before running fix. The fix command auto-commits and your in-progress work would be incorporated into the fix commit."
   **Do not proceed until working tree is clean.**
4. Run: `run-script review-preflight --review-dir <path> --check-fix`
5. **Check existing fix-plan.md:** If exists, check `review_version` vs `current_version` (stale?), `status` (partial → resume?, planned → resume?, completed → new plan).

### Phase 1: Gather Findings

6. Extract findings: `run-script review-status --review-path <path> --action list-findings`
7. Filter by `--scope`: `critical` (critical only), `default` (critical+suggestion, **the default**), `all` (including nits)
8. Skip `resolved`/`fixed` findings. Skip `deferred` unless `--include-deferred`.
9. If no matches: suggest `--include-deferred`, `update`, or `--scope all` as appropriate.

### Phase 2: Plan Fixes (sub-agent)

Dispatch fix-planner sub-agent:

Use the Agent tool with:
- subagent_type: `codebase-notes:fix-planner`
- prompt: Include findings JSON (IDs, severities, statuses, file refs, descriptions), scope, current diff, and fix-plan template from `${CLAUDE_PLUGIN_ROOT}/skills/code-review/templates/fix-plan.md`

The planner returns a structured fix plan with: impact analysis (all files that must change, flag if >5 files outside review scope), clusters (findings touching overlapping code — same file within 20 lines, same function, shared impacted files), conflict detection (different personas recommending contradictory changes on same code), and ordering (dependencies first, build fixes first, critical first, isolated before coupled).

**Conflict resolution (orchestrator handles interactively):**
- 4+ conflicts: batch table with quick choices (A / B / defer)
- 1-3 conflicts: present each with full reasoning

Write `fix-plan.md` from planner output. Present plan summary to user for approval. Wait for confirmation.

### Phase 3: Execute Fixes (sub-agents, sequential)

16. Record anchor: `PRE_FIX_SHA=$(git rev-parse HEAD)`. Update fix-plan.md: `run-script review-frontmatter --path <fix-plan.md> --action update --set pre_fix_sha=$PRE_FIX_SHA --set status=in-progress`

17. For each cluster, dispatch fix-executor sub-agent:

Use the Agent tool with:
- subagent_type: `codebase-notes:fix-executor`
- prompt: Include cluster details (finding IDs, approach, files, verification commands) and changes from prior clusters

Each executor: validates targets still exist, reads current code, applies fixes, runs verification (linter + tests), commits per-cluster. Returns: status (pass/fail), files changed, verification output, commit SHA, issues.

**On failure:** Do NOT proceed. Ask user: (1) attempt to fix verification failure, (2) revert cluster and skip, (3) stop. If reverting: `git checkout -- <files>`.

18. Post-fix full verification: run linter + tests on all touched files across clusters.

19. **Squash into single commit** (anchored SHA):
    ```bash
    git reset --soft $PRE_FIX_SHA
    git commit -m "$(cat <<'EOF'
    fix: address code review findings from v<N> review

    Fixes applied:
    - <finding ID>: <summary>

    Deferred:
    - <finding ID> (severity): <reason>

    Review: <slug>/review.md
    EOF
    )"
    ```

### Phase 4: Update Review Documents

20. Update each finding's status in review.md (`fixed` with `**Fix:**` description, or `deferred` with `**Reason:**`)
21. Regenerate Fix Log: `run-script review-status --review-path <path> --action regenerate-fixlog`
22. Update fix-plan.md: `run-script review-frontmatter --path <fix-plan.md> --action update --set status=completed --set last_updated=YYYY-MM-DD`
23. Update review.md frontmatter: `run-script review-frontmatter --path <path> --action update --set last_updated=YYYY-MM-DD --set status=fixes-applied --set last_fix_sha=<SHA>`
24. Present fix summary with per-finding status table, commit SHA, deferred count. Suggest: push, then `update` for follow-up review.

---

## Subcommand: `list`

1. Run Step 0 to resolve repo ID and code-reviews path
2. List all subdirectories in `code-reviews/`
3. For each review directory, read `context.md` frontmatter for metadata and `review.md` frontmatter for version/status:
   ```bash
   run-script review-frontmatter --path <path_to_review.md> --action read
   ```
4. Present as table:
   ```
   | # | Identifier | Type | Base | Created | Status | Version |
   |---|-----------|------|------|---------|--------|---------|
   | 1 | pr-123 | PR | main | 2026-03-20 | reviewed | v1 |
   ```
5. If no reviews exist, suggest `/codebase-notes:code-review new "identifier"`

## Subcommand: `view`

1. Run Step 0 to resolve repo ID and code-reviews path
2. Resolve identifier to slug. Check both slug form and scan directory names for partial matches.
3. Read and display `context.md` — summarize onboarding context
4. Read and display `review.md`:
   - Show **Review History** table first (version audit trail)
   - Show **Summary** table (persona verdicts and counts)
   - Show **Fix Log** if any fixes have been applied
   - Offer to expand individual persona sections for detail
5. If review doesn't exist, suggest `/codebase-notes:code-review new`

---

## Subcommand: `loop`

Automated review→fix→update cycle. Runs until critical/suggestion findings converge or max cycles reached.

**Recommended: Use the bash orchestrator for multi-branch loops.** It spawns a fresh Claude session per phase (no context pressure):
```bash
${CLAUDE_PLUGIN_ROOT}/scripts/review-loop.sh --stack "feat/base-branch" --project "project-name"
${CLAUDE_PLUGIN_ROOT}/scripts/review-loop.sh --branches "feat/a feat/b" --max-cycles 3
${CLAUDE_PLUGIN_ROOT}/scripts/review-loop.sh --resume
${CLAUDE_PLUGIN_ROOT}/scripts/review-loop.sh --dry-run --stack "feat/base"
```

The bash script handles state, convergence detection, and rebase between branches. Each phase (review, fix, verify) gets a fresh context. Convergence is determined by the `review-status --action list-findings` script — NOT by LLM judgment.

For single-branch or in-session use, the inline flow below also works:

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"branch1" "branch2" ...` | Yes (unless `--stack`) | Branches to review in order |
| `--stack BASE` | No | Auto-discover stacked branches via `run-script review-stack --base <BASE>` |
| `--project NAME` | No | Project context.md only — routed to DE, SA, APT personas. Does NOT read other project files. |
| `--max-cycles N` | No | Max fix cycles per branch (default: 3) |
| `--auto-approve` | No | Skip fix-plan confirmation, auto-defer conflicts, auto-skip failed clusters |
| `--dry-run` | No | Preview branch list + existing findings without executing |
| `--resume` | No | Resume from `loop-state.json` |
| `--reset` | No | Delete existing `loop-state.json` and start fresh. Use when re-running after a completed loop. |

**Note:** Loop flags are passed via `--loop-args` when invoked programmatically.

### Flow

1. **Reset (if `--reset`):** Delete `loop-state.json` if it exists. This clears all prior loop state so the loop starts fresh. Without `--reset`, an existing `loop-state.json` with all branches converged will cause the loop to exit immediately with "nothing to do."

2. **Resolve branches:**
   - `--resume`: `run-script review-loop-state --review-dir <path> --action read`, skip branches with status `converged`, `stalled`, `hard-cap`, `clean`
   - `--stack`: `run-script review-stack --base <BASE>`, get ordered list. If multiple children at any level, present disambiguation.
   - Explicit list: use as provided
   - `--dry-run`: show branch table (see Dry-Run Output below), exit

3. **Initialize state:** `run-script review-loop-state --review-dir <path> --action write --branches '<json>' --args '<json>'`

3. **For each branch:**

   **Progress:** Announce `### Branch N/M: <name>`

   a. **Load context:**
      - If `--project`: read ONLY `~/.claude/repo_notes/<repo_id>/projects/<name>/context.md` for project context. Do NOT read other files in the project folder (research data, open questions, etc. will pollute context). Route to DE, SA, and APT personas only.
      - If stacked and parent completed: re-read parent's POST-FIX review.md for cross-branch context (summary + unresolved findings)

   b. **Review:** Check if `code-reviews/<slug>/` exists.
      - Exists → run `update` subcommand flow
      - New → run `new` subcommand flow (with `--base <parent>` if stacked)
      - **Per-persona progress:** Log each persona as it runs: `Review: running <Persona>... (N findings)`

   c. **Check findings:** `run-script review-status --review-path <path> --action list-findings`
      - Filter: severity in (critical, suggestion), status in (new, missed, regressed)
      - Zero → log "Branch clean", update state, skip to next

   d. **Fix cycle** (up to `--max-cycles`):
      Track `min_findings_seen` across cycles.

      **Step 1 — Fix:** Run `fix` flow (pass `--auto-approve` if set)
      - **Fix-failed check:** `git diff --stat` — if no changes, log "nothing to fix", exit cycle
      - **Per-cluster progress:** Log `Cluster K/M: pass` or `Cluster K/M: fail`

      **Step 2 — Re-review (MANDATORY):** Run `update` flow to verify fixes and detect new issues.
      - This is the VALIDATION step. Do NOT skip it. Do NOT check convergence before this runs.
      - The update re-runs all personas against the post-fix code.

      **Step 3 — Convergence check (ONLY after update completes):**
      - `run-script review-status --review-path <path> --action list-findings`
      - Count findings where status in (`new`, `missed`, `regressed`) AND severity in (`critical`, `suggestion`)
      - **Progress:** Log `Cycle N result: X new, Y resolved`
      - **Converged:** count = 0 → exit cycle, move to next branch
      - **Stalled:** count >= `min_findings_seen` → log "stalled at N findings", exit cycle
      - **Hard cap:** cycle = `--max-cycles` → log remaining, exit cycle
      - **Continue:** update `min_findings_seen = min(min_findings_seen, count)`, go to Step 1
      - Checkpoint: `run-script review-loop-state --action update-branch --branch <name> --status in-progress --cycles <N>`

   e. **Finalize branch:**
      - Update state: `run-script review-loop-state --action update-branch --branch <name> --status <converged|stalled|hard-cap|fix-failed|clean>`
      - Log remaining suggestions/nits

   f. **Rebase next branch** (stacked mode only):
      ```bash
      git fetch origin <current_branch>
      git rebase <current_branch> <next_branch>
      ```
      If conflict: `git rebase --abort`, log "Rebase of <next_branch> onto <current_branch> failed with conflicts. Skipping rebase — review will analyze pre-rebase code.", continue anyway.
      **Progress:** Announce `Rebasing next branch...`

   g. **Checkpoint after branch 1** (unless `--auto-approve`):
      "Branch 1/N complete: <name> (<cycles> cycles, <status>). Continue with remaining branches? (yes/stop)"

4. **Final summary:** Table with Branch | Cycles | Status | Critical | Suggestions | Nits columns, plus `Total: N branches, M converged, K stalled`.

### Exit Conditions

| Condition | Detection | Action |
|-----------|-----------|--------|
| **Converged** | Zero qualifying findings (status in new/missed/regressed, severity critical/suggestion) | Move to next branch |
| **Stalled** | Count >= minimum seen across all prior cycles (prevents oscillation) | Log "stalled at N findings", move on |
| **Hard cap** | Cycle count = `--max-cycles` | Log remaining, move on |
| **Fix failed** | `git diff --stat` shows no changes after fix | Log "nothing to fix", move on |
| **Clean** | Initial review has zero critical/suggestion findings | Skip fix cycles entirely |

### Dry-Run Output

When `--dry-run` is passed, resolve branches and print without executing:

```
## Dry Run: N branches

| Branch | Review Exists | Critical | Suggestions | Est. Cycles |
|--------|--------------|----------|-------------|-------------|
| feat/vertical-slice | yes (v2) | 1 | 3 | 1-2 |
| feat/eval-harness | no | — | — | 1-3 |

Estimated total cycles: 4-11
```

### Progress Protocol

Emit structured progress at each milestone. Format:

```
## Loop: N branches to review
### Branch 1/N: feat/vertical-slice
  Review: running Systems Architect... (3 findings)
  Review: running Domain Expert... (1 finding)
  Review: 7 findings total (2 critical, 4 suggestions, 1 nit)
  Fix cycle 1/3:
    Planning... 2 clusters, 0 conflicts
    Cluster 1/2: pass | Cluster 2/2: pass
    Committed: abc1234 | Updating review...
    Cycle 1 result: 1 new finding, 5 resolved
  Fix cycle 2/3:
    Cycle 2 result: 0 new findings → CONVERGED
  Remaining: 1 nit (not fixed)
  Rebasing next branch...
### Branch 2/N: ...
```

---

## Backward Compatibility: Pre-Versioned Reviews

When `update` or `fix` encounters review.md without `current_version`:

1. Treat as v1 — add: `current_version: 1`, `head_sha: ???????`, `merge_base_sha: ???????`, `last_fix_sha: null`
2. Assign finding IDs retroactively: `run-script review-status --review-path <path> --action assign-ids`
3. Add Review History table (v1 row, SHA as `???????`) and Fix Log placeholder
4. Proceed normally — first `update` falls back to full re-review (same as GC'd OLD_HEAD path)

Migration is in-place. Original content preserved; only structure added.

---

## Retroactive Setup

When this skill runs on a repo that already has codebase-notes but no `code-reviews/` directory, create it automatically in Step 0. No migration needed — the directory is simply added.

---

## Cross-Referencing Protocol

1. **Before context.md:** Read `notes/00-overview.md`. Grep `git_tracked_paths` across note frontmatter for changed files. Read matching notes.
2. **During review.md:** Each persona references relevant notes. Domain Expert especially draws on domain notes.
3. **After review.md:** Flag notes the change may make stale. Offer update via `/codebase-notes:update`.

This cross-referencing leverages accumulated codebase-notes knowledge for architecture- and domain-aware reviews.
