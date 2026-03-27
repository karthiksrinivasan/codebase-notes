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
#   ./scripts/review-loop.sh --reset --stack feat/vertical-slice       # Clear prior state, start fresh
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
RESET=false
AUTO_APPROVE=true  # Always auto-approve in headless mode

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack)      STACK_BASE="$2"; shift 2 ;;
    --branches)   BRANCHES="$2"; shift 2 ;;
    --project)    PROJECT="$2"; shift 2 ;;
    --max-cycles) MAX_CYCLES="$2"; shift 2 ;;
    --resume)     RESUME=true; shift ;;
    --reset)      RESET=true; shift ;;
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
  # --reset: clear prior state AND old review files so loop starts truly fresh
  if [[ "$RESET" == "true" ]]; then
    if [[ -f "$STATE_FILE" ]]; then
      info "Resetting: removing existing $STATE_FILE"
      rm -f "$STATE_FILE"
    fi
    # Archive old review directories so file-age checks don't see stale files
    # Reviews are renamed to <slug>.pre-<timestamp> to preserve history
    local reset_ts
    reset_ts="$(date +%Y%m%d-%H%M%S)"
    local old_reviews
    old_reviews="$(find "$REVIEWS_DIR" -maxdepth 1 -type d \( -name "feat-*" -o -name "fix-*" -o -name "hotfix-*" \) 2>/dev/null)"
    if [[ -n "$old_reviews" ]]; then
      info "Resetting: archiving old review directories (suffix: .pre-${reset_ts})"
      echo "$old_reviews" | while read -r d; do mv "$d" "${d}.pre-${reset_ts}"; done
    fi
    # Also archive old loop-state and logs
    if [[ -d "$LOG_DIR" ]]; then
      mv "$LOG_DIR" "${LOG_DIR}.pre-${reset_ts}"
      mkdir -p "$LOG_DIR"
    fi
  fi

  if [[ "$RESUME" == "true" ]]; then
    if [[ ! -f "$STATE_FILE" ]]; then
      die "No loop-state.json found. Cannot resume."
    fi
    info "Resuming from $STATE_FILE"
    return 0
  fi

  # If state exists and not reset, check if already complete
  if [[ -f "$STATE_FILE" ]]; then
    local all_done
    all_done="$(jq '[.branches[] | select(.status == "pending" or .status == "in-progress")] | length' "$STATE_FILE" 2>/dev/null || echo "0")"
    if [[ "$all_done" -eq 0 ]]; then
      warn "All branches in loop-state.json are already complete."
      warn "Use --reset to start a fresh loop, or --resume to re-check."
      die "Nothing to do. Pass --reset to clear prior state."
    fi
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

  # Build project context snippet (known issues, runtime notes)
  local project_context=""
  if [[ -n "$PROJECT" ]]; then
    local project_context_file
    project_context_file="$(run_script repo-id)"
    project_context_file="$HOME/.claude/repo_notes/${project_context_file}/projects/${PROJECT}/context.md"
    if [[ -f "$project_context_file" ]]; then
      project_context="

## Project Context (from ${PROJECT}/context.md)
$(cat "$project_context_file")

IMPORTANT: Known issues listed above are environmental/runtime — do NOT flag them as code findings unless the code itself is incorrect. For example, if the context says 'set OMP_NUM_THREADS=1 before running FAISS', that is a deployment concern, not a code bug."
    fi
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
${project_context}${cross_context}" \
    "$log_file"
}

# ─── Phase: FIX ───────────────────────────────────────────────────────────────

phase_fix() {
  local branch="$1"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local review_path="${REVIEWS_DIR}/${slug}/review.md"

  # Load project context for fix guidance
  local fix_project_context=""
  if [[ -n "$PROJECT" ]]; then
    local ctx_repo_id
    ctx_repo_id="$(run_script repo-id)"
    local ctx_file="$HOME/.claude/repo_notes/${ctx_repo_id}/projects/${PROJECT}/context.md"
    if [[ -f "$ctx_file" ]]; then
      fix_project_context="

## Project Context
$(cat "$ctx_file")

IMPORTANT: Do NOT attempt to fix known runtime/environmental issues listed above. Only fix actual code defects."
    fi
  fi

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
- The commit SHA
${fix_project_context}" \
    "$log_file"
}

# ─── Phase: CONFIRM (fresh review + script-based assess) ─────────────────────
#
# Two sub-steps in sequence:
# 1. CONFIRM-REVIEW: Fresh code-review new (archives prior review, unbiased)
# 2. CONFIRM-ASSESS: Script compares findings against deferred registry
#    → re-discoveries auto-deferred, contradictions flagged, only new qualify

phase_confirm() {
  local branch="$1"
  local cycle="$2"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local review_dir="${REVIEWS_DIR}/${slug}"
  local registry_path="${REVIEWS_DIR}/${slug}/deferred-registry.json"

  # --- Sub-step 1: Archive existing review and run fresh ---
  if [[ -d "$review_dir" ]]; then
    # Save deferred registry before archiving (it must survive the archive)
    local saved_registry=""
    if [[ -f "$registry_path" ]]; then
      saved_registry="$(cat "$registry_path")"
    fi

    local confirm_ts
    confirm_ts="$(date +%Y%m%d-%H%M%S)"
    mv "$review_dir" "${review_dir}.pre-confirm-${confirm_ts}"
    info "Archived existing review for fresh confirm review"

    # Restore deferred registry into new directory
    if [[ -n "$saved_registry" ]]; then
      mkdir -p "$review_dir"
      echo "$saved_registry" > "$registry_path"
    fi
  fi

  # Run fresh review (phase_review sees no review.md → mode=new)
  info "CONFIRM sub-step 1: Fresh review (unbiased)"
  phase_review "$branch" || warn "Confirm review exited with error — assessing results anyway"

  # --- Sub-step 2: Script-based assessment ---
  local review_path="${review_dir}/review.md"
  if [[ ! -f "$review_path" ]]; then
    warn "No review.md after confirm review — treating as stalled" >&2
    echo "stalled"
    return
  fi

  info "CONFIRM sub-step 2: Assess findings against deferred registry"

  # Auto-populate deferred registry from this review's deferred findings
  run_script review-deferred \
    --registry-path "$registry_path" \
    --action auto-populate \
    --review-path "$review_path" \
    --cycle "$cycle" 2>/dev/null || true

  # Run assessment
  local assess_json
  assess_json="$(run_script review-assess \
    --review-path "$review_path" \
    --registry-path "$registry_path" 2>/dev/null || echo '{"summary":{"new_qualifying":0,"total":0}}')"

  local new_qualifying total re_discovered contradictions
  new_qualifying="$(echo "$assess_json" | jq '.summary.new_qualifying')"
  total="$(echo "$assess_json" | jq '.summary.total')"
  re_discovered="$(echo "$assess_json" | jq '.summary.re_discovered')"
  contradictions="$(echo "$assess_json" | jq '.summary.contradictions')"

  # Log assessment results to stderr (not captured by $())
  info "ASSESS: $new_qualifying new qualifying, $re_discovered re-discovered, $contradictions contradictions (of $total total)" >&2

  if [[ "$re_discovered" -gt 0 ]]; then
    info "ASSESS: $re_discovered findings were previously deferred — not counted as qualifying" >&2
  fi
  if [[ "$contradictions" -gt 0 ]]; then
    warn "ASSESS: $contradictions findings contradict prior fixes — flagged, not counted" >&2
  fi

  # Return convergence decision
  if [[ "$total" -eq 0 ]]; then
    warn "Confirm review has 0 findings — may not have been written properly" >&2
    echo "stalled"
  elif [[ "$new_qualifying" -eq 0 ]]; then
    success "CONVERGED: 0 new qualifying findings after assessment" >&2
    echo "converged"
  elif [[ "$cycle" -ge "$MAX_CYCLES" ]]; then
    echo "hard-cap"
  else
    echo "continue"
  fi
}

# ─── Phase: CHECK (parse raw review, decide next action) ─────────────────────
# Used only after the initial REVIEW (before any fix cycle).
# After FIX, CONFIRM handles both review and check.

phase_check() {
  local branch="$1"
  local cycle="$2"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local review_path="${REVIEWS_DIR}/${slug}/review.md"

  if [[ ! -f "$review_path" ]]; then
    warn "No review.md found — treating as stalled" >&2
    echo "stalled"
    return
  fi

  # Use script to count qualifying findings
  local findings_json
  findings_json="$(run_script review-status --review-path "$review_path" --action list-findings 2>/dev/null || echo "[]")"

  local qualifying
  qualifying="$(echo "$findings_json" | jq '[.[] | select(
    (.status == "new" or .status == "missed" or .status == "regressed") and
    (.severity == "critical" or .severity == "suggestion")
  )] | length')"

  local total_findings
  total_findings="$(echo "$findings_json" | jq 'length')"

  if [[ "$total_findings" -eq 0 ]]; then
    warn "review.md has 0 findings — may not have been written properly" >&2
    echo "stalled"
    return
  fi

  info "Branch $branch cycle $cycle: $qualifying qualifying / $total_findings total findings" >&2

  if [[ "$qualifying" -eq 0 ]]; then
    success "CLEAN: 0 qualifying findings" >&2
    echo "converged"
  else
    echo "continue"
  fi
}

# ─── Deferred Registry Helpers ───────────────────────────────────────────────

record_fix_history() {
  local branch="$1"
  local cycle="$2"
  local commit="$3"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local registry_path="${REVIEWS_DIR}/${slug}/deferred-registry.json"
  local review_path="${REVIEWS_DIR}/${slug}/review.md"

  # Get list of fixed findings and modified files from the review
  local fixed_ids modified_files summaries_json
  fixed_ids="$(run_script review-status --review-path "$review_path" --action list-findings 2>/dev/null \
    | jq -c '[.[] | select(.status == "fixed") | .id]' || echo '[]')"
  modified_files="$(git diff --name-only "${commit}^..${commit}" 2>/dev/null \
    | jq -R -s 'split("\n") | map(select(. != ""))' || echo '[]')"

  # Build summaries map from fixed findings
  summaries_json="$(run_script review-status --review-path "$review_path" --action list-findings 2>/dev/null \
    | jq -c '[.[] | select(.status == "fixed")] | map({(.id): .title}) | add // {}' || echo '{}')"

  local entry
  entry="$(jq -n \
    --argjson cycle "$cycle" \
    --arg commit "$commit" \
    --argjson findings_fixed "$fixed_ids" \
    --argjson files_modified "$modified_files" \
    --argjson summaries "$summaries_json" \
    '{cycle: $cycle, commit: $commit, findings_fixed: $findings_fixed, files_modified: $files_modified, summaries: $summaries}')"

  run_script review-deferred \
    --registry-path "$registry_path" \
    --action add-fix \
    --entry "$entry" 2>/dev/null || true
}

populate_deferred_registry() {
  local branch="$1"
  local cycle="$2"
  local slug
  slug="$(echo "$branch" | sed 's|/|-|g')"
  local registry_path="${REVIEWS_DIR}/${slug}/deferred-registry.json"
  local review_path="${REVIEWS_DIR}/${slug}/review.md"

  [[ -f "$review_path" ]] || return 0

  run_script review-deferred \
    --registry-path "$registry_path" \
    --action auto-populate \
    --review-path "$review_path" \
    --cycle "$cycle" 2>/dev/null || true
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

    # Stash any dirty files (e.g., uv.lock from previous fix sessions) before checkout
    if [[ -n "$(git diff --name-only 2>/dev/null)" ]]; then
      info "Stashing dirty working tree before checkout..."
      git stash push -m "review-loop: pre-checkout stash" 2>/dev/null || true
    fi

    # Checkout the branch
    info "Checking out $branch..."
    git checkout "$branch" 2>/dev/null || git checkout -b "$branch" "origin/$branch" 2>/dev/null || die "Cannot checkout $branch"

    # ── Phase 1: REVIEW ────────────────────────────────────────────────────
    info "Phase 1: REVIEW"
    phase_review "$branch" || warn "Review session exited with error — checking results anyway"

    # Check if clean (no qualifying findings → skip fix entirely)
    local check_result
    check_result="$(phase_check "$branch" 0)"
    if [[ "$check_result" == "converged" ]]; then
      success "Branch $branch is clean — no critical/suggestion findings"
      state_set ".branches[$i].status = \"clean\" | .branches[$i].cycles = 0"

    else
      # Populate deferred registry from initial review
      populate_deferred_registry "$branch" 0

      # ── Fix-Confirm cycles ──────────────────────────────────────────────
      local cycle=0
      local final_status="hard-cap"

      while [[ "$cycle" -lt "$MAX_CYCLES" ]]; do
        cycle=$((cycle + 1))
        info "═══ Cycle $cycle/$MAX_CYCLES for $branch ═══"

        # ── Phase 2: FIX ──────────────────────────────────────────────────
        info "Phase 2: FIX"
        phase_fix "$branch" || warn "Fix session exited with error — checking results anyway"

        # Record fix history in deferred registry (for contradiction detection)
        local fix_commit
        fix_commit="$(git log --oneline -1 --since='10 minutes ago' --format='%h' 2>/dev/null || echo "")"
        if [[ -n "$fix_commit" ]]; then
          record_fix_history "$branch" "$cycle" "$fix_commit"
        fi

        # Populate deferred registry from fix session's deferred findings
        populate_deferred_registry "$branch" "$cycle"

        # ── Phase 3: CONFIRM (fresh review + assess) ─────────────────────
        info "Phase 3: CONFIRM"
        local confirm_result
        confirm_result="$(phase_confirm "$branch" "$cycle")"

        state_set ".branches[$i].cycles = $cycle"

        case "$confirm_result" in
          converged)
            success "Branch $branch CONVERGED after $cycle cycle(s) — confirmed by fresh review + assessment"
            final_status="converged"
            break ;;
          hard-cap)
            warn "Branch $branch hit hard cap at $MAX_CYCLES cycles"
            final_status="hard-cap"
            break ;;
          stalled)
            warn "Branch $branch stalled at cycle $cycle"
            final_status="stalled"
            break ;;
          continue)
            info "Branch $branch has new issues — continuing to cycle $((cycle+1))"
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
