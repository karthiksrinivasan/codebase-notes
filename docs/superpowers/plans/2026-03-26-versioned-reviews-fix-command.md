# Versioned Progressive Reviews + Fix Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add versioned progressive reviews (with finding IDs, status tracking, squash detection, and missed-finding reasoning) and a `fix` subcommand (with fix-plan.md, conflict-aware execution, auto-commit, and review doc updates) to the code-review skill.

**Architecture:** The existing `update` subcommand becomes version-aware — each update creates a new version entry, computes a tree-content delta between the old and new head (rebase-proof), and classifies every finding by its lifecycle status. Frontmatter stays flat (current state only); the Review History table in the document body is the audit trail. The new `fix` subcommand reads all findings, groups them into non-conflicting fix clusters, writes a `fix-plan.md` for user approval, executes fixes cluster-by-cluster with per-cluster commits and verification, then squashes into a single commit. The fix log is regenerated from per-finding statuses (single source of truth).

**Tech Stack:** Python (deterministic review helpers in `scripts/code_review.py`), Bash (git, gh/glab CLI), Markdown (review artifacts).

---

## Review Notes (from multi-persona plan review)

Issues found and addressed during three-persona plan review (Systems Architect, Adversarial Path Tracer, Standards Compliance — 39 findings total, 12 critical):

1. **Dual source of truth (VRF-01, VRF-02)** — Frontmatter versions array + Review History table + Fix Log all tracked overlapping state. **Fix:** Flatten frontmatter to current-state-only keys. Review History table is the single audit trail. Fix Log is regenerated from per-finding `**Status:**` fields.
2. **State machine gap (VRF-03, SC-9, SC-10)** — `fixed`/`deferred` statuses not in classification table, status vocabularies collided. **Fix:** Complete state transition matrix covering all 7 statuses as prior states. Document-level and finding-level status enums separated.
3. **Deeply nested frontmatter (SC-4)** — Three levels deep broke codebase convention. **Fix:** Only flat keys in frontmatter (`current_version`, `head_sha`, `merge_base_sha`). Version history lives in the Review History table.
4. **Ancestry check too coarse (APT-1, APT-2, APT-3)** — Binary ancestor/not-ancestor conflated rebase, amend, squash, GC into one bucket. **Fix:** Tree-content comparison (`OLD_HEAD^{tree}` vs `NEW_HEAD^{tree}`) as primary delta mechanism. Ancestry check is metadata annotation only.
5. **No working tree pre-flight (APT-6, APT-13)** — Dirty tree could corrupt fixes or produce phantom findings. **Fix:** Mandatory `git status --porcelain` check before `fix` (hard block) and `update` (warning).
6. **No intermediate checkpoints (APT-4)** — Cluster interaction failures left all changes entangled. **Fix:** Commit per-cluster during execution, squash into single commit at the end.
7. **Duplicate frontmatter parser (SC-11)** — Plan proposed `_extract_frontmatter` but `parse_frontmatter` already exists in staleness.py. **Fix:** Reuse existing import.
8. **Fix commit not tracked (VRF-04)** — Next `update` couldn't distinguish fix changes from developer changes. **Fix:** Record `last_fix_sha` in frontmatter so `update` can diff from post-fix state.
9. **GC'd OLD_HEAD (APT-16)** — `git diff` would fail fatally if old ref was garbage-collected. **Fix:** Validate OLD_HEAD with `git cat-file -t` before using; fall back to full re-review.
10. **Delta diff includes base merges (SC-15)** — `git diff OLD_HEAD NEW_HEAD` includes merged-in base changes. **Fix:** Use tree-diff approach; document limitation for merge-based integrations.
11. **Scope naming collision (SC-1)** — `--scope suggestion` overloads severity name. **Fix:** Rename to `--scope default` (critical + suggestion), `--scope critical`, `--scope all`.
12. **List/view not updated (VRF-08, SC-13, SC-14)** — Subcommands don't show version info. **Fix:** Update `list` and `view` to include version and fix status.

Issues found during branch-vs-PR workflow review (DX Reviewer, Workflow Integrity — 23 findings total, 9 critical):

13. **Fix branch validation (DX-1, WI-2, WI-12)** — `fix` can commit to wrong branch or code you don't own. **Fix:** Pre-flight check: verify current branch matches `head_branch` from context.md. Hard block if mismatched.
14. **Anchored squash SHA (WI-9)** — `HEAD~N` squash is fragile, can squash wrong commits. **Fix:** Record `PRE_FIX_SHA` before Phase 3 begins, use `git reset --soft $PRE_FIX_SHA` for squash. Store in fix-plan.md for partial resumption.
15. **Identifier disambiguation (WI-1)** — Bare number `42` could match `pr-42` or branch `42`. **Fix:** If multiple slug matches found, present disambiguation prompt with metadata from context.md.
16. **PR lifecycle updates (WI-3)** — Merged/closed PR leaves review in stale status. **Fix:** On `update` when remote branch is gone, check PR state via forge CLI and update review status to `merged` or `abandoned`.
17. **Branch context gap (DX-3, WI-5)** — Branch mode lacks PR description for "Why This Change". **Fix:** Prompt user once for branch purpose if commit messages are insufficient. Check for existing PR via `gh pr list --head <branch>`.
18. **Base branch detection (WI-8)** — `git symbolic-ref` guesses wrong base for non-default-branch workflows. **Fix:** Add `--base` optional argument to `new` for explicit override.
19. **Deferred finding revisit (WI-11)** — No way to un-defer findings. **Fix:** Add `--include-deferred` flag to `fix`.

**Roadmap (future features, out of scope for this plan):**
- **Publish to PR (DX-10):** Post findings as PR review comments via `gh pr review`
- **PR comments in update (DX-8):** Incorporate author responses when re-reviewing
- **Branch-to-PR promotion (DX-7):** `link` subcommand to carry review history from branch to PR
- **Uncommitted changes for `new` (DX-2):** Warning when branch has uncommitted changes

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `scripts/code_review.py` | All review helper scripts: preflight, delta, finding status management, frontmatter ops |
| Modify | `scripts/__main__.py` | Register review-preflight, review-delta, review-status, review-frontmatter commands |
| Modify | `skills/code-review/SKILL.md` | Add versioned review logic, fix subcommand, referencing scripts for deterministic ops |
| Modify | `scripts/context_index.py` | Add version count and fix status to code-reviews table |

**Design principle:** Scripts handle deterministic operations (parsing, counting, validation, git analysis). The LLM agent handles judgment (classification reasoning, fix planning, code changes). This ensures state machine invariants hold regardless of which LLM runs the skill.

### Script Commands

| Command | Purpose | Output |
|---------|---------|--------|
| `review-preflight` | Pre-flight checks for update/fix | JSON: clean_tree, branch_match, old_head_valid, remote_exists, forge_cli, pr_state |
| `review-delta` | Tree-content delta analysis | JSON: tree_identical, history_rewritten, old_head_gc, merge_base_drift, changed_files |
| `review-status` | Finding management | Subcommands: assign-ids, validate-transition, regenerate-fixlog, regenerate-history-row, list-findings |
| `review-frontmatter` | Frontmatter read/update | JSON read, or in-place update with --set key=value |

---

### Task 1: Update review.md template with finding IDs and version-aware structure

**Files:**
- Modify: `skills/code-review/SKILL.md:239-473` (the review.md template in the `new` subcommand)

This task updates the review.md format to support versioning from day one. Every review created with `new` is v1.

- [ ] **Step 1: Read the current review.md template section**

Already read. The template starts at line 249 with the frontmatter and ends at line 473 with the summary table.

- [ ] **Step 2: Update frontmatter in review.md template**

Replace the current frontmatter block (lines 252-257) with flat, version-aware frontmatter. **No nested objects** — follows codebase convention of flat keys (addresses VRF-01, SC-4):

```yaml
---
identifier: <original identifier>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
status: reviewed
current_version: 1
head_sha: <short SHA of head at review time>
merge_base_sha: <short SHA of merge-base>
last_fix_sha: null
---
```

**Key design decisions:**
- `head_sha` / `merge_base_sha` track CURRENT version state only (updated on each `update`)
- `last_fix_sha` tracks the most recent fix commit (so `update` can diff from post-fix state, not pre-fix — addresses VRF-04)
- Version HISTORY lives in the Review History table in the document body (single source of truth for audit trail)
- No `findings_snapshot` in frontmatter — counts are computed from the Review History table

**Document-level status values** (hyphenated compounds — addresses SC-9):

| Status | Set by | Meaning |
|--------|--------|---------|
| `review-in-progress` | `new` (initial) | Review being written |
| `reviewed` | `new` (final) | Initial review complete |
| `review-updated` | `update` | Progressive review performed |
| `fixes-applied` | `fix` | Fixes committed, awaiting re-review |

- [ ] **Step 3: Add Review History section after the title**

Insert after `# Review: <title>` (line 258). This table is the **single source of truth** for version history (addresses VRF-01):

```markdown
## Review History

| Version | Date | Head SHA | Trigger | New | Resolved | Persists | Missed | Regressed |
|---------|------|----------|---------|-----|----------|----------|--------|-----------|
| v1 | YYYY-MM-DD | `abc1234` | new | <count> | — | — | — | — |

---
```

**Rules:**
- This table is the authoritative audit trail — never duplicate its data in frontmatter
- After modifying any version state, regenerate row counts from per-finding `**Status:**` fields
- The `Head SHA` column provides the linkage for delta diffs between versions

- [ ] **Step 4: Add finding ID format to each persona's Findings section**

Update each persona's Findings section to use stable IDs. The ID format is `<persona-prefix>-<number>`:

| Persona | Prefix |
|---------|--------|
| Senior Systems Architect | `SA` |
| Domain Expert | `DE` |
| Standards Compliance | `SC` |
| Adversarial Path Tracer | `APT` |
| Build & Runtime Verifier | `BRV` |

Each finding becomes a sub-heading with metadata:

```markdown
### Findings

#### SA-1 (critical) — Missing error propagation in `parse_config`
**File:** src/config.py:45-52
**Status:** new
<Description of the finding with specific details>

#### SA-2 (suggestion) — Consider extracting shared validation logic
**File:** src/validators.py:12, src/handlers.py:89
**Status:** new
<Description>
```

**Finding-level status values** (single words, separate vocabulary from document-level — addresses SC-9, SC-10):

| Status | Set by | Meaning |
|--------|--------|---------|
| `new` | `new`, `update` | First appearance |
| `persists` | `update` | Was found before, code not fixed yet |
| `resolved` | `update` | Previously found, no longer applies |
| `missed` | `update` | Found on code that existed in prior version — **requires reasoning** |
| `regressed` | `update` | Was resolved or fixed, came back |
| `fixed` | `fix` | Addressed by fix command |
| `deferred` | `fix` | User chose not to fix |

- [ ] **Step 5: Add Fix Log section before the Summary table**

Insert before `## Summary` (line 460). The Fix Log is a **regenerated view** — always rebuilt by scanning all per-finding `**Status:**` fields (addresses VRF-02):

```markdown
## Fix Log

_No fixes applied yet. Use `/codebase-notes:code-review fix "<identifier>"` to address findings._

<!--
After fixes are applied, regenerate this table from per-finding statuses:

| Finding | Severity | Status | Fix Summary | Applied In |
|---------|----------|--------|-------------|------------|
| SA-1 | critical | fixed | Added error propagation with typed exception | v2 |
| DE-2 | suggestion | deferred | Requires API change — user chose to defer | — |

IMPORTANT: The per-finding **Status:** field is the single source of truth.
This table is regenerated from those statuses — never edit it independently.
-->
```

- [ ] **Step 6: Record head_sha during `new` subcommand**

In the `new` subcommand flow (Step 2: Gather the Diff), add instruction to capture and store the head SHA:

After computing the merge base, also capture:
```bash
HEAD_SHA=$(git rev-parse --short <head>)
MERGE_BASE_SHA=$(git rev-parse --short $MERGE_BASE)
```

These values go into the flat frontmatter keys `head_sha` and `merge_base_sha`.

- [ ] **Step 7: Add complete state transition matrix**

Add this after the finding status table (addresses VRF-03). This is the **authoritative reference** for how `update` classifies findings when a prior status exists:

```markdown
### Finding Status Transitions

When `update` runs, each finding from the previous version must be reclassified. Use this matrix — the prior status (row) determines valid next statuses (columns):

| Prior Status → | new | persists | resolved | missed | regressed | fixed | deferred |
|----------------|-----|----------|----------|--------|-----------|-------|----------|
| `new` | — | ✓ if still present | ✓ if gone | — | — | — | — |
| `persists` | — | ✓ if still present | ✓ if gone | — | — | — | — |
| `resolved` | — | — | ✓ stays resolved | — | ✓ if reappears | — | — |
| `missed` | — | ✓ if still present | ✓ if gone | — | — | — | — |
| `regressed` | — | ✓ if still present | ✓ if gone | — | — | — | — |
| `fixed` | — | — | ✓ if still gone | — | ✓ if reappears | ✓ stays fixed | — |
| `deferred` | — | ✓ still present (preserve reason) | ✓ if gone | — | — | — | ✓ stays deferred |

**Key rules:**
- `fixed` → `regressed`: The fix didn't hold. Note "(was fixed in v<N>)" on the finding.
- `deferred` → `persists`: Finding still exists but was intentionally deferred. Preserve the deferred reason as a note.
- `deferred` → `resolved`: Code changed and the deferred issue went away naturally.
- Findings with status `new` or `missed` from the CURRENT version are newly discovered — they don't have a "prior status."
```

- [ ] **Step 8: Add finding matching heuristics**

Add after the state transition matrix (addresses VRF-06, APT-7, APT-8):

```markdown
### Finding Matching Across Versions

To determine if a finding from v(N) still exists in v(N+1), match using this priority:

1. **Exact file:line match** — same file, same or overlapping line range (within 10 lines of drift)
2. **Same function/class match** — same function or class name in a different file (code was moved). Use `git log --follow` or grep to trace renames.
3. **Semantic match** — same root cause described differently due to refactoring. Keep the original finding ID, update file references and description, mark as `persists (refactored)`.
4. **No match found** — if uncertain whether a new finding is related to a resolved one, classify as `new` and add a note: "Possibly related to resolved finding <ID>."

**Never** match solely by file:line — code moves. **Never** create a duplicate finding for the same root cause — update the existing one.
```

- [ ] **Step 9: Update `list` and `view` subcommands**

Update the `list` subcommand table format to include version info:

```markdown
| # | Identifier | Type | Base | Created | Status | Version |
|---|-----------|------|------|---------|--------|---------|
| 1 | pr-123 | PR | main | 2026-03-20 | reviewed | v1 |
| 2 | feat-new-agent | branch | main | 2026-03-25 | fixes-applied | v3 |
```

Update the `view` subcommand flow to show Review History and Fix Log summary alongside the existing summary table.

- [ ] **Step 10: Verify the template changes are self-consistent**

Read through the complete updated template. Confirm:
- Frontmatter is flat (no nested objects)
- Finding-level and document-level statuses use separate vocabularies
- State transition matrix covers all 7 finding statuses as prior states
- Fix Log is documented as a regenerated view
- Review History table has `Head SHA` column for delta diff linkage
- `list` and `view` show version info

- [ ] **Step 11: Commit**

```bash
git add skills/code-review/SKILL.md
git commit -m "feat: add finding IDs, version tracking, and fix log to review.md template"
```

---

### Task 2: Rewrite the `update` subcommand for progressive versioned review

**Files:**
- Modify: `skills/code-review/SKILL.md:547-582` (the `update` subcommand section)

This is the core of the versioned review feature. The `update` subcommand now creates a new version, computes tree-content deltas (rebase-proof), and classifies findings using the state transition matrix from Task 1.

- [ ] **Step 1: Read the current `update` subcommand**

Already read. It's lines 547-582 — a simple re-run of personas with optional `--focus`.

- [ ] **Step 2: Replace the `update` subcommand Flow section**

Replace lines 558-582 with the following expanded flow:

```markdown
### Flow

#### Pre-flight

1. Run Step 0 to resolve the repo ID and code-reviews path
2. Verify the review exists — if not, suggest `new`
3. **Working tree check** (addresses APT-13):

   ```bash
   git status --porcelain
   ```

   If any tracked files are modified, warn: "Your working tree has uncommitted changes. The review will analyze committed code only, but linter/test checks (Build & Runtime Verifier) will run against your working tree. Consider committing or stashing first for accurate results." Proceed after warning — this is not a hard block for `update` (unlike `fix`).

4. Read existing `review.md` — extract:
   - `current_version` (N)
   - `head_sha` (OLD_HEAD) from frontmatter
   - `last_fix_sha` from frontmatter (may be null)
   - All findings with their IDs and statuses

#### Fetch and Validate

5. Re-fetch and validate refs:

   ```bash
   git fetch origin <head_branch> 2>/dev/null || true
   ```

   **Validate remote branch exists** (addresses APT-14):
   ```bash
   git ls-remote origin <head_branch>
   ```
   If empty, error: "Remote branch `<head_branch>` no longer exists. The PR may have been merged or the branch deleted. If merged, no further review is needed. If renamed, create a new review with the new branch name."

   **Validate OLD_HEAD still exists** (addresses APT-16):
   ```bash
   git cat-file -t <OLD_HEAD> 2>/dev/null
   ```
   If this fails, OLD_HEAD has been garbage-collected (typically after force-push + 2 weeks). Skip delta diff, perform full re-review with message: "Previous review head `<OLD_HEAD>` has been garbage-collected. Performing full re-review."

   Compute new refs:
   ```bash
   NEW_HEAD_SHA=$(git rev-parse --short <head>)
   MERGE_BASE_SHA=$(git rev-parse --short $(git merge-base <base> <head>))
   ```

   **Determine diff base:** If `last_fix_sha` is set and valid (not null, passes `git cat-file -t`), use it instead of OLD_HEAD for the delta. This ensures fix-introduced changes are excluded from the delta (addresses VRF-04):
   ```
   DIFF_BASE = last_fix_sha if set and valid, else OLD_HEAD (head_sha)
   ```

#### Compute Delta (tree-content comparison)

6. **Tree-content delta** (addresses APT-1, APT-2, APT-3 — rebase-proof):

   Instead of checking commit ancestry (which conflates rebase, amend, squash, and GC), compare tree contents directly:

   ```bash
   # Compare tree objects — this works even after rebase/amend
   OLD_TREE=$(git rev-parse DIFF_BASE^{tree} 2>/dev/null)
   NEW_TREE=$(git rev-parse <NEW_HEAD>^{tree} 2>/dev/null)

   if [ "$OLD_TREE" = "$NEW_TREE" ]; then
     # Trees are identical — no code changes between versions
     echo "No code changes since last review. Nothing to update."
     exit 0
   fi

   # Delta diff: what changed in the tree content
   git diff $OLD_TREE $NEW_TREE --stat
   git diff $OLD_TREE $NEW_TREE
   ```

   **Detect history rewriting** (metadata annotation only, not a classification decision):
   ```bash
   git merge-base --is-ancestor DIFF_BASE <NEW_HEAD> 2>/dev/null
   REWRITTEN=$?  # 0 = linear history, non-zero = rewritten (rebase/squash/amend)
   ```

   If history was rewritten (`REWRITTEN != 0`):
   - Note in Review History: `update (history rewritten)` in the trigger column
   - Log: "Branch history was rewritten (rebase, amend, or squash) since last review. Using tree-content comparison for accurate delta."
   - **Do NOT nuke prior findings** — the tree diff provides accurate content changes regardless of history rewriting

   **If OLD_HEAD was garbage-collected** (from step 5):
   - Cannot compute tree diff — fall back to full re-review
   - Note in Review History: `update (full re-review — prior ref GC'd)`
   - Classify all findings as `new` (fresh start, no `missed` since we can't compare)

   **Full branch diff** (total scope, same as `new`):
   ```bash
   git diff $MERGE_BASE_SHA <NEW_HEAD> --stat
   git diff $MERGE_BASE_SHA <NEW_HEAD>
   ```

   Parse the tree delta to build a set of **changed file:line ranges** — these are the "new code" regions.

   **Note on base branch merges** (addresses SC-15): If the developer merged the base branch into their feature branch between reviews, the tree delta will include those changes. This is a known limitation of tree-content comparison. The delta may overcount "new code" regions, which means some findings that would be `missed` get classified as `new` instead — a safe direction to err.

   **Check merge-base drift** (addresses APT-15): Compare the current merge-base SHA with the one stored in frontmatter. If they differ, log: "Base branch has advanced (merge-base moved from `<old>` to `<new>`). Integration issues may have appeared." This triggers a full persona re-run even if `--focus` was specified.

7. **Re-run personas** (all five, or subset if `--focus` provided — same focus mapping table as before. If merge-base drifted, run all five regardless of `--focus`.)

   For each persona, review the full branch diff but with awareness of the delta. Each finding must be classified:

   **Classification rules:**

   | Finding in v(N+1) | Was in v(N)? | In tree delta? | Classification |
   |-------------------|-------------|----------------|----------------|
   | Yes | No | Yes | `new` — normal new finding on new code |
   | Yes | No | No | `missed` — **MUST include reasoning** |
   | Yes | Yes (same) | — | `persists` — not yet addressed |
   | No | Yes | — | `resolved` — finding no longer applies |
   | Yes | Yes (was resolved/fixed) | — | `regressed` — was resolved or fixed, came back |

   **For findings with prior status `fixed` or `deferred`, use the state transition matrix from Task 1 Step 7.**

   **Missed finding reasoning (MANDATORY for `missed` classification):**

   When a finding is on code that existed in the previous review version but wasn't flagged, append a `**Missed in v<N> because:**` line. Valid reasons:

   - "Cross-layer interaction: the new code in `<file>` made the coupling between `<A>` and `<B>` visible — this couldn't be traced without seeing both sides"
   - "Context expansion: domain notes on `<topic>` were read this time, revealing that `<assumption>` is incorrect"
   - "Pattern contrast: the new approach in `<file>` highlights that the old code in `<other_file>` has the same class of bug"
   - "Persona overlap: `<other persona>`'s finding `<ID>` in this version drew attention to this related issue"
   - "Genuine oversight: this should have been caught in v<N> — the code path was in scope and the issue is straightforward"

   Be honest. "Genuine oversight" is a valid reason and builds trust.

   **Use the finding matching heuristics from Task 1 Step 8** to determine if a finding "was in v(N)."

#### Update Documents

8. **Update finding statuses in review.md:**

   - Use the state transition matrix (Task 1 Step 7) for findings with prior statuses
   - New findings: add with next available ID and `**Status:** new` or `**Status:** missed`
   - Do NOT delete resolved findings — keep them with `resolved` status for audit trail
   - **Regenerate the Fix Log table** from per-finding statuses (the Fix Log is a view, not a source of truth)

9. **Update Review History table** (single source of truth for version audit):

   Add a new row:

   ```markdown
   | v<N+1> | YYYY-MM-DD | `<NEW_HEAD_SHA>` | update | <new_count> | <resolved_count> | <persists_count> | <missed_count> | <regressed_count> |
   ```

   If history was rewritten, the trigger column reads `update (history rewritten)`.
   If OLD_HEAD was GC'd, the trigger column reads `update (full re-review — prior ref GC'd)`.

   **Regenerate row counts** by scanning all per-finding `**Status:**` fields for this version — never hardcode counts.

10. **Update frontmatter** (flat keys only):

    ```yaml
    current_version: <N+1>
    last_updated: YYYY-MM-DD
    status: review-updated
    head_sha: <NEW_HEAD_SHA>
    merge_base_sha: <MERGE_BASE_SHA>
    # last_fix_sha stays unchanged (only fix command updates it)
    ```

11. **Update context.md** if the scope changed (new files, different summary)

12. **Present a version diff summary:**

    ```
    ## Review v1 → v2

    **Delta:** 3 files changed, 45 additions, 12 deletions (tree-content comparison)

    | Category | Count | Details |
    |----------|-------|---------|
    | New findings | 2 | APT-4 (critical), BRV-3 (suggestion) |
    | Resolved | 5 | SA-1, SA-2, DE-1, SC-1, APT-1 |
    | Persists | 1 | DE-2 (suggestion) |
    | Missed | 1 | APT-5 (critical) — cross-layer interaction |
    | Regressed | 0 | — |
    ```

    Offer: view full updated review, run fix command, view specific findings
```

- [ ] **Step 3: Update the focus mapping table**

Keep the existing focus mapping table (lines 565-575) but ensure it references all five personas. Also fix the existing bug at line 578 ("all four personas" → "all five personas" — addresses SC-2).

- [ ] **Step 4: Verify the classification rules are exhaustive**

Walk through edge cases using the state transition matrix:
- Finding on deleted code → `resolved` (code no longer exists)
- Finding on moved code (same logic, different file) → `persists` (match by semantic content per Task 1 Step 8)
- Finding that was `deferred` in fix log → `persists` (preserve deferred reason as note) per state transition matrix
- Finding that was `fixed` but reappears → `regressed` with note "(was fixed in v<N>)"
- Finding on code touched by a fix attempt that didn't fully resolve it → `regressed` if it was marked `fixed`, `persists` if it was never fixed
- Rebase without code change → tree diff is empty → "No code changes" early exit
- Amend with trivial change → small tree delta → normal delta-aware review
- Force-push with different code → tree delta shows real changes → accurate classification
- GC'd OLD_HEAD → full re-review, all findings classified as `new`

- [ ] **Step 5: Commit**

```bash
git add skills/code-review/SKILL.md
git commit -m "feat: rewrite update subcommand for progressive versioned reviews"
```

---

### Task 3: Add the `fix` subcommand

**Files:**
- Modify: `skills/code-review/SKILL.md` — add new subcommand section after `update`, update subcommands table, update storage structure

This is the second major feature. The `fix` subcommand reads findings, plans fixes, prompts for conflicts, executes, verifies, auto-commits, and updates review.md.

- [ ] **Step 1: Update the subcommands table**

Add `fix` to the table at lines 17-23:

```markdown
| Subcommand | Arguments | Description |
|------------|-----------|-------------|
| `new` | `"identifier"` (required) | Create a new review for a PR or branch |
| `list` | (none) | List all reviews for the current repo |
| `view` | `"identifier"` (required) | Read and display an existing review |
| `update` | `"identifier"` (required), `--focus AREA` | Re-run or amend a review with updated diff or focused area |
| `fix` | `"identifier"` (required), `--scope SCOPE` | Fix findings from the review and update review docs |
```

- [ ] **Step 2: Add fix example to the examples list**

Add after line 35:

```markdown
- `/codebase-notes:code-review fix "#42"` — fix critical+suggestion findings from PR #42's review (default scope)
- `/codebase-notes:code-review fix "#42" --scope critical` — fix only critical findings
- `/codebase-notes:code-review fix "#42" --scope all` — fix everything including nits
```

- [ ] **Step 3: Update storage structure**

Update the storage structure diagram (lines 42-47) to include fix-plan.md:

```markdown
## Storage Structure

```
~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/
├── context.md     # Onboarding context — prereqs, motivation, scope, architecture impact
├── review.md      # Multi-persona review — five specialist perspectives, versioned
└── fix-plan.md    # Fix execution plan — clusters, ordering, conflict resolution
```
```

- [ ] **Step 4: Write the full `fix` subcommand section**

Add after the `update` subcommand section (after line 582):

```markdown
---

## Subcommand: `fix`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"identifier"` | **Yes** | The review identifier |
| `--scope SCOPE` | No | Which severity threshold to fix (addresses SC-1 — avoids overloading severity names): `critical` (critical only), `default` (critical + suggestion, **the default**), `all` (everything including nits) |

### Flow

#### Phase 0: Pre-flight Checks

1. Run Step 0 to resolve the repo ID and code-reviews path
2. Verify the review exists — if not, suggest `new`
3. **Mandatory branch validation** (addresses DX-1, WI-2, WI-12 — HARD BLOCK):

   ```bash
   CURRENT_BRANCH=$(git branch --show-current)
   ```

   Read `head_branch` from `context.md` frontmatter. If `CURRENT_BRANCH` does not match `head_branch`, hard-block: "Fix targets branch `<head_branch>` but you are on `<CURRENT_BRANCH>`. Run `git checkout <head_branch>` first."

   **Do not proceed if branches don't match.** This prevents fixing code on the wrong branch (especially dangerous in PR mode where you might be on `main`).

4. **Mandatory working tree check** (addresses APT-6 — HARD BLOCK):

   ```bash
   git status --porcelain
   ```

   If ANY tracked files are modified or staged, error: "Working tree has uncommitted changes. Please commit or stash your changes before running fix. The fix command auto-commits and your in-progress work would be incorporated into the fix commit."

   **Do not proceed until the working tree is clean.**

5. **Check for existing fix-plan.md** (addresses VRF-07, APT-9):

   If `fix-plan.md` exists in the review directory:
   - Read its frontmatter: `review_version` and `status`
   - If `review_version` does not match `current_version` in review.md, the plan is stale: "A fix plan exists from a previous review version (v<old> vs current v<new>). Creating a new plan."
   - If `status` is `partial`, ask: "A partially completed fix plan exists. Resume it, or create a new one?"
   - If `status` is `planned`, ask: "An unapplied fix plan exists from YYYY-MM-DD. Resume it, or create a new one?"
   - If `status` is `completed`, proceed to create a new plan (previous fixes are done)

#### Phase 1: Gather and Analyze Findings

5. Read `review.md` — extract ALL findings across ALL versions with their:
   - Finding ID (e.g., `SA-1`, `APT-3`)
   - Severity (`critical`, `suggestion`, `nit`)
   - Status (`new`, `persists`, `missed`, `regressed` — skip `resolved` and `fixed`)
   - File and line references
   - Description
6. Filter by `--scope`:
   - `critical`: only `critical` severity
   - `default` (default): `critical` + `suggestion`
   - `all`: all severities including `nit`
7. Skip findings with status `resolved`, `fixed`, or `deferred`
8. If no findings match, report: "No actionable findings to fix at this scope." Suggest `/codebase-notes:code-review update "<identifier>"` to re-review for new findings, or `--scope all` if only nits remain.

#### Phase 2: Plan Fixes

9. **Impact analysis** (addresses APT-5 — discover ALL files that must change):

   For each finding, identify ALL files that must change — not just the file referenced in the finding:
   - If the fix involves renaming: grep for all usages across the codebase
   - If the fix changes a function signature: find all callers
   - If the fix changes a type: find all consumers
   - If the fix requires more than 5 files outside the original review scope, flag: "This fix has broad impact (N files beyond the review scope). Confirm before proceeding."

   Add all impacted files to the finding's file manifest.

10. **Group findings into fix clusters:**

    A fix cluster is a set of findings that touch overlapping code regions (same file within 20 lines of each other, or same function, or shared impacted files from step 9). Findings in a cluster MUST be fixed together because changing one affects the others.

    ```
    Cluster 1: [SA-1, APT-3] — both touch src/config.py:40-60
    Cluster 2: [DE-2] — isolated in src/domain/models.py:15 (+ 8 caller files)
    Cluster 3: [SC-1, SC-2] — both in src/handlers.py naming conventions
    Cluster 4: [BRV-1] — missing dependency in pyproject.toml
    ```

11. **Detect conflicts within and across clusters:**

    Structured conflict detection (addresses VRF-09): only check for conflicts between findings that (a) touch the same file:line range AND (b) come from different personas. Findings in different files are unlikely to conflict.

    A conflict exists when two findings recommend contradictory changes:
    - Persona A says "extract to helper" vs Persona B says "keep inline"
    - Persona A says "add validation" vs Persona B says "trust internal callers"
    - Persona A says "rename to X" vs Persona B says "rename to Y"

    **Batch conflict resolution** (addresses APT-11 — avoids decision fatigue):

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

12. **Determine fix ordering across clusters:**

    Order clusters by:
    1. **Dependencies first** — if Cluster A's fix changes a type/interface that Cluster B depends on, fix A first
    2. **Build/dependency fixes first** — BRV findings (missing deps, broken imports) before code changes
    3. **Critical severity first** within same priority level
    4. **Isolated clusters before coupled clusters** — less risk of cascading issues

13. **Write `fix-plan.md`:**

    Create `~/.claude/repo_notes/<repo_id>/code-reviews/<slug>/fix-plan.md`:

    ```markdown
    ---
    identifier: <original identifier>
    review_version: <current_version from review.md>
    created: YYYY-MM-DD
    last_updated: YYYY-MM-DD
    scope: default
    status: planned
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

    ### Cluster 1: Config error handling [SA-1, APT-3]
    **Files:** src/config.py:40-60
    **Impacted files:** src/main.py, src/cli.py (callers of parse_config)
    **Order:** 1 (no dependencies)
    **Approach:**
    - SA-1: Add typed exception for parse failures, propagate to callers
    - APT-3: Handle the None case at line 45 before accessing .value

    **Verification:**
    - Run the repo's configured linter on changed files
    - Run the repo's test runner on relevant test files

    ### Cluster 2: Domain model correction [DE-2]
    **Files:** src/domain/models.py:15
    **Impacted files:** src/api/endpoints.py, src/services/embedding.py, + 6 more (callers of normalize_embedding)
    **Order:** 2 (independent)
    **Approach:**
    - DE-2: Rename `normalize_embedding` to `unit_normalize_embedding` to reflect that magnitude is lost. Update all 8 caller files.

    **Verification:**
    - Run the repo's configured linter on all changed files
    - Run the repo's test runner on relevant test files
    - Grep for any remaining references to old name

    ### Deferred Findings

    | Finding | Severity | Reason |
    |---------|----------|--------|
    | SC-3 | nit | Out of scope (--scope default) |
    | DE-4 | suggestion | User deferred: "requires API migration, will handle in separate PR" |

    ## Execution Checklist

    - [ ] Cluster 1: Config error handling
    - [ ] Cluster 2: Domain model correction
    - [ ] Post-fix verification (full linter + test suite)
    - [ ] Squash commits
    - [ ] Update review.md with fix status
    ```

14. **Present fix plan to user for approval:**

    Show a summary:
    ```
    ## Fix Plan for PR #42

    **Scope:** critical + suggestion — 5 findings to fix
    **Clusters:** 3 (2 findings overlap in src/config.py)
    **Conflicts:** 1 resolved (SA-2 vs SC-1 — chose SA-2 per your input)
    **Deferred:** 2 (1 out of scope, 1 user-deferred)
    **Impact:** 14 files total (6 in review scope, 8 additional callers/consumers)

    Execution order:
    1. Cluster 1: Config error handling [SA-1, APT-3] — 4 files
    2. Cluster 2: Domain model correction [DE-2] — 9 files
    3. Cluster 3: Handler naming [SC-1] — 1 file

    Full plan saved to: fix-plan.md

    Proceed with fixes? (yes / review plan first / adjust)
    ```

    Wait for user confirmation before proceeding.

#### Phase 3: Execute Fixes

15. **Record pre-fix anchor** (addresses WI-9 — anchored SHA instead of fragile `HEAD~N`):

    ```bash
    PRE_FIX_SHA=$(git rev-parse HEAD)
    ```

    Store this in `fix-plan.md` frontmatter as `pre_fix_sha: <SHA>` so it survives partial plan resumption.

16. **Execute cluster by cluster with per-cluster commits** (addresses APT-4 — intermediate checkpoints for targeted rollback):

    For each cluster, in order:

    a. **Re-validate targets** (addresses APT-12): Before applying, verify that the code regions referenced in the fix plan still exist and match the expected state. If a previous cluster materially changed this cluster's target, pause and re-plan this cluster based on current code.
    b. Read the current state of all files in the cluster (including impacted files from step 9)
    c. Apply the fix — make the code changes
    d. Run the cluster's verification commands (repo's configured linter + relevant tests on touched files — addresses VRF-11, uses same detection as Build & Runtime Verifier)
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

16. **Post-fix full verification:**

    After all clusters are applied:

    ```bash
    # Run full linter on all touched files (using repo's configured linter)
    <repo_linter> <all_files_touched_across_clusters>

    # Run full test suite for affected areas (using repo's configured test runner)
    <repo_test_runner> <test_files_matching_touched_code>
    ```

    If this fails and per-cluster verification passed, the failure is likely from cluster interaction. Use per-cluster commits to identify which cluster combination caused it:
    ```bash
    # Check each cluster boundary
    git stash  # save current state
    git reset --soft HEAD~<N_clusters>  # go back to pre-fix state
    # Apply clusters one-by-one, testing after each, to find the breaking combination
    ```

18. **Squash into single commit** (uses anchored SHA from step 15 — addresses WI-9):

    After all verification passes, squash the per-cluster commits into one:

    ```bash
    git reset --soft $PRE_FIX_SHA
    git commit -m "$(cat <<'EOF'
    fix: address code review findings from v<N> review

    Fixes applied:
    - SA-1: Added error propagation in parse_config
    - APT-3: Added nil check before .value access
    - DE-2: Renamed normalize_embedding for clarity
    - SC-1: Updated handler naming to match conventions

    Deferred:
    - SC-3 (nit): out of scope
    - DE-4 (suggestion): requires API migration

    Review: <slug>/review.md
    EOF
    )"
    ```

#### Phase 4: Update Review Documents

19. **Update each finding's status in review.md:**

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

20. **Regenerate the Fix Log table** from per-finding statuses (addresses VRF-02 — Fix Log is a view, not a source of truth):

    Scan ALL findings in review.md. For each finding with status `fixed` or `deferred`, add a row:

    ```markdown
    ## Fix Log

    | Finding | Severity | Status | Fix Summary | Applied In |
    |---------|----------|--------|-------------|------------|
    | SA-1 | critical | fixed | Added error propagation with typed exception | v1→v2 |
    | APT-3 | critical | fixed | Added nil check before .value access | v1→v2 |
    | DE-2 | suggestion | fixed | Renamed to unit_normalize_embedding | v1→v2 |
    | SC-1 | suggestion | fixed | Updated handler naming conventions | v1→v2 |
    | SC-3 | nit | deferred | Out of scope (--scope default) | — |
    | DE-4 | suggestion | deferred | Requires API migration | — |
    ```

21. **Update fix-plan.md:**

    - Update frontmatter `status` to `completed` (or `partial` if some clusters failed/were skipped)
    - Update `last_updated`
    - Check off completed clusters in the Execution Checklist

22. **Update review.md frontmatter:**

    ```yaml
    last_updated: YYYY-MM-DD
    status: fixes-applied
    last_fix_sha: <short SHA of the squashed fix commit>
    # current_version stays unchanged — only update increments it
    ```

23. **Present fix summary:**

    ```
    ## Fixes Applied for PR #42

    | Finding | Status | Verification |
    |---------|--------|-------------|
    | SA-1 | fixed | linter pass, tests pass |
    | APT-3 | fixed | linter pass, tests pass |
    | DE-2 | fixed | linter pass, tests pass, 8 callers updated |
    | SC-1 | fixed | linter pass |

    **Committed:** `abc1234` — "fix: address code review findings from v1 review"
    **Deferred:** 2 findings (SC-3, DE-4)

    Next steps:
    - Push the commit and update the PR
    - Run `/codebase-notes:code-review update "#42"` for a follow-up review (v2)
    ```
```

- [ ] **Step 5: Verify fix subcommand handles edge cases**

Walk through these scenarios mentally:
- **No findings to fix**: All findings already resolved/fixed → report "Nothing to fix" and exit
- **All findings are nits with default scope**: Nothing matches → suggest `--scope all`
- **Single finding, no clusters needed**: Works as a single cluster of 1
- **Fix introduces a NEW issue** (e.g., fixing a type error creates an import error): Caught by per-cluster verification, stops execution, reports to user
- **Review has no versions yet** (created before versioning was added): Treat as v1, populate version info from frontmatter dates
- **fix-plan.md already exists**: Existing plan from a previous fix attempt. Ask user: "A fix plan already exists from YYYY-MM-DD. Resume that plan, or create a new one?"

- [ ] **Step 6: Commit**

```bash
git add skills/code-review/SKILL.md
git commit -m "feat: add fix subcommand for cohesive review finding resolution"
```

---

### Task 4: Update context_index.py to surface version info

**Files:**
- Modify: `scripts/context_index.py:158-174` (the `_build_code_reviews_table` function)

This is a small enhancement to show version count and fix status in the session priming index.

- [ ] **Step 1: Read the current function**

```python
def _build_code_reviews_table(section_dir: Path, repo_dir: Path) -> list[str]:
    """Build table rows for the code-reviews/ directory."""
    rows: list[str] = []
    for review_dir in sorted(section_dir.iterdir()):
        if not review_dir.is_dir():
            continue
        context_file = review_dir / "context.md"
        review_file = review_dir / "review.md"
        identifier = review_dir.name
        title = _extract_title(context_file) if context_file.is_file() else identifier
        has_review = "yes" if review_file.is_file() else "no"
        rel_context = context_file.relative_to(repo_dir) if context_file.is_file() else f"code-reviews/{identifier}/context.md"
        rows.append(f"| {rel_context} | {title} | {has_review} |")
    return rows
```

- [ ] **Step 2: Add version and fix status extraction**

Update the function to parse `current_version` and `status` from review.md frontmatter. **Reuse existing `parse_frontmatter`** from `scripts.staleness` which is already imported in context_index.py (addresses SC-11 — no duplicate parser):

```python
def _build_code_reviews_table(section_dir: Path, repo_dir: Path) -> list[str]:
    """Build table rows for the code-reviews/ directory."""
    rows: list[str] = []
    for review_dir in sorted(section_dir.iterdir()):
        if not review_dir.is_dir():
            continue
        context_file = review_dir / "context.md"
        review_file = review_dir / "review.md"
        identifier = review_dir.name
        title = _extract_title(context_file) if context_file.is_file() else identifier
        has_review = "yes" if review_file.is_file() else "no"
        version = "\u2014"
        status = "\u2014"
        if review_file.is_file():
            fm = parse_frontmatter(review_file)
            if fm:
                version = f"v{fm.get('current_version', '1')}"
                status = fm.get("status", "\u2014")
        rel_context = context_file.relative_to(repo_dir) if context_file.is_file() else f"code-reviews/{identifier}/context.md"
        rows.append(f"| {rel_context} | {title} | {has_review} | {version} | {status} |")
    return rows
```

Note: uses `\u2014` (em dash) for missing values, matching the pattern used in `_build_notes_table` (addresses SC-12).

- [ ] **Step 3: Update the table header in `_generate_index`**

Update the code-reviews section header (around line 240):

```python
    if code_reviews_dir.is_dir():
        rows = _build_code_reviews_table(code_reviews_dir, repo_dir)
        if rows:
            parts.append("## code-reviews/")
            parts.append("| Path | Title | Reviewed | Version | Status |")
            parts.append("|------|-------|----------|---------|--------|")
            parts.extend(rows)
            parts.append("")
```

- [ ] **Step 4: Verify `parse_frontmatter` is already imported**

Check that `context_index.py` already imports `parse_frontmatter` from `scripts.staleness`. If not, add the import. Do NOT create a new `_extract_frontmatter` helper — reuse the existing one.

- [ ] **Step 5: Verify the context index output**

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd /Users/karthik/Documents/work/codebase-notes/scripts && uv run python -m scripts context-index
```

Confirm code-reviews section now shows Version and Status columns.

- [ ] **Step 6: Commit**

```bash
git add scripts/context_index.py
git commit -m "feat: surface review version and status in session context index"
```

---

### Task 5: Handle backward compatibility with pre-versioned reviews

**Files:**
- Modify: `skills/code-review/SKILL.md` — add a backward compatibility note in the `update` and `fix` subcommands

Reviews created before this change won't have `current_version`, `versions`, or finding IDs in their review.md.

- [ ] **Step 1: Add backward compatibility section**

Add after the `update` subcommand flow, before the `fix` subcommand:

```markdown
### Backward Compatibility: Pre-Versioned Reviews

When `update` or `fix` encounters a review.md without version tracking (no `current_version` in frontmatter):

1. **Treat it as v1** — add flat version keys to frontmatter:
   - `current_version: 1`
   - `head_sha: ???????` (unknown — cannot compute delta for first update)
   - `merge_base_sha: ???????`
   - `last_fix_sha: null`
2. **Assign finding IDs retroactively** — scan existing findings and assign IDs using the persona prefix scheme (SA-1, DE-1, etc.). Set all statuses to `new`.
3. **Add the Review History table** (with v1 row, head SHA as `???????`) and Fix Log placeholder section
4. **Proceed normally** with the update or fix flow. Since `head_sha` is unknown, the first `update` after migration will fall back to full re-review (same as GC'd OLD_HEAD path).

This migration happens in-place — the review.md is rewritten with the new structure. The original content is preserved; only structure is added.
```

- [ ] **Step 2: Commit**

```bash
git add skills/code-review/SKILL.md
git commit -m "feat: add backward compatibility for pre-versioned reviews"
```

---

### Task 6: Branch-vs-PR workflow improvements

**Files:**
- Modify: `skills/code-review/SKILL.md` — update `new`, `update`, `fix`, and identifier resolution

These are targeted improvements from the branch-vs-PR workflow review that address real usage gaps.

- [ ] **Step 1: Add `--base` argument to `new` subcommand (addresses WI-8)**

Update the `new` Arguments table to include:

```markdown
| `--base BRANCH` | No | Override base branch detection (default: auto-detect from PR metadata or `git symbolic-ref`) |
```

In Step 1 (Resolve the Identifier), after "Determine the base branch," add:

```markdown
If `--base` was provided, use it instead of auto-detection. This is important for branches that diverged from non-default branches (e.g., `feat/x` branched from `develop`, not `main`).
```

Update examples:
```markdown
- `/codebase-notes:code-review new "feat/new-agent" --base "develop"` — review branch against develop
```

- [ ] **Step 2: Add `--include-deferred` flag to `fix` subcommand (addresses WI-11)**

Update the `fix` Arguments table:

```markdown
| `--include-deferred` | No | Re-include previously deferred findings in the fix plan |
```

In Phase 1 step 7, change from:
"Skip findings with status `resolved`, `fixed`, or `deferred`"
to:
"Skip findings with status `resolved` or `fixed`. Also skip `deferred` unless `--include-deferred` is set."

In Phase 1 step 8, when no findings match and deferred findings exist:
"No actionable findings to fix at this scope. N findings were previously deferred. Run with `--include-deferred` to revisit them."

- [ ] **Step 3: Add identifier disambiguation (addresses WI-1)**

Update the Identifier Slug Resolution section to add disambiguation rules:

```markdown
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
```

- [ ] **Step 4: Add PR lifecycle detection to `update` (addresses WI-3)**

In the `update` flow, after the remote branch validation (step 5), add:

```markdown
**If remote branch is gone and identifier is a PR/MR:**

Check PR state via forge CLI:
```bash
gh pr view <number> --json state
# or: glab mr view <number> --output json
```

| PR State | Action |
|----------|--------|
| `MERGED` | Update review.md status to `merged`, add final Review History row with trigger `merged`, report: "PR #N has been merged. Review is complete." |
| `CLOSED` | Update review.md status to `abandoned`, report: "PR #N was closed without merging." |
| (unknown) | Error with current message about branch deletion |

This ensures `list` shows accurate lifecycle state for completed PRs.
```

- [ ] **Step 5: Add branch context gathering to `new` (addresses DX-3, WI-5)**

In the `new` flow, Step 3 (Gather Cross-Reference Context), add for branch-mode reviews:

```markdown
**Branch-mode context enrichment** (when no PR metadata is available):

1. Read full commit bodies (not just oneline): `git log --format="%B" $MERGE_BASE..<head>`
2. Check if a PR already exists for this branch: `gh pr list --head <branch> --json number,title,body --limit 1`
   - If found, pull its metadata and use it as if this were a PR review
3. If commit messages are insufficient (all single-line, no descriptive bodies), prompt the user: "No PR description available. What is this branch trying to accomplish? (one sentence, or press Enter to skip)"
4. Store the user's response in context.md under "Why This Change"
```

- [ ] **Step 6: Commit**

```bash
git add skills/code-review/SKILL.md
git commit -m "feat: add branch-vs-PR workflow improvements (--base, --include-deferred, disambiguation, PR lifecycle)"
```

---

### Task 7: Integration test — full versioned review cycle

**Files:**
- No file changes — this is a validation task

- [ ] **Step 1: Create a fresh review**

From a repo with an active branch/PR:
```
/codebase-notes:code-review new "<identifier>"
```

Verify:
- review.md has `current_version: 1`, `head_sha`, `merge_base_sha` (flat keys, no nested objects)
- All findings have IDs (SA-1, DE-1, etc.) and `**Status:** new`
- Review History table has one row with Head SHA
- Fix Log shows placeholder
- Finding-level statuses are single words; document-level status is hyphenated

- [ ] **Step 2: Make some code changes and run update**

Push a commit to the branch, then:
```
/codebase-notes:code-review update "<identifier>"
```

Verify:
- `current_version` incremented to 2
- `head_sha` and `merge_base_sha` updated to new values
- Findings classified correctly using state transition matrix (new, persists, resolved)
- Any missed findings have reasoning with specific `**Missed in v1 because:**` line
- Review History table has two rows with counts regenerated from per-finding statuses
- Tree-content delta was used (check for "tree-content comparison" in output)

- [ ] **Step 3: Run fix command**

```
/codebase-notes:code-review fix "<identifier>"
```

Verify:
- Branch validation passed (current branch matches head_branch)
- Working tree was clean
- fix-plan.md created with clusters, ordering, and `pre_fix_sha`
- User prompted for any conflicts (batch mode if 4+)
- Fixes applied and verified per-cluster with intermediate commits
- Per-cluster commits squashed into single commit using anchored SHA
- review.md updated with fix status on each finding
- Fix Log table regenerated from per-finding statuses
- `last_fix_sha` set in review.md frontmatter

- [ ] **Step 4: Run follow-up update**

```
/codebase-notes:code-review update "<identifier>"
```

Verify:
- v3 review diffs from `last_fix_sha` (not old `head_sha`)
- Fixed findings show as `resolved` per state transition matrix
- Fix Log provides context for the review
- Any new issues from the fixes are caught
- `regressed` classification works if a fix didn't hold

- [ ] **Step 5: Test tree-content delta with rebase**

Rebase the branch onto updated main:
```bash
git rebase main
```
Then run update:
```
/codebase-notes:code-review update "<identifier>"
```

Verify:
- Tree-content comparison works despite history rewrite
- Review History notes "history rewritten" as metadata annotation
- Findings are NOT nuked — delta is computed from tree content
- If tree content is identical after rebase, early exit with "No code changes"

- [ ] **Step 6: Test PR lifecycle (if PR mode)**

If testing with a PR, merge it and run:
```
/codebase-notes:code-review update "<identifier>"
```

Verify:
- Remote branch detected as gone
- PR state queried via forge CLI
- Review status updated to `merged`
- Final row added to Review History
