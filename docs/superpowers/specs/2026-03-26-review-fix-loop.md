# Review-Fix Loop Subcommand Spec

**Date:** 2026-03-26
**Status:** Approved
**Goal:** Add a `loop` subcommand that automates the review→fix→update cycle until critical/high findings are resolved, with explicit branch lists and stacked branch auto-discovery.

---

## Review Notes

Issues addressed from multi-persona spec review (21 findings: 6 critical, 6 high, 6 medium, 3 low):

1. **WI-1/DX-3: Interactive prompts block automation** — Added `--auto-approve` mode: skip plan confirmation, auto-defer conflicting findings, auto-skip failed clusters.
2. **WI-4: No rebase between stacked branches** — Added rebase step after parent fix cycle. Abort on conflict, log, move on.
3. **SF-1: Forge URL parsing fails for self-hosted** — Parse hostname explicitly, handle SSH/HTTPS, share via `_detect_forge()`.
4. **SF-2: No cycle detection in stack discovery** — Added visited set + depth cap (20).
5. **DX-1: ~$50-130 per stack, no guardrails** — Added `--dry-run` flag and checkpoint after first branch.
6. **DX-2: 3-5 hour wall-clock** — Acknowledged as batch job, added resume via `loop-state.json`.
7. **WI-2: Convergence ignores `regressed`** — Added `regressed` to convergence check.
8. **WI-3: Stall detection defeated by oscillation** — Compare against minimum-ever count, not just last cycle.
9. **WI-7/WI-8: No resume; `new` vs `update` wrong on retry** — `loop-state.json` tracks progress. Use `update` if review exists.
10. **DX-4: No progress feedback** — Defined progress protocol with branch/cycle/persona announcements.
11. **WI-10: Cross-branch context stale after fixes** — Re-read parent review after fix cycle completes.
12. **DX-7: Project context to all personas** — Route to Domain Expert + Systems Architect only.
13. **DX-8/WI-3: Max cycles too high** — Default `--max-cycles` to 3.
14. **DX-9: Abandoned coordinator design** — Removed.
15. **SF-7: Duplicate forge detection** — `run_preflight` calls `_detect_forge()` internally.
16. **SF-4: PR/MR state filtering** — Added `--state open` filter; return all children for disambiguation.
17. **SF-6: Unauthenticated CLI** — Auth check after `shutil.which`; fall back to git topology on auth failure.

---

## Modes

### Mode A: Explicit Branch List

```bash
/codebase-notes:code-review loop "feat/auth" "feat/api" "feat/db" [--project "projects/auth-refactor"]
```

Reviews each branch in order. No stack relationship assumed.

### Mode C: Stacked Branches

```bash
/codebase-notes:code-review loop --stack "feat/composition-embeddings-vertical-slice" [--project "projects/composition-embeddings"]
```

Starts at base, auto-discovers chain, reviews each layer in order. Each branch's review gets post-fix context from the previous branch.

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"branch1" "branch2" ...` | Yes (unless `--stack`) | Branches to review in order |
| `--stack BASE` | No | Auto-discover stacked branches from base |
| `--project NAME` | No | Project notes for domain context (routed to DE + SA personas only) |
| `--max-cycles N` | No | Max fix cycles per branch (default: **3**) |
| `--auto-approve` | No | Skip fix-plan confirmation, auto-defer conflicts, auto-skip failed clusters |
| `--dry-run` | No | Preview branch list + existing findings without running reviews |
| `--resume` | No | Resume from last incomplete branch (reads `loop-state.json`) |

---

## Loop Behavior Per Branch

```
For each branch:
  1. Load project context (if --project, route to DE + SA only)
  2. Load parent branch's POST-FIX review summary (if stacked)
  3. If review exists for this branch: run UPDATE flow
     If no review exists: run NEW flow [--base <parent> if stacked]
  4. Check findings: any critical/suggestion severity?
     - No → log "clean", move to next branch
     - Yes → enter fix cycle
  5. Fix cycle (max --max-cycles, default 3):
     a. Run FIX flow (with --auto-approve if set)
     b. Run UPDATE flow
     c. Convergence check (see below)
     d. Write loop-state.json checkpoint
  6. Log remaining suggestions/nits
  7. If stacked: rebase next branch onto this branch's tip
  8. Move to next branch
```

### Idempotency Rule (WI-8)

The loop NEVER unconditionally calls `new`. Before reviewing each branch:
- Check if `code-reviews/<slug>/` exists
- If yes → use `update` flow (preserves version history)
- If no → use `new` flow

This makes the loop safely re-runnable and resumable.

### Auto-Approve Mode (WI-1/DX-3)

When `--auto-approve` is set, the fix subcommand runs without user interaction:
- **Fix-plan approval**: auto-approved (no "Proceed?" prompt)
- **Conflict resolution**: auto-defer all conflicting findings (both sides deferred with reason "auto-deferred: conflict in automated loop")
- **Cluster verification failure**: auto-skip failed clusters (revert and continue)
- **No findings to fix**: silently move to next cycle

Without `--auto-approve`, the loop pauses for user input at each interaction point (semi-attended mode).

### Convergence Check (WI-2, WI-3)

After each update cycle, count findings where:
- Status is `new`, `missed`, or `regressed` (not just new/missed — WI-2 fix)
- Severity is `critical` or `suggestion`

**Exit conditions:**

| Condition | Detection | Action |
|-----------|-----------|--------|
| **Converged** | Zero qualifying findings | Move to next branch |
| **Stalled** | Current count ≥ minimum count seen across all cycles (WI-3 fix) | Log "stalled at N findings", move on |
| **Hard cap** | Cycle count = `--max-cycles` | Log remaining, move on |
| **Fix failed** | Fix command produces no changes | Log "nothing to fix", move on |
| **Clean** | Initial review has zero critical/suggestion | Skip fix cycles entirely |

### Rebase Between Stacked Branches (WI-4)

After completing branch N's full loop (review + fix cycles), before moving to branch N+1:

```bash
git fetch origin <branch_N>
git rebase <branch_N> <branch_N+1>
```

**If rebase conflicts:**
- Abort: `git rebase --abort`
- Log: "Rebase of <branch_N+1> onto <branch_N> failed with conflicts. Skipping rebase — review will analyze pre-rebase code."
- Continue with the review anyway (findings may include false positives from stale base)

### Cross-Branch Context (WI-10)

Context from parent branch is gathered **after** the parent's full loop completes (post-fix), not after just the initial review. This ensures the child branch sees the resolved state:

```markdown
## Context from Parent Branch Review (post-fix)

Parent: feat/vertical-slice (v2, fixes-applied)

### Summary
| Persona | Verdict | Critical | Suggestions |
...

### Remaining Unresolved Findings
<only findings still persisting/deferred after fixes>

Check: Does this branch inherit unresolved parent issues?
```

---

## Progress Protocol (DX-4)

The loop emits structured progress at each milestone:

```
## Loop: 4 branches to review

### Branch 1/4: feat/vertical-slice
  Review: running Systems Architect... (3 findings)
  Review: running Domain Expert... (1 finding)
  Review: running Standards Compliance... (0 findings)
  Review: running Adversarial Path Tracer... (2 findings)
  Review: dispatching Build & Runtime Verifier...
  Review: BRV complete (1 finding)
  Review: 7 findings total (2 critical, 4 suggestions, 1 nit)

  Fix cycle 1/3:
    Planning... 2 clusters, 0 conflicts
    Cluster 1/2: pass ✓
    Cluster 2/2: pass ✓
    Committed: abc1234
    Updating review...
    Cycle 1 result: 1 new finding (suggestion), 5 resolved

  Fix cycle 2/3:
    Planning... 1 cluster
    Cluster 1/1: pass ✓
    Committed: def5678
    Updating review...
    Cycle 2 result: 0 new findings → CONVERGED

  Remaining: 1 nit (not fixed)
  Rebasing next branch...

### Branch 2/4: feat/eval-harness
  ...
```

---

## Resume Capability (WI-7, DX-5)

### `loop-state.json`

Written to `~/.claude/repo_notes/<repo_id>/code-reviews/loop-state.json` after each branch completes:

```json
{
  "started": "2026-03-26T10:30:00Z",
  "branches": [
    {"branch": "feat/vertical-slice", "status": "converged", "cycles": 2},
    {"branch": "feat/eval-harness", "status": "in-progress", "cycles": 1},
    {"branch": "feat/visualization", "status": "pending"},
    {"branch": "feat/wire-consumers", "status": "pending"}
  ],
  "current_branch_index": 1,
  "current_cycle": 1,
  "args": {
    "stack": "feat/vertical-slice",
    "project": "projects/composition-embeddings",
    "max_cycles": 3,
    "auto_approve": true
  }
}
```

### Resume Flow

When `--resume` is passed:
1. Read `loop-state.json`
2. Skip branches with status `converged`, `stalled`, `hard-cap`, `clean`
3. Resume from the first branch with status `in-progress` or `pending`
4. For `in-progress` branches: use `update` flow (review already exists)

### Dry Run (DX-1)

When `--dry-run` is passed:
1. Resolve branch list (discover stack if `--stack`)
2. For each branch, check if a review exists and count current findings
3. Print summary without executing any reviews:

```
## Dry Run: 4 branches

| Branch | Review Exists | Critical | Suggestions | Est. Cycles |
|--------|--------------|----------|-------------|-------------|
| feat/vertical-slice | yes (v2) | 1 | 3 | 1-2 |
| feat/eval-harness | no | — | — | 1-3 |
| feat/visualization | no | — | — | 1-3 |
| feat/wire-consumers | no | — | — | 1-3 |

Estimated total cycles: 4-11
```

### Checkpoint After First Branch (DX-1)

After the first branch completes (unless `--auto-approve`), pause and report:

```
Branch 1/4 complete: feat/vertical-slice (2 cycles, converged)
Continue with remaining 3 branches? (yes / stop)
```

---

## Stack Discovery

### New Script: `review-stack`

```bash
run-script review-stack --base "feat/vertical-slice"
```

Returns ordered JSON:
```json
{
  "base": "feat/composition-embeddings-vertical-slice",
  "stack": [
    {"branch": "feat/composition-embeddings-vertical-slice", "pr": 1987, "base": "main"},
    {"branch": "feat/composition-embeddings-eval-harness", "pr": 1988, "base": "feat/composition-embeddings-vertical-slice"},
    {"branch": "feat/composition-embeddings-visualization", "pr": 1989, "base": "feat/composition-embeddings-eval-harness"},
    {"branch": "feat/composition-embeddings-wire-consumers-v2", "pr": 2003, "base": "feat/composition-embeddings-visualization"}
  ],
  "method": "pr_chain",
  "forge": "gitlab",
  "warnings": []
}
```

### Discovery Algorithm (SF-2, SF-4)

1. **Detect forge** via `_detect_forge()` (shared function — see below)
2. **Try PR/MR chain first** (if CLI available and authenticated):
   - GitHub: `gh pr list --base <branch> --json number,headRefName --state open`
   - GitLab: `glab mr list --target-branch <branch> -F json` → filter for non-merged/closed MRs
   - Extract child branch name and PR/MR number
   - **Cycle detection:** maintain `visited: set[str]`. If child already in visited, warn and stop recursion.
   - **Depth cap:** max 20 levels. If exceeded, warn and stop.
   - If branch has **multiple children**: return all in the JSON (orchestrator handles disambiguation)
   - Recurse: each child becomes new base
3. **If no CLI or auth fails**, fall back to **git topology**:
   - Pre-compute all branch tips via `git for-each-ref --format='%(refname:short) %(objectname:short)' refs/heads/` (single subprocess)
   - For each candidate: check `git merge-base --is-ancestor <base_tip> <candidate_tip>`
   - **Direct children filter:** candidate is direct child if it's a descendant of base AND no other descendant of base is an ancestor of the candidate
   - Same cycle detection and depth cap as PR chain
   - **Performance:** warn if >100 candidate branches; suggest installing forge CLI
4. **Return** ordered list with method used and any warnings

### Field Mapping (SF-4)

| Field | GitHub (`gh`) | GitLab (`glab`) |
|-------|-------------|---------------|
| Child branch | `headRefName` | `source_branch` |
| PR/MR number | `number` | `iid` |
| Base branch | `baseRefName` | `target_branch` |
| State | `state` (OPEN/MERGED/CLOSED) | `state` (opened/merged/closed) |

Filter: only include items where state is `OPEN` (GitHub) or `opened` (GitLab).

---

## Forge Detection

### Shared Function: `_detect_forge()` (SF-1, SF-7)

Internal function in `code_review.py` used by both `run_forge` and `run_preflight`:

```python
def _detect_forge(remote_url: str) -> dict:
    """Parse remote URL to detect forge type. Handles SSH and HTTPS, self-hosted instances."""
```

**Hostname parsing logic (SF-1):**
1. Normalize URL: handle both `git@host:org/repo.git` (SSH) and `https://host/org/repo.git` (HTTPS)
2. Extract hostname
3. Match rules (in order):
   - Hostname ends with `github.com` → forge=github, cli=gh
   - Hostname ends with `gitlab.com` → forge=gitlab, cli=glab
   - Hostname contains `github` → forge=github, cli=gh (self-hosted GitHub Enterprise)
   - Hostname contains `gitlab` → forge=gitlab, cli=glab (self-hosted GitLab)
   - Check if `.gitlab-ci.yml` exists in repo root → forge=gitlab, cli=glab
   - Otherwise → forge=unknown, cli=null

**CLI availability + auth check (SF-6):**
1. `shutil.which(cli)` → `cli_available: bool`
2. If available, run auth check:
   - GitHub: `gh auth status` (exit 0 = authenticated)
   - GitLab: `glab auth status` (exit 0 = authenticated)
3. `cli_authenticated: bool`
4. If available but not authenticated → `cli_usable: false`, fall back to git topology

### `run_forge(args)` Entry Point

```bash
run-script review-forge [--remote REMOTE]
```

**Input:** Optional `--remote` (default: `origin`)
**Output:**
```json
{
  "forge": "gitlab",
  "cli": "glab",
  "cli_available": true,
  "cli_authenticated": true,
  "cli_usable": true,
  "remote_url": "git@gitlab.com:radical-ai/arc.git",
  "hostname": "gitlab.com"
}
```

---

## Project Context Integration (DX-7)

The `--project` flag loads project notes. Context is routed **only to Domain Expert and Systems Architect** personas (not all 5 — DX-7 fix):

1. Read `~/.claude/repo_notes/<repo_id>/projects/<name>/index.md`
2. Pass to DE persona: project goals, domain constraints, open questions
3. Pass to SA persona: architecture decisions, design patterns, integration points
4. SC, APT, BRV: do NOT receive project context (irrelevant to their focus)
5. Each review's context.md links to project notes under "Pre-requisites"

If `--project` points to a nonexistent or empty directory, warn and continue without project context.

---

## New Script Commands

### `review-forge`

Added to `scripts/code_review.py` as `run_forge(args)`.

**Args:** `--remote REMOTE` (default: origin)
**Output:** JSON with forge, cli, cli_available, cli_authenticated, cli_usable, remote_url, hostname
**Logic:** Calls `_detect_forge()` shared function. See Forge Detection section above.

### `review-stack`

Added to `scripts/code_review.py` as `run_stack(args)`.

**Args:** `--base BRANCH`
**Output:** JSON with ordered stack array, method, forge, warnings
**Logic:**
1. Call `_detect_forge()` internally
2. If `cli_usable`: PR/MR chain with cycle detection + depth cap
3. Else: git topology with pre-computed refs + direct child filter
4. Return ordered list with warnings for cycles, depth cap, multiple children, performance

### `review-loop-state`

Added to `scripts/code_review.py` as `run_loop_state(args)`.

**Args:** `--review-dir PATH`, `--action ACTION` (read | write | update-branch)
**Additional for write:** `--branches JSON` (initial branch list), `--args JSON` (loop arguments)
**Additional for update-branch:** `--branch NAME`, `--status STATUS`, `--cycles N`
**Output:** JSON of current state (for read), or confirmation (for write/update)

This script manages `loop-state.json` deterministically — the SKILL.md orchestrator doesn't manually edit JSON.

### Registration in `__main__.py`

```python
# review-forge
forge_parser = subparsers.add_parser("review-forge", help="Detect git forge and CLI availability")
forge_parser.add_argument("--remote", default="origin", help="Git remote name")

# review-stack
stack_parser = subparsers.add_parser("review-stack", help="Discover stacked branch chain")
stack_parser.add_argument("--base", required=True, help="Base branch of the stack")

# review-loop-state
loop_state_parser = subparsers.add_parser("review-loop-state", help="Manage loop state file")
loop_state_parser.add_argument("--review-dir", required=True, help="Code reviews directory path")
loop_state_parser.add_argument("--action", required=True, choices=["read", "write", "update-branch"])
loop_state_parser.add_argument("--branches", help="JSON branch list (for write)")
loop_state_parser.add_argument("--args", help="JSON loop arguments (for write)")
loop_state_parser.add_argument("--branch", help="Branch name (for update-branch)")
loop_state_parser.add_argument("--status", help="Branch status (for update-branch)")
loop_state_parser.add_argument("--cycles", type=int, help="Cycle count (for update-branch)")
```

---

## SKILL.md `loop` Section (~80 lines)

The `loop` subcommand is added to SKILL.md as an orchestrator workflow. It calls the existing `new`/`update`/`fix` flows (which dispatch BRV and fix sub-agents). This keeps the dispatch chain flat.

### Key Orchestrator Responsibilities

1. **Branch resolution:** script call (`review-stack`) or use provided list
2. **State management:** script call (`review-loop-state`) for checkpoints
3. **Idempotency:** check review exists → `update` vs `new`
4. **Cycle management:** convergence check, stall detection, hard cap
5. **Stacked mode:** rebase between branches, post-fix cross-branch context
6. **Progress announcements:** emit structured progress at each milestone
7. **Dry run:** preview without executing
8. **Resume:** read state file, skip completed branches

### What the Orchestrator Does NOT Do

- Parse forge URLs → `_detect_forge()` script
- Discover stacks → `review-stack` script
- Track loop state → `review-loop-state` script
- Run builds/tests → BRV sub-agent
- Plan fixes → fix-planner sub-agent
- Apply fixes → fix-executor sub-agent
- Assign finding IDs → `review-status` script
- Validate transitions → `review-status` script

---

## Changes Summary

| Component | Action | Description |
|-----------|--------|-------------|
| `scripts/code_review.py` | Add | `_detect_forge()`, `run_forge()`, `run_stack()`, `run_loop_state()` |
| `scripts/code_review.py` | Modify | Refactor `run_preflight()` to use `_detect_forge()` |
| `scripts/__main__.py` | Modify | Register `review-forge`, `review-stack`, `review-loop-state` |
| `skills/code-review/SKILL.md` | Modify | Add `loop` subcommand (~80 lines), update subcommands table, update Step 0.5 to use `review-forge` |

No new agents — loop runs in SKILL.md orchestrator, dispatches existing BRV/fix agents.
