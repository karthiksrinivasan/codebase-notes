# Hybrid Architecture Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the code-review skill from a 1337-line monolithic SKILL.md into a hybrid architecture: ~550-line orchestrator + 5 persona reference files + 3 sub-agent definitions + 3 templates.

**Architecture:** Four read-only personas (SA, DE, SC, APT) stay inline in SKILL.md for cross-persona synergy. Three sub-agents (BRV, fix-planner, fix-executor) are extracted to `agents/` for tool isolation. Persona details move to reference files in `personas/`. Document templates move to `templates/`. Existing scripts (`code_review.py`) are unchanged.

**Tech Stack:** Markdown (skill/agent/persona/template files), no code changes — pure skill layer restructure.

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `skills/code-review/templates/review.md` | Review document skeleton with placeholders |
| Create | `skills/code-review/templates/context.md` | Context document skeleton with placeholders |
| Create | `skills/code-review/templates/fix-plan.md` | Fix plan skeleton with placeholders |
| Create | `skills/code-review/personas/systems-architect.md` | SA persona reference (focus, questions, format) |
| Create | `skills/code-review/personas/domain-expert.md` | DE persona reference (focus, cross-layer reasoning, format) |
| Create | `skills/code-review/personas/standards-compliance.md` | SC persona reference (focus, standards table, format) |
| Create | `skills/code-review/personas/adversarial-path-tracer.md` | APT persona reference (focus, 3 categories, tables, format) |
| Create | `skills/code-review/personas/build-runtime-verifier.md` | BRV persona reference (execution steps, format) |
| Create | `agents/review-build-runtime-verifier.md` | BRV sub-agent definition (Bash access, opus, high effort) |
| Create | `agents/fix-planner.md` | Fix planner sub-agent definition (read-only, opus, high effort) |
| Create | `agents/fix-executor.md` | Fix executor sub-agent definition (Write/Edit/Bash, opus, high effort) |
| Rewrite | `skills/code-review/SKILL.md` | Hybrid orchestrator (~550 lines) referencing all above files |

**Scripts unchanged:** `scripts/code_review.py`, `scripts/__main__.py`, `scripts/context_index.py` — no modifications needed.

---

### Task 1: Create template files

**Files:**
- Create: `skills/code-review/templates/review.md`
- Create: `skills/code-review/templates/context.md`
- Create: `skills/code-review/templates/fix-plan.md`

These are document skeletons with `{placeholder}` variables that the orchestrator fills in.

- [ ] **Step 1: Create the templates directory**

```bash
mkdir -p /Users/karthik/Documents/work/codebase-notes/skills/code-review/templates
```

- [ ] **Step 2: Write templates/review.md**

Create `skills/code-review/templates/review.md` with this exact content:

```markdown
---
identifier: {identifier}
created: {date}
last_updated: {date}
status: reviewed
current_version: 1
head_sha: {head_sha}
merge_base_sha: {merge_base_sha}
last_fix_sha: null
---
# Review: {title}

## Review History

| Version | Date | Head SHA | Trigger | New | Resolved | Persists | Missed | Regressed |
|---------|------|----------|---------|-----|----------|----------|--------|-----------|
| v1 | {date} | `{head_sha}` | new | {new_count} | — | — | — | — |

---

{persona_sections}

## Fix Log

_No fixes applied yet. Use `/codebase-notes:code-review fix "{identifier}"` to address findings._

## Summary

| Persona | Verdict | Critical | Suggestions |
|---------|---------|----------|-------------|
{summary_rows}

## Recommended Actions

{recommended_actions}
```

- [ ] **Step 3: Write templates/context.md**

Create `skills/code-review/templates/context.md` with this exact content:

```markdown
---
identifier: {identifier}
type: {type}
base_branch: {base}
head_branch: {head}
created: {date}
last_updated: {date}
status: reviewed
---
# {title}

## Pre-requisites

{prerequisites}

## Why This Change

{motivation}

## What Changed

### Summary
{change_summary}

### By Area
| Area | Files | Nature of Change |
|------|-------|-----------------|
{area_rows}

### Architecture Impact
{architecture_impact}

## How It Works
{implementation_approach}

## Related Notes
| Note | Relevance | May Need Update |
|------|-----------|-----------------|
{related_notes}
```

- [ ] **Step 4: Write templates/fix-plan.md**

Create `skills/code-review/templates/fix-plan.md` with this exact content:

```markdown
---
identifier: {identifier}
review_version: {version}
created: {date}
last_updated: {date}
scope: {scope}
status: planned
pre_fix_sha: {pre_fix_sha}
---
# Fix Plan: {title}

**Review version:** v{version}
**Scope:** {scope} — {count} findings to address
**Conflicts:** {conflict_count}
**Deferred:** {deferred_count}

## Conflict Resolution
{conflicts_table}

## Fix Clusters
{clusters}

## Deferred Findings
{deferred_table}

## Execution Checklist
{checklist}
```

- [ ] **Step 5: Commit**

```bash
git add skills/code-review/templates/
git commit -m "feat: add review, context, and fix-plan templates for code-review skill"
```

---

### Task 2: Create persona reference files

**Files:**
- Create: `skills/code-review/personas/systems-architect.md`
- Create: `skills/code-review/personas/domain-expert.md`
- Create: `skills/code-review/personas/standards-compliance.md`
- Create: `skills/code-review/personas/adversarial-path-tracer.md`
- Create: `skills/code-review/personas/build-runtime-verifier.md`

These are NOT agent definitions. They are reference documents that SKILL.md reads for inline persona instructions. Each contains the persona's focus, review questions, and output format.

- [ ] **Step 1: Create the personas directory**

```bash
mkdir -p /Users/karthik/Documents/work/codebase-notes/skills/code-review/personas
```

- [ ] **Step 2: Write personas/systems-architect.md**

Create `skills/code-review/personas/systems-architect.md` with this exact content:

```markdown
# Systems Architect (SA)

**Focus:** Code quality, design patterns, scalability, maintainability, separation of concerns.

## Review Questions
- Does the change follow established patterns in the codebase?
- Are abstractions at the right level?
- Will this scale? Performance implications?
- Is the separation of concerns clean?
- Are there better design alternatives?

## Finding Format
#### SA-N (severity) — Title
**File:** path:line-range
**Status:** new
Description with specific details and reasoning.
```

- [ ] **Step 3: Write personas/domain-expert.md**

Create `skills/code-review/personas/domain-expert.md` with this exact content:

```markdown
# Domain Expert (DE)

**Focus:** Domain correctness AND cross-layer semantic reasoning.

## Surface-Level Checks
- Are domain concepts used correctly?
- Do naming conventions match domain terminology?
- Are domain invariants preserved?

## Cross-Layer Semantic Reasoning (critical)
- Trace data between layers (API → service → storage → output). At each boundary: does this transformation preserve domain meaning?
- Flag normalization/aggregation/projection that destroys domain-meaningful information
- Check filters, scopes, and thresholds match the actual domain of the data
- Verify labels and user-facing text accurately describe what code does
- Check that operations preserve or explicitly discard data provenance

**Note:** Domain inferred from repo docs and codebase notes. Materials science: units, physical constraints, composition semantics. Web app: business logic, user flows, authorization scope.

## Finding Format
#### DE-N (severity) — Title
**File:** path:line-range
**Status:** new
Cross-layer findings include the specific layer boundary where meaning is lost.
```

- [ ] **Step 4: Write personas/standards-compliance.md**

Create `skills/code-review/personas/standards-compliance.md` with this exact content:

```markdown
# Standards Compliance (SC)

**Focus:** Adherence to the repo's stated standards and conventions.

## Review Questions
- Does the code follow conventions in CLAUDE.md and AGENTS.md?
- Are there linter config violations?
- Does commit style match the repo's convention?
- Are imports, naming, and file organization consistent?

## Standards Referenced Table
| Source | Key Rules |
|--------|-----------|
| CLAUDE.md | <relevant rules> |
| AGENTS.md | <relevant rules> |
| Other | <linter configs, .editorconfig, etc.> |

## Finding Format
#### SC-N (severity) — Title
**File:** path:line-range
**Status:** new
Cite the specific standard violated.
```

- [ ] **Step 5: Write personas/adversarial-path-tracer.md**

Create `skills/code-review/personas/adversarial-path-tracer.md` with this exact content:

```markdown
# Adversarial Path Tracer (APT)

**Focus:** Edge cases, error propagation, behavioral side effects, timing hazards.

## A. Edge Cases and Error Propagation
- nil/null/None/empty inputs?
- Error paths handled? Propagation correct?
- Boundary values (0, max_int, empty list, huge input)?
- Implicit assumptions that could break?

## B. Behavioral Side Effects on Existing Code
- Find every caller/consumer of modified functions. Read them. Does the change break caller assumptions?
- If return type, side effects, or error behavior changed, trace every call site
- If new feature auto-activates, check impact on existing workflows
- If public API added, verify end-to-end wiring complete

## C. Order-of-Operations and Timing Hazards
- Write before lock? Read stale state? Advance cursor before confirming? Write before prerequisite structures exist? Race conditions?

## Tables
### Traced Paths
| Path | Input Condition | Expected | Potential | Issue? |
|------|----------------|----------|-----------|--------|

### Caller Impact
| Modified Function | Caller | Assumption That May Break | Severity |
|------------------|--------|--------------------------|----------|

## Finding Format
#### APT-N (severity) — Title
**File:** path:line-range
**Status:** new
Concrete scenario that triggers the issue.
```

- [ ] **Step 6: Write personas/build-runtime-verifier.md**

Create `skills/code-review/personas/build-runtime-verifier.md` with this exact content:

```markdown
# Build & Runtime Verifier (BRV)

**Focus:** Does this code actually run? Verified by execution, not reading.

This persona is dispatched as a sub-agent (needs Bash tool access).
See `agents/review-build-runtime-verifier.md` for the agent definition.

## Execution Steps
1. Dependency check — verify new imports resolve
2. Linter pass — run repo's configured linter on changed files
3. Test execution — run relevant tests, check they test new behavior
4. Build/artifact verification — CLI commands, registrations, wiring

## Finding Format
#### BRV-N (severity) — Title
**File:** path:line-range
**Status:** new
Exact command and output that revealed the issue.
```

- [ ] **Step 7: Commit**

```bash
git add skills/code-review/personas/
git commit -m "feat: add 5 persona reference files for code-review skill"
```

---

### Task 3: Create sub-agent definitions

**Files:**
- Create: `agents/review-build-runtime-verifier.md`
- Create: `agents/fix-planner.md`
- Create: `agents/fix-executor.md`

These ARE agent definitions — placed at the plugin root `agents/` directory for auto-discovery by Claude Code. Each has YAML frontmatter with `name`, `description`, `tools`, `model`, `effort`, `maxTurns`, and optionally `memory`.

- [ ] **Step 1: Create the agents directory**

```bash
mkdir -p /Users/karthik/Documents/work/codebase-notes/agents
```

- [ ] **Step 2: Write agents/review-build-runtime-verifier.md**

Create `agents/review-build-runtime-verifier.md` with this exact content:

```markdown
---
name: review-build-runtime-verifier
description: Verifies code changes by actually executing tests, linters, and builds. Must run commands, not just read code. Dispatched by code-review skill.
tools: Read, Grep, Glob, Bash
model: opus
effort: high
maxTurns: 15
memory: project
---

You are verifying code changes by actually running them. You MUST execute commands, not just read code.

## Your Focus

**Step 1: Dependency check**
- For every new import in the diff, verify the package is declared as a dependency
- Run import checks (e.g., `uv run python -c "import <module>"`)

**Step 2: Linter pass**
- Identify the repo's configured linters from CI config, pyproject.toml, package.json
- Run the linter on changed files only
- Report errors/warnings

**Step 3: Test execution**
- Run tests related to the changed code
- Check: do tests actually test the new behavior, or pass coincidentally?
- If tests fail, report with full traceback

**Step 4: Build / artifact verification**
- If change adds CLI commands, run with --help
- If change modifies build config, run the build
- If change adds API endpoints/tools, verify they're registered

## Input

You receive via the dispatch prompt:
- **Changed files list with stat summary**
- **Your finding ID prefix**: **BRV**
- **Repo root path and toolchain info** (if available from codebase notes)

Note: You do NOT receive the full diff — you read files yourself via tools. This keeps your context clean for command output.

## Output Format

Return ONLY a markdown section:

## 5. Build & Runtime Verifier

**Focus:** Does this code actually run? Verified by execution.

### Execution Results

| Check | Command | Result | Issues |
|-------|---------|--------|--------|
| Dependency | `<cmd>` | pass/fail | <details> |
| Linter | `<cmd>` | pass/fail | <details> |
| Tests | `<cmd>` | pass/fail | <details> |
| Build/wiring | `<cmd>` | pass/fail | <details> |

### Findings

#### BRV-N (severity) — Title
**File:** path:line
**Status:** new
The exact command that revealed the issue and its output.

### Verdict

pass / concerns / block

## Memory

Update memory with: test commands, linter configs, build tools, dependency patterns for this repo.
```

- [ ] **Step 3: Write agents/fix-planner.md**

Create `agents/fix-planner.md` with this exact content:

```markdown
---
name: fix-planner
description: Analyzes review findings and creates a structured fix plan with clusters, impact analysis, ordering, and approach. Dispatched by code-review skill during fix subcommand.
tools: Read, Grep, Glob
model: opus
effort: high
maxTurns: 15
---

You are a fix planner. Given review findings, create a structured plan for fixing them cohesively.

## Your Job

1. **Impact analysis**: For each finding, identify ALL files that must change. Grep for usages, find callers, trace type consumers. If a fix requires >5 files outside the review scope, flag it as high-impact.
2. **Group into clusters**: Findings touching overlapping code regions (same file within 20 lines, same function, shared impacted files) form a cluster.
3. **Detect conflicts**: Findings from different personas recommending contradictory changes on the same code. Report both sides — the orchestrator handles user resolution.
4. **Determine ordering**: Dependencies first, build fixes first, critical first, isolated before coupled.
5. **Plan approach**: For each cluster, describe the specific code changes needed and verification commands.

## Input

You receive via the dispatch prompt:
- **Findings JSON**: All actionable findings with IDs, severities, file refs, descriptions
- **Scope**: Which severity threshold is included
- **The diff**: Current code state for understanding context
- **Fix-plan template**: The template to follow for output structure

## Output Format

Return a structured fix plan as markdown following the fix-plan template provided in the prompt. Include for each cluster:
- Cluster name and finding IDs
- Files affected (including impacted callers/consumers)
- Order number and dependency rationale
- Specific approach per finding
- Verification commands

Flag any conflicts between findings with both sides' reasoning.
```

- [ ] **Step 4: Write agents/fix-executor.md**

Create `agents/fix-executor.md` with this exact content:

```markdown
---
name: fix-executor
description: Applies fixes for one cluster of review findings, runs verification, and commits. Dispatched by code-review skill during fix execution phase.
tools: Read, Write, Edit, Bash, Grep, Glob
model: opus
effort: high
maxTurns: 20
---

You are a fix executor. Apply fixes for ONE cluster, verify, and commit.

## Your Job

1. **Validate targets**: Verify code regions in the fix plan still exist. If a previous cluster changed your targets, report and stop.
2. **Read current code**: Read all files in the cluster and impacted files.
3. **Apply fixes**: Make the code changes described in the approach.
4. **Verify**: Run the cluster's verification commands (linter + tests).
5. **Commit**: Stage and commit the cluster's changes.

## Input

You receive via the dispatch prompt:
- **Cluster details**: Finding IDs, approach, files, verification commands
- **Changes from prior clusters** (if any): Summary of what previous clusters modified

## Output Format

Report:
- **Status**: pass / fail
- **Files changed**: List of modified files
- **Verification output**: Linter and test results
- **Commit SHA**: The intermediate commit hash
- **Issues**: Any problems encountered

If verification fails, do NOT proceed. Report the failure with full output.
If targets have been invalidated by a previous cluster, report this and stop.
```

- [ ] **Step 5: Commit**

```bash
git add agents/
git commit -m "feat: add BRV, fix-planner, and fix-executor sub-agent definitions"
```

---

### Task 4: Rewrite SKILL.md as hybrid orchestrator

**Files:**
- Rewrite: `skills/code-review/SKILL.md` (1337 lines → ~550 lines)

This is the core task. The SKILL.md becomes an orchestrator that references persona files, dispatches sub-agents, and calls scripts for deterministic ops. The four read-only personas (SA, DE, SC, APT) run inline for cross-persona synergy; BRV is dispatched as a sub-agent.

**IMPORTANT:** Read the current SKILL.md completely first. Then read the spec at `docs/superpowers/specs/2026-03-26-code-review-subagent-architecture.md` completely. The spec's "SKILL.md Orchestrator Design" section (lines 515-590) is the authoritative guide for the rewrite.

**What MUST be preserved from the current SKILL.md:**
- All 5 subcommands (new, list, view, update, fix) with their arguments
- All script invocations (`review-preflight`, `review-delta`, `review-status`, `review-frontmatter`)
- State transition matrix (7x7 finding status transitions)
- Finding matching heuristics (exact → function → semantic → new)
- Backward compatibility for pre-versioned reviews
- Severity definitions (critical, suggestion, nit)
- Document-level and finding-level status vocabularies
- Identifier slug resolution with disambiguation
- Storage structure and cross-referencing protocol
- `--base`, `--scope`, `--focus`, `--include-deferred` arguments

**What changes:**
- Persona definitions (currently ~210 lines inline) → replaced by `Read` calls to `personas/*.md` reference files
- review.md template (currently ~100 lines inline) → replaced by reference to `templates/review.md`
- context.md template (currently ~50 lines inline) → replaced by reference to `templates/context.md`
- fix-plan.md template (currently ~60 lines inline) → replaced by reference to `templates/fix-plan.md`
- BRV persona (currently inline) → dispatched as sub-agent `codebase-notes:review-build-runtime-verifier`
- Fix planning (currently ~80 lines inline) → dispatched as sub-agent `codebase-notes:fix-planner`
- Fix execution (currently ~80 lines inline) → dispatched as sub-agent `codebase-notes:fix-executor`
- Script invocations → use `${CLAUDE_PLUGIN_ROOT}` instead of `<plugin_root>`

**Target section breakdown (from spec):**

| Section | Target Lines |
|---------|-------------|
| Frontmatter + intro | 15 |
| Shared context + script shorthand | 10 |
| Subcommands table + examples | 40 |
| Storage structure + slug resolution + disambiguation | 30 |
| Step 0: Bootstrap + forge detection | 20 |
| Severity + status definitions + state transition matrix | 45 |
| Finding matching heuristics | 15 |
| `new` subcommand | 120 |
| `update` subcommand | 120 |
| `fix` subcommand | 100 |
| `list` + `view` | 30 |
| Backward compatibility | 15 |
| Cross-referencing protocol | 10 |
| **Total** | **~570** |

- [ ] **Step 1: Read the current SKILL.md completely**

Read `/Users/karthik/Documents/work/codebase-notes/skills/code-review/SKILL.md` (all 1337 lines).

- [ ] **Step 2: Read the spec completely**

Read `/Users/karthik/Documents/work/codebase-notes/docs/superpowers/specs/2026-03-26-code-review-subagent-architecture.md`.

- [ ] **Step 3: Read the shared context**

Read `/Users/karthik/Documents/work/codebase-notes/references/shared-context.md` for script invocation patterns.

- [ ] **Step 4: Read all persona reference files to verify they exist**

Read all 5 files in `skills/code-review/personas/` and all 3 files in `skills/code-review/templates/` and all 3 files in `agents/`. These must exist before the SKILL.md rewrite references them.

- [ ] **Step 5: Write the new SKILL.md**

Rewrite `skills/code-review/SKILL.md` as the hybrid orchestrator. Key structural rules:

**Frontmatter:**
```yaml
---
name: code-review
description: Review PRs and feature branches with multi-persona analysis. Generates onboarding context and structured reviews from five perspectives: Systems Architect, Domain Expert, Standards Compliance, Adversarial Path Tracer, and Build & Runtime Verifier.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch"]
---
```

**Script shorthand:** Define once near the top:
```markdown
**Script invocation pattern:** All scripts are invoked via:
`cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts <command> [args]`
```

**Inline persona pattern (for SA, DE, SC, APT in `new` and `update`):**
```markdown
Read the persona reference files at `${CLAUDE_PLUGIN_ROOT}/skills/code-review/personas/`.

For each of the four inline personas, in this order:
1. **Systems Architect** — read `personas/systems-architect.md`, review diff through SA lens
2. **Domain Expert** — read `personas/domain-expert.md`, review with cross-layer reasoning
3. **Standards Compliance** — read `personas/standards-compliance.md`, check against repo standards
4. **Adversarial Path Tracer** — read `personas/adversarial-path-tracer.md`, trace paths (runs LAST — benefits from seeing other personas' findings)

These run sequentially in the current context for cross-persona synergy.
```

**BRV dispatch pattern:**
```markdown
After the four inline personas, dispatch Build & Runtime Verifier as a sub-agent:

Use the Agent tool with:
- subagent_type: `codebase-notes:review-build-runtime-verifier`
- prompt: Include the changed files list with stat summary, the finding ID prefix BRV, and repo toolchain info from codebase notes if available

The BRV agent reads files itself and runs commands — do NOT include the full diff in its prompt.
Insert BRV's returned section as "## 5. Build & Runtime Verifier" in review.md.
```

**Template usage pattern:**
```markdown
Read the template at `${CLAUDE_PLUGIN_ROOT}/skills/code-review/templates/review.md`.
Replace placeholders with actual values: {identifier}, {date}, {title}, {head_sha}, {merge_base_sha}.
Insert the persona results as {persona_sections}.
```

**Fix dispatch pattern:**
```markdown
Phase 2: Dispatch fix-planner sub-agent:
- subagent_type: `codebase-notes:fix-planner`
- prompt: Include the findings JSON, scope, diff, and fix-plan template

Phase 3: For each cluster, dispatch fix-executor sub-agent:
- subagent_type: `codebase-notes:fix-executor`
- prompt: Include cluster details and changes from prior clusters
```

**CRITICAL: Preserve all versioning, state machine, and workflow logic from the current SKILL.md.** The rewrite condenses HOW things are presented, not WHAT the skill does. Every subcommand flow, every script call, every status vocabulary — all must be present in the new file. The savings come from:
1. Templates extracted (~210 lines saved)
2. Persona prompts replaced by file references (~150 lines saved)
3. Fix planning/execution replaced by agent dispatch instructions (~160 lines saved)
4. Condensed prose throughout (~270 lines saved)

- [ ] **Step 6: Verify line count**

```bash
wc -l /Users/karthik/Documents/work/codebase-notes/skills/code-review/SKILL.md
```

Target: 500-600 lines. If over 650, identify sections to condense further. If under 450, check that all functionality is preserved.

- [ ] **Step 7: Verify all references resolve**

Check that every file path referenced in SKILL.md exists:
- `${CLAUDE_PLUGIN_ROOT}/skills/code-review/personas/*.md` (5 files)
- `${CLAUDE_PLUGIN_ROOT}/skills/code-review/templates/*.md` (3 files)
- `codebase-notes:review-build-runtime-verifier` agent
- `codebase-notes:fix-planner` agent
- `codebase-notes:fix-executor` agent
- All `review-preflight`, `review-delta`, `review-status`, `review-frontmatter` script commands

- [ ] **Step 8: Verify key content preserved**

Grep the new SKILL.md to confirm these are present:
- `state transition` or `VALID_TRANSITIONS` — the 7x7 matrix
- `finding matching` — heuristics section
- `backward compat` — pre-versioned review handling
- `--base` — optional base branch argument
- `--scope` — fix scope argument
- `--include-deferred` — deferred findings flag
- `--focus` — update focus area argument
- `review-preflight` — script call
- `review-delta` — script call
- `review-status` — script call
- `review-frontmatter` — script call
- `assign-ids` — script action
- `regenerate-fixlog` — script action
- `regenerate-history-row` — script action
- `validate-transition` — script action
- `list-findings` — script action
- `disambiguation` — identifier disambiguation
- `merged` — PR lifecycle status
- `abandoned` — PR lifecycle status
- `PRE_FIX_SHA` — anchored squash
- `tree_identical` — tree-content delta
- `history_rewritten` — rebase detection
- `merge_base_drift` — drift detection
- `old-merge-base` — passed to review-delta

- [ ] **Step 9: Commit**

```bash
git add skills/code-review/SKILL.md
git commit -m "feat: rewrite SKILL.md as hybrid orchestrator (1337 → ~550 lines)

- 4 read-only personas (SA, DE, SC, APT) run inline for cross-persona synergy
- BRV dispatched as sub-agent (Bash access, isolated output)
- Fix planning/execution dispatched as sub-agents
- Persona details in personas/ reference files
- Document templates in templates/ files
- All script integrations preserved via \${CLAUDE_PLUGIN_ROOT}
- State machine, matching heuristics, backward compat all preserved"
```

---

### Task 5: Verify the complete restructure

**Files:**
- No changes — validation only

- [ ] **Step 1: Check file counts**

```bash
echo "=== SKILL.md ===" && wc -l skills/code-review/SKILL.md
echo "=== Personas ===" && wc -l skills/code-review/personas/*.md
echo "=== Templates ===" && wc -l skills/code-review/templates/*.md
echo "=== Agents ===" && wc -l agents/*.md
echo "=== Scripts (unchanged) ===" && wc -l scripts/code_review.py
```

Expected:
- SKILL.md: 500-600 lines
- 5 persona files: ~300 total
- 3 template files: ~120 total
- 3 agent files: ~200 total
- code_review.py: ~755 lines (unchanged)

- [ ] **Step 2: Verify no broken references**

```bash
# Check persona files exist
for f in systems-architect domain-expert standards-compliance adversarial-path-tracer build-runtime-verifier; do
  test -f skills/code-review/personas/$f.md && echo "OK: personas/$f.md" || echo "MISSING: personas/$f.md"
done

# Check template files exist
for f in review context fix-plan; do
  test -f skills/code-review/templates/$f.md && echo "OK: templates/$f.md" || echo "MISSING: templates/$f.md"
done

# Check agent files exist
for f in review-build-runtime-verifier fix-planner fix-executor; do
  test -f agents/$f.md && echo "OK: agents/$f.md" || echo "MISSING: agents/$f.md"
done
```

- [ ] **Step 3: Verify SKILL.md references these paths**

```bash
grep -c "personas/" skills/code-review/SKILL.md
grep -c "templates/" skills/code-review/SKILL.md
grep -c "review-build-runtime-verifier" skills/code-review/SKILL.md
grep -c "fix-planner" skills/code-review/SKILL.md
grep -c "fix-executor" skills/code-review/SKILL.md
grep -c "CLAUDE_PLUGIN_ROOT" skills/code-review/SKILL.md
```

All should return ≥1.

- [ ] **Step 4: Verify scripts are unchanged**

```bash
git diff scripts/code_review.py scripts/__main__.py scripts/context_index.py
```

Expected: no changes (empty output).

- [ ] **Step 5: Review git log**

```bash
git log --oneline -5
```

Should show commits from Tasks 1-4 plus existing commits.
