#!/usr/bin/env bash
###############################################################################
# review-loop.sh — Autonomous review→fix→update loop for stacked branches
#
# Each branch gets a fresh Claude session (no context pressure).
# State persists to loop-state.json — fully resumable.
#
# Phases per branch:
#   1. REVIEW   — Run code-review (new or update) via Claude session
#   2. FIX      — Fix critical/suggestion findings
#   3. VERIFY   — Run update review to validate fixes
#   4. CHECK    — Parse findings, decide converge/stall/continue
#   → Repeat FIX-VERIFY-CHECK up to --max-cycles
#
# Usage:
#   ./scripts/review-loop.sh --stack feat/vertical-slice               # Stack mode
#   ./scripts/review-loop.sh --branches "feat/a feat/b feat/c"         # Explicit list
#   ./scripts/review-loop.sh --resume                                  # Resume from state
#   ./scripts/review-loop.sh --dry-run --stack feat/vertical-slice     # Preview only
#   ./scripts/review-loop.sh --stack feat/x --project comp-embeddings  # With project context
#
# State:
#   Persisted to <code-reviews-dir>/loop-state.json — fully resumable.
#   Logs at <code-reviews-dir>/loop-logs/
###############################################################################
set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="${PLUGIN_ROOT}/scripts"
MODEL="claude-opus-4-6"
CLAUDE_CMD="claude"
MAX_CYCLES=3
MAX_REVIEW_FIX_LOOPS=3

# ─── CLI Flags ────────────────────────────────────────────────────────────────

STACK_BASE=""
BRANCHES=""
PROJECT=""
DRY_RUN=false
RESUME=false
AUTO_APPROVE=true  # Always auto-approve in headless mode

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack)      STACK_BASE="$2"; shift 2 ;;
    --branches)   BRANCHES="$2"; shift 2 ;;
    --project)    PROJECT="$2"; shift 2 ;;
    --max-cycles) MAX_CYCLES="$2"; shift 2 ;;
    --resume)     RESUME=true; shift ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --model)      MODEL="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^###/p' "$0" | head -n -1 | sed 's/^# \?//'
      exit 0 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ─── Helpers ──────────────────────────────────────────────────────────────────

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
info()    { echo "[$(timestamp)] [INFO] $*" | tee -a "${LOG_FILE:-/dev/stderr}"; }
warn()    { echo "[$(timestamp)] [WARN] $*" | tee -a "${LOG_FILE:-/dev/stderr}"; }
error()   { echo "[$(timestamp)] [ERROR] $*" | tee -a "${LOG_FILE:-/dev/stderr}"; }
success() { echo "[$(timestamp)] [DONE] $*" | tee -a "${LOG_FILE:-/dev/stderr}"; }
die()     { error "$@"; exit 1; }
hr()      { echo ""; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }

run_script() {
  local repo_root
  repo_root="$(git rev-parse --show-toplevel)"
  export REPO_ROOT="$repo_root"
  (cd "$SCRIPTS_DIR" && uv run python -m scripts "$@")
}

# ─── Resolve Repo and Paths ──────────────────────────────────────────────────

REPO_ROOT="$(git rev-parse --show-toplevel)"
REPO_ID="$(run_script repo-id)"
REVIEWS_DIR="$HOME/.claude/repo_notes/${REPO_ID}/code-reviews"
STATE_FILE="${REVIEWS_DIR}/loop-state.json"
LOG_DIR="${REVIEWS_DIR}/loop-logs"
LOG_FILE="${LOG_DIR}/review-loop.log"

mkdir -p "$REVIEWS_DIR" "$LOG_DIR"

# ─── State Management ────────────────────────────────────────────────────────

state_get() { jq -r "$1" "$STATE_FILE"; }
state_set() {
  local tmp="${STATE_FILE}.tmp"
  jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
}

# ─── Discover Branches ────────────────────────────────────────────────────────

discover_branches() {
  if [[ "$RESUME" == "true" ]]; then
    if [[ ! -f "$STATE_FILE" ]]; then
      die "No loop-state.json found. Cannot resume."
    fi
    info "Resuming from $STATE_FILE"
    return 0
  fi

  local branch_list=()

  if [[ -n "$STACK_BASE" ]]; then
    info "Discovering stack from base: $STACK_BASE"
    local stack_json
    stack_json="$(run_script review-stack --base "$STACK_BASE")"

    # Check for warnings
    local warnings
    warnings="$(echo "$stack_json" | jq -r '.warnings[]?' 2>/dev/null)"
    if [[ -n "$warnings" ]]; then
      warn "Stack discovery warnings:"
      echo "$warnings" | while read -r w; do warn "  $w"; done
    fi

    # Extract branch names in order
    while IFS= read -r branch; do
      branch_list+=("$branch")
    done < <(echo "$stack_json" | jq -r '.stack[].branch')

    info "Found ${#branch_list[@]} branches in stack"

  elif [[ -n "$BRANCHES" ]]; then
    read -ra branch_list <<< "$BRANCHES"
    info "Using explicit branch list: ${#branch_list[@]} branches"

  else
    die "Must specify --stack BASE, --branches \"a b c\", or --resume"
  fi

  # Build initial state
  local branches_json="["
  local first=true
  for branch in "${branch_list[@]}"; do
    if [[ "$first" == "true" ]]; then first=false; else branches_json+=","; fi
    branches_json+="{\"branch\":\"$branch\",\"status\":\"pending\",\"cycles\":0}"
  done
  branches_json+="]"

  local args_json
  args_json=$(jq -n \
    --arg stack "$STACK_BASE" \
    --arg project "$PROJECT" \
    --argjson max_cycles "$MAX_CYCLES" \
    '{stack: $stack, project: $project, max_cycles: $max_cycles, auto_approve: true}')

  run_script review-loop-state \
    --review-dir "$REVIEWS_DIR" \
    --action write \
    --branches "$branches_json" \
    --loop-args "$args_json"

  info "State initialized at $STATE_FILE"
}

# ─── Claude Session Runner ────────────────────────────────────────────────────

run_claude() {
  local description="$1"
  local prompt="$2"
  local log_file="$3"

  hr
  info "Spawning Claude session: $description"
  info "Log: $log_file"

  if [[ "$DRY_RUN" == "true" ]]; then
    info "DRY RUN — would execute: $description"
    echo "  Prompt (first 500 chars): ${prompt:0:500}..."
    return 0
  fi

  local exit_code=0
  set +e
  (
    set -o pipefail
    $CLAUDE_CMD --print \
      --verbose \
      --output-format stream-json \
      --model "$MODEL" \
      --dangerously-skip-permissions \
      "$prompt" 2>"${log_file%.log}.stderr" \
      | tee "${log_file%.log}.jsonl" \
      | jq -rj 'if .type == "assistant" then
          (.message.content[]? | select(.type=="text") | .text // empty)
        elif .type == "result" then
          (.result // empty), "\n"
        else empty end' 2>/dev/null \
      | tee "$log_file"
  )
  exit_code=$?
  set -e

  if [[ $exit_code -eq 0 ]]; then
    success "Session complete: $description"
  else
    error "Session failed (exit $exit_code): $description"
  fi
  return $exit_code
}

# ─── Phase: REVIEW ────────────────────────────────────────────────────────────

phase_review() {
  local branch="$1"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local review_dir="${REVIEWS_DIR}/${slug}"
  local review_exists="false"
  [[ -d "$review_dir" ]] && review_exists="true"

  local mode="new"
  [[ "$review_exists" == "true" ]] && mode="update"

  # Build base branch arg for stacked mode
  local base_arg=""
  if [[ -n "$STACK_BASE" ]]; then
    # Find this branch's parent from the stack
    local parent
    parent="$(jq -r --arg b "$branch" '.branches[] | select(.branch == $b) | .base // empty' "$STATE_FILE" 2>/dev/null || echo "")"
    # If parent not in state, check the stack discovery
    if [[ -z "$parent" ]]; then
      parent="$(run_script review-stack --base "$STACK_BASE" | jq -r --arg b "$branch" '.stack[] | select(.branch == $b) | .base // empty')"
    fi
    if [[ -n "$parent" && "$parent" != "null" ]]; then
      base_arg="--base \"$parent\""
    fi
  fi

  # Build project context arg
  local project_arg=""
  if [[ -n "$PROJECT" ]]; then
    project_arg="--project \"$PROJECT\""
  fi

  # Build cross-branch context
  local cross_context=""
  if [[ -n "$STACK_BASE" ]]; then
    # Find parent's review.md for cross-branch context
    local parent_slug
    parent_slug="$(echo "${parent:-}" | sed 's|/|-|g')"
    local parent_review="${REVIEWS_DIR}/${parent_slug}/review.md"
    if [[ -f "$parent_review" ]]; then
      cross_context="

## Cross-Branch Context (from parent: ${parent:-})
The parent branch has been reviewed and fixed. Read the parent's review at:
${parent_review}
Focus on: Summary table, Recommended Actions, and any unresolved findings.
Check if this branch inherits or addresses parent issues."
    fi
  fi

  local log_file="${LOG_DIR}/${slug}-review-$(date +%s).log"

  run_claude \
    "Review $branch ($mode)" \
    "Run /codebase-notes:code-review ${mode} \"${branch}\" ${base_arg} ${project_arg}

This is an automated review-fix loop. After the review completes:
1. Write the review.md and context.md files
2. Run the assign-ids and regenerate-history-row scripts
3. Report the total finding counts at the end

Key: Use the persona reference files at ${PLUGIN_ROOT}/skills/code-review/personas/ for each persona.
Dispatch BRV as sub-agent: codebase-notes:review-build-runtime-verifier
${cross_context}" \
    "$log_file"
}

# ─── Phase: FIX ───────────────────────────────────────────────────────────────

phase_fix() {
  local branch="$1"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local review_path="${REVIEWS_DIR}/${slug}/review.md"

  local log_file="${LOG_DIR}/${slug}-fix-$(date +%s).log"

  run_claude \
    "Fix findings for $branch" \
    "Run /codebase-notes:code-review fix \"${branch}\" --scope default --auto-approve

This is an automated fix cycle. Key behaviors for --auto-approve:
- Auto-approve the fix plan (no 'Proceed?' prompt)
- Auto-defer any conflicting findings
- Auto-skip failed clusters (revert and continue)
- Commit all fixes at the end

After fixing, report:
- How many findings were fixed
- How many were deferred
- The commit SHA" \
    "$log_file"
}

# ─── Phase: VERIFY (update review after fix) ──────────────────────────────────

phase_verify() {
  local branch="$1"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"

  local log_file="${LOG_DIR}/${slug}-verify-$(date +%s).log"

  run_claude \
    "Verify fixes for $branch (update review)" \
    "Run /codebase-notes:code-review update \"${branch}\"

This is the MANDATORY post-fix verification step.
Re-run all personas against the post-fix code to:
1. Confirm fixes resolved the targeted findings
2. Detect any new issues introduced by the fixes
3. Classify findings: new/persists/resolved/missed/regressed

After the update, run:
  review-status --action list-findings to get the current finding counts.

Report the finding counts clearly:
- Total critical (status=new,missed,regressed)
- Total suggestions (status=new,missed,regressed)
- Total resolved
- Assessment: CONVERGED (0 qualifying) or HAS_ISSUES (N remaining)" \
    "$log_file"
}

# ─── Phase: CHECK (parse results, decide next action) ─────────────────────────

phase_check() {
  local branch="$1"
  local cycle="$2"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local review_path="${REVIEWS_DIR}/${slug}/review.md"

  if [[ ! -f "$review_path" ]]; then
    warn "No review.md found for $branch after verify — treating as stalled"
    echo "stalled"
    return
  fi

  # Use script to count qualifying findings
  local findings_json
  findings_json="$(run_script review-status --review-path "$review_path" --action list-findings 2>/dev/null || echo "[]")"

  # Count qualifying: status in (new, missed, regressed) AND severity in (critical, suggestion)
  local qualifying
  qualifying="$(echo "$findings_json" | jq '[.[] | select(
    (.status == "new" or .status == "missed" or .status == "regressed") and
    (.severity == "critical" or .severity == "suggestion")
  )] | length')"

  info "Branch $branch cycle $cycle: $qualifying qualifying findings remaining"

  if [[ "$qualifying" -eq 0 ]]; then
    echo "converged"
  elif [[ "$cycle" -ge "$MAX_CYCLES" ]]; then
    echo "hard-cap"
  else
    echo "continue"
  fi
}

# ─── Rebase Next Branch ──────────────────────────────────────────────────────

rebase_next() {
  local current="$1"
  local next="$2"

  info "Rebasing $next onto $current..."
  git fetch origin "$current" 2>/dev/null || true

  local exit_code=0
  set +e
  git rebase "$current" "$next" 2>"${LOG_DIR}/rebase-${next}.stderr"
  exit_code=$?
  set -e

  if [[ $exit_code -ne 0 ]]; then
    warn "Rebase of $next onto $current failed. Aborting rebase."
    git rebase --abort 2>/dev/null || true
    warn "Review of $next will analyze pre-rebase code (may have false positives)"
  else
    success "Rebase of $next onto $current succeeded"
  fi
}

# ─── Dry Run ──────────────────────────────────────────────────────────────────

dry_run() {
  hr
  echo ""
  echo "  DRY RUN — Review-Fix Loop"
  echo ""

  local total
  total="$(jq '.branches | length' "$STATE_FILE")"

  echo "  | # | Branch | Review Exists | Status |"
  echo "  |---|--------|--------------|--------|"

  for ((i = 0; i < total; i++)); do
    local branch status slug
    branch="$(jq -r ".branches[$i].branch" "$STATE_FILE")"
    status="$(jq -r ".branches[$i].status" "$STATE_FILE")"
    slug="$(echo "$branch" | sed 's|/|-|g')"
    local exists="no"
    [[ -d "${REVIEWS_DIR}/${slug}" ]] && exists="yes"
    echo "  | $((i+1)) | $branch | $exists | $status |"
  done

  echo ""
  echo "  Max cycles per branch: $MAX_CYCLES"
  echo "  Estimated total cycles: $total — $((total * MAX_CYCLES))"
  echo ""
  hr
  exit 0
}

# ─── Main Loop ────────────────────────────────────────────────────────────────

main() {
  # Preflight
  command -v jq >/dev/null 2>&1 || die "jq required. Install: brew install jq"
  command -v "$CLAUDE_CMD" >/dev/null 2>&1 || die "claude CLI required."
  command -v uv >/dev/null 2>&1 || die "uv required."
  [[ -d "$(git rev-parse --show-toplevel)/.git" ]] || die "Not in a git repository."

  # Discover/load branches
  discover_branches

  [[ "$DRY_RUN" == "true" ]] && dry_run

  local total
  total="$(jq '.branches | length' "$STATE_FILE")"

  hr
  echo ""
  echo "  REVIEW-FIX LOOP"
  echo "  Branches: $total | Max cycles: $MAX_CYCLES | Model: $MODEL"
  echo "  State: $STATE_FILE"
  echo "  Logs: $LOG_DIR"
  echo ""

  # Show branch status
  for ((i = 0; i < total; i++)); do
    local branch status
    branch="$(jq -r ".branches[$i].branch" "$STATE_FILE")"
    status="$(jq -r ".branches[$i].status" "$STATE_FILE")"
    local icon
    case "$status" in
      converged|clean) icon="[DONE]" ;;
      stalled|hard-cap) icon="[STOP]" ;;
      pending)  icon="[    ]" ;;
      *)        icon="[>$status<]" ;;
    esac
    echo "  $icon Branch $((i+1)): $branch"
  done
  echo ""
  hr

  # Process each branch
  for ((i = 0; i < total; i++)); do
    local branch status cycles
    branch="$(jq -r ".branches[$i].branch" "$STATE_FILE")"
    status="$(jq -r ".branches[$i].status" "$STATE_FILE")"
    cycles="$(jq -r ".branches[$i].cycles // 0" "$STATE_FILE")"

    # Skip completed branches
    case "$status" in
      converged|stalled|hard-cap|clean)
        info "Skipping $branch (status: $status)"
        continue ;;
    esac

    hr
    info ">>> Branch $((i+1))/$total: $branch"

    # Mark in-progress
    state_set ".branches[$i].status = \"in-progress\""

    # Checkout the branch
    info "Checking out $branch..."
    git checkout "$branch" 2>/dev/null || git checkout -b "$branch" "origin/$branch" 2>/dev/null || die "Cannot checkout $branch"

    # Phase 1: Initial review
    info "Phase 1: REVIEW"
    phase_review "$branch"

    # Check if clean (no qualifying findings)
    local check_result
    check_result="$(phase_check "$branch" 0)"
    if [[ "$check_result" == "converged" ]]; then
      success "Branch $branch is clean — no critical/suggestion findings"
      state_set ".branches[$i].status = \"clean\" | .branches[$i].cycles = 0"

    else
      # Fix cycles
      local cycle=0
      local final_status="hard-cap"

      while [[ "$cycle" -lt "$MAX_CYCLES" ]]; do
        cycle=$((cycle + 1))
        info "Fix cycle $cycle/$MAX_CYCLES for $branch"

        # Phase 2: Fix
        info "Phase 2: FIX (cycle $cycle)"
        phase_fix "$branch"

        # Check if fix produced changes
        local changes
        changes="$(git diff --stat 2>/dev/null | wc -l)"
        if [[ "$changes" -eq 0 ]]; then
          # Also check for committed changes since the fix might have committed
          local recent_diff
          recent_diff="$(git log --oneline -1 --since='5 minutes ago' 2>/dev/null | wc -l)"
          if [[ "$recent_diff" -eq 0 ]]; then
            warn "Fix produced no changes — nothing to fix"
            final_status="fix-failed"
            break
          fi
        fi

        # Phase 3: Verify (MANDATORY post-fix update review)
        info "Phase 3: VERIFY (cycle $cycle)"
        phase_verify "$branch"

        # Phase 4: Check convergence
        info "Phase 4: CHECK (cycle $cycle)"
        check_result="$(phase_check "$branch" "$cycle")"

        state_set ".branches[$i].cycles = $cycle"

        case "$check_result" in
          converged)
            success "Branch $branch CONVERGED after $cycle cycle(s)"
            final_status="converged"
            break ;;
          hard-cap)
            warn "Branch $branch hit hard cap at $MAX_CYCLES cycles"
            final_status="hard-cap"
            break ;;
          continue)
            info "Branch $branch has remaining issues — continuing to cycle $((cycle+1))"
            ;;
        esac
      done

      state_set ".branches[$i].status = \"$final_status\" | .branches[$i].cycles = $cycle"
    fi

    success "Branch $((i+1))/$total complete: $branch ($(jq -r ".branches[$i].status" "$STATE_FILE"))"

    # Rebase next branch if stacked mode
    if [[ -n "$STACK_BASE" && $((i+1)) -lt "$total" ]]; then
      local next_branch
      next_branch="$(jq -r ".branches[$((i+1))].branch" "$STATE_FILE")"
      rebase_next "$branch" "$next_branch"
    fi
  done

  # Final summary
  hr
  echo ""
  echo "  LOOP SUMMARY"
  echo ""
  echo "  | Branch | Cycles | Status |"
  echo "  |--------|--------|--------|"
  for ((i = 0; i < total; i++)); do
    local branch status cycles
    branch="$(jq -r ".branches[$i].branch" "$STATE_FILE")"
    status="$(jq -r ".branches[$i].status" "$STATE_FILE")"
    cycles="$(jq -r ".branches[$i].cycles // 0" "$STATE_FILE")"
    echo "  | $branch | $cycles | $status |"
  done

  local converged stalled
  converged="$(jq '[.branches[] | select(.status == "converged" or .status == "clean")] | length' "$STATE_FILE")"
  stalled="$(jq '[.branches[] | select(.status == "stalled" or .status == "hard-cap" or .status == "fix-failed")] | length' "$STATE_FILE")"
  echo ""
  echo "  Total: $total branches, $converged converged/clean, $stalled stalled/capped"
  echo ""
  hr

  success "Review-fix loop complete!"
}

main "$@"
