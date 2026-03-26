# Review-Fix Loop Subcommand Spec

**Date:** 2026-03-26
**Status:** Draft
**Goal:** Add a `loop` subcommand to the code-review skill that automates the review→fix→update cycle until critical/high findings are resolved, with support for explicit branch lists and stacked branch auto-discovery.

---

## Modes

### Mode A: Explicit Branch List

```bash
/codebase-notes:code-review loop "feat/auth" "feat/api" "feat/db" [--project "projects/auth-refactor"]
```

Reviews each branch in order. No stack relationship assumed between them.

### Mode C: Stacked Branches

```bash
/codebase-notes:code-review loop --stack "feat/composition-embeddings-vertical-slice" [--project "projects/composition-embeddings"]
```

Starts at the given base branch, auto-discovers the chain (via PR chain or git topology), and reviews each layer in stack order. Each branch's review gets context from the previous branch's review.

---

## Loop Behavior Per Branch

```
For each branch:
  1. Load project context (from --project if provided)
  2. Load prior branch's review summary (if stacked)
  3. Run: /codebase-notes:code-review new "<branch>" [--base <parent>]
  4. Check findings: any critical or suggestion severity?
     - No → log "clean", move to next branch
     - Yes → enter fix cycle
  5. Fix cycle (max 5 iterations):
     a. Run: /codebase-notes:code-review fix "<branch>" --scope default
     b. Run: /codebase-notes:code-review update "<branch>"
     c. Check: zero NEW critical/suggestion findings in this update?
        - Yes → exit cycle (convergence)
        - No → continue cycle
     d. At cycle 5 → exit (hard cap), log remaining findings
  6. Log remaining suggestions/nits (don't fix them)
  7. Move to next branch
```

### Exit Conditions

| Condition | Action |
|-----------|--------|
| Zero new critical/suggestion after update | **Converged** — move to next branch |
| 5 fix cycles exhausted | **Hard cap** — log remaining, move on |
| Fix command fails (verification error, no findings to fix) | **Stalled** — log status, move on |
| All findings are nits only | **Clean enough** — move on |

### What "New" Means

The convergence check looks at findings with status `new` or `missed` at severity `critical` or `suggestion`. Findings that `persist` from prior cycles are NOT counted as convergence blockers — they were already known. Only genuinely new discoveries trigger another cycle.

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
  "forge": "gitlab"
}
```

### Discovery Algorithm

1. **Detect forge** via `review-forge` script (new — see below)
2. **Try PR/MR chain first** (more reliable — PRs explicitly declare their base):
   - GitHub: `gh pr list --base <branch> --json number,headRefName --state open`
   - GitLab: `glab mr list --target-branch <branch> -F json`
   - Extract `source_branch`/`headRefName` → that's the child
   - Recurse: child becomes new base, repeat until no children found
3. **If no forge CLI available**, fall back to **git topology**:
   - For each unmerged local branch, check if `git merge-base <current> <candidate>` equals `git rev-parse <current>` (current branch tip is the merge-base = candidate branches off current)
   - Filter to direct children only (not transitive)
4. **If branch has multiple children**: present to user, ask which path to follow (or "all" for a breadth-first approach)

### New Script: `review-forge`

```bash
run-script review-forge
```

Returns:
```json
{
  "forge": "gitlab",
  "cli": "glab",
  "cli_available": true,
  "remote_url": "git@gitlab.com:radical-ai/arc.git"
}
```

Logic:
- Parse `git remote get-url origin`
- Check for `github.com` → forge=github, cli=gh
- Check for `gitlab` anywhere in URL → forge=gitlab, cli=glab
- Verify CLI available via `shutil.which(cli)`
- Return structured JSON

This replaces the current prose-based forge detection in SKILL.md Step 0.5.

---

## Project Context Integration

The `--project` flag points to a project notes directory under `~/.claude/repo_notes/<repo_id>/projects/<name>/`. When provided:

1. Read the project's `index.md` for goals, architecture decisions, open questions
2. Pass project context to each persona alongside the diff and codebase notes
3. Each review's context.md links to the project notes under "Pre-requisites"

This gives reviewers domain knowledge about the feature being built across the stack — not just what the code does, but *why* and *how it fits the larger goal*.

---

## Cross-Branch Context (Stacked Mode)

When reviewing branch N+1 in a stack, the orchestrator:

1. Reads branch N's `review.md` — specifically the **Summary table** and **Recommended Actions**
2. Reads branch N's `context.md` — the **What Changed** and **How It Works** sections
3. Passes this as additional context to personas:

```
## Context from Parent Branch Review

The parent branch (feat/vertical-slice) was reviewed. Key context:

### Summary
| Persona | Verdict | Critical | Suggestions |
...

### Unresolved Findings
<any persisting or deferred findings from parent>

### Recommended Actions (from parent review)
<parent's recommended actions>

When reviewing this branch, check:
- Does this branch inherit any of the parent's unresolved issues?
- Does this branch's approach align with or contradict the parent's architecture?
- Are there cross-branch dependencies that could break?
```

---

## New Sub-Agent: `loop-coordinator`

The loop is complex enough to warrant its own agent definition. This keeps the SKILL.md `loop` subcommand section compact — it just dispatches the coordinator.

```
agents/loop-coordinator.md
```

The coordinator:
- Receives the branch list (explicit or from `review-stack` script)
- Receives project context path
- Manages the per-branch cycle: new → [fix → update]* → next
- Tracks convergence per branch
- Passes cross-branch context in stacked mode
- Produces a final summary

The coordinator invokes the code-review skill's `new`, `fix`, and `update` subcommands. Since sub-agents can't invoke skills directly, the coordinator uses the underlying operations:
- Calls scripts for deterministic ops (`review-preflight`, `review-delta`, `review-status`, etc.)
- Runs inline personas for review (reads persona reference files)
- Dispatches BRV sub-agent for build verification
- Dispatches fix-planner and fix-executor sub-agents for fixes

Wait — sub-agents can't spawn other sub-agents. So the coordinator can't dispatch BRV/fix agents.

**Revised approach:** The `loop` subcommand runs in the SKILL.md orchestrator (main context), not as a separate agent. It's a workflow that calls the existing `new`, `fix`, and `update` flows in sequence. This keeps the dispatch chain flat: main → BRV/fix agents (one level only).

### SKILL.md `loop` Section (~60 lines)

```markdown
## Subcommand: `loop`

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `"branch1" "branch2" ...` | Yes (unless --stack) | Branches to review in order |
| `--stack BASE` | No | Auto-discover stacked branches from base |
| `--project NAME` | No | Project notes path for domain context |
| `--max-cycles N` | No | Max fix cycles per branch (default: 5) |

### Flow

1. **Resolve branch list:**
   - If `--stack`: run `run-script review-stack --base <BASE>`, get ordered list
   - Otherwise: use provided branch list

2. **Load project context** (if `--project`):
   - Read `~/.claude/repo_notes/<repo_id>/projects/<name>/index.md`

3. **For each branch in order:**

   a. **Initial review:** Follow the `new` subcommand flow (Steps 1-8).
      - If stacked: pass `--base <parent_branch>` and cross-branch context from parent's review
      - If `--project`: include project context in persona prompts

   b. **Check findings:** Run `run-script review-status --review-path <path> --action list-findings`
      - Filter for critical + suggestion severity
      - If zero: log "Branch clean", skip to next branch

   c. **Fix cycle** (up to --max-cycles, default 5):
      - Run the `fix` subcommand flow (Phases 0-4) with `--scope default`
      - Run the `update` subcommand flow (Steps 1-12)
      - Run `run-script review-status --review-path <path> --action list-findings`
      - Count findings where status is `new` or `missed` AND severity is critical or suggestion
      - If zero new: **converged** — exit cycle
      - If same or more new findings as last cycle: **stalled** — exit cycle
      - Otherwise: continue

   d. **Log remaining:** List any persisting suggestions/nits (not fixed, just noted)
   e. **Move to next branch**

4. **Final summary:**

   ```
   ## Loop Summary

   | Branch | Cycles | Status | Critical | Suggestions | Nits |
   |--------|--------|--------|----------|-------------|------|
   | feat/vertical-slice | 2 | converged | 0 | 0 | 3 |
   | feat/eval-harness | 3 | converged | 0 | 1 | 2 |
   | feat/visualization | 5 | hard-cap | 1 | 2 | 1 |
   | feat/wire-consumers | 1 | clean | 0 | 0 | 0 |

   Total: 4 branches reviewed, 3 converged, 1 hit hard cap
   Remaining issues: 1 critical (feat/visualization), 3 suggestions
   ```
```

---

## New Script Commands

### `review-forge`

Added to `scripts/code_review.py` as `run_forge(args)`.

**Input:** No args (reads from `git remote get-url origin`)
**Output:** JSON with forge, cli, cli_available, remote_url
**Logic:**
- `git remote get-url origin` → parse URL
- `github.com` in URL → forge=github, cli=gh
- `gitlab` in URL → forge=gitlab, cli=glab
- `shutil.which(cli)` → cli_available
- Return JSON

### `review-stack`

Added to `scripts/code_review.py` as `run_stack(args)`.

**Input:** `--base BRANCH`
**Output:** JSON with ordered stack array
**Logic:**
1. Call `run_forge` internally to detect forge + CLI
2. If CLI available:
   - GitHub: `gh pr list --base <branch> --json number,headRefName --state open`
   - GitLab: `glab mr list --target-branch <branch> -F json` → extract `source_branch`, `iid`
   - Recurse: each child becomes new base
3. If no CLI:
   - For each local unmerged branch: check if `git merge-base <base> <candidate> == git rev-parse <base>`
   - Filter direct children
   - Recurse
4. Build ordered list and return

### Registration in `__main__.py`

```python
# review-forge
subparsers.add_parser("review-forge", help="Detect git forge (GitHub/GitLab) and CLI availability")

# review-stack
stack_parser = subparsers.add_parser("review-stack", help="Discover stacked branch chain from base")
stack_parser.add_argument("--base", required=True, help="Base branch of the stack")
```

---

## Changes Summary

| Component | Action | Description |
|-----------|--------|-------------|
| `scripts/code_review.py` | Add | `run_forge()` and `run_stack()` functions |
| `scripts/__main__.py` | Modify | Register `review-forge` and `review-stack` commands |
| `skills/code-review/SKILL.md` | Modify | Add `loop` subcommand (~60 lines), update Step 0.5 to use `review-forge` script |
| `skills/code-review/SKILL.md` | Modify | Update subcommands table with `loop` |

No new agents needed — the loop runs in the SKILL.md orchestrator context to maintain the flat dispatch chain (main → BRV/fix agents).
