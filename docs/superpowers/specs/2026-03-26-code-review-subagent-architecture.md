# Code Review Skill: Hybrid Architecture Spec

**Date:** 2026-03-26
**Status:** Approved
**Goal:** Simplify SKILL.md from 1337 → ~550 lines via hybrid approach: 4 read-only personas stay inline (cross-persona synergy), BRV + fix agents dispatched as sub-agents (tool isolation), templates and persona references extracted to files, scripts handle deterministic ops.

---

## Design Rationale

A multi-persona review found that full sub-agent extraction (all 5 personas as agents) has critical DX tradeoffs:
- **Cross-persona synergy lost** — personas can't see each other's findings when isolated
- **No speed gain** — agent setup overhead + BRV dominates wall-clock time either way
- **3-5x cost increase** — diff duplicated into 5 agent prompts
- **Classification ambiguity** — `update` flow requires semantic matching that isolated agents can't do

The hybrid approach keeps the strengths (shared context, streaming UX, no cost multiplier) while extracting only what genuinely benefits from isolation.

---

## Architecture Overview

```
SKILL.md (orchestrator + 4 inline personas, ~550 lines)
  ├── Gathers context (diff, notes, standards)
  ├── Calls scripts for deterministic ops
  ├── Runs SA, DE, SC, APT personas inline (shared context, cross-persona synergy)
  ├── Dispatches BRV as sub-agent (needs Bash, verbose output isolated)
  ├── Dispatches fix-planner / fix-executor as sub-agents
  ├── Assembles final documents
  └── Manages user interaction (conflicts, approval)

personas/ (5 reference files, ~300 lines total)
  ├── Read by SKILL.md for inline persona instructions
  └── NOT dispatched as agents (except BRV)

agents/ (3 sub-agents, ~200 lines total)
  ├── review-build-runtime-verifier (Bash access, isolated output)
  ├── fix-planner (read-only analysis)
  └── fix-executor (Write/Edit/Bash for code changes)

templates/ (3 files, ~120 lines total)
  ├── review.md skeleton
  ├── context.md skeleton
  └── fix-plan.md skeleton

scripts/code_review.py (existing, ~760 lines)
  ├── review-preflight
  ├── review-delta
  ├── review-status
  └── review-frontmatter
```

## File Structure

```
codebase-notes/                                   # plugin root
├── agents/                                       # auto-discovered sub-agents (3 only)
│   ├── review-build-runtime-verifier.md
│   ├── fix-planner.md
│   └── fix-executor.md
├── skills/
│   └── code-review/
│       ├── SKILL.md                              # orchestrator + 4 inline personas
│       ├── personas/                             # reference files read by SKILL.md
│       │   ├── systems-architect.md
│       │   ├── domain-expert.md
│       │   ├── standards-compliance.md
│       │   ├── adversarial-path-tracer.md
│       │   └── build-runtime-verifier.md         # also used as agent system prompt source
│       └── templates/
│           ├── review.md
│           ├── context.md
│           └── fix-plan.md
├── scripts/
│   ├── code_review.py                            # deterministic helpers (existing)
│   ├── __main__.py
│   └── ...
```

### Why This Split

| Component | Location | Reasoning |
|-----------|----------|-----------|
| SA, DE, SC, APT | Inline in SKILL.md (read persona references) | Cross-persona synergy — APT traces paths SA flagged, DE builds on SC's naming findings |
| BRV | Sub-agent in agents/ | Needs Bash tool, produces verbose test/linter output that would pollute main context |
| Fix Planner | Sub-agent in agents/ | Benefits from clean context — analyzes findings without main conversation noise |
| Fix Executor | Sub-agent in agents/ | Needs Write/Edit/Bash, runs per-cluster in isolation |
| Persona details | Reference files in personas/ | Maintainability — update one persona without touching SKILL.md |
| Templates | Separate files in templates/ | Keeps SKILL.md lean, templates are filled programmatically |

---

## Sub-Agent Definitions (3 agents)

All agents use: `model: opus`, `effort: high`

### agents/review-build-runtime-verifier.md

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

### agents/fix-planner.md

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

## Output Format

Return a structured fix plan as markdown following the fix-plan template provided in the prompt.
```

### agents/fix-executor.md

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
- **Files changed**: List
- **Verification output**: Linter and test results
- **Commit SHA**: The intermediate commit hash
- **Issues**: Any problems encountered

If verification fails, do NOT proceed. Report the failure with full output.
```

---

## Persona Reference Files (5 files)

These are NOT agent definitions — they're reference documents read by SKILL.md. Each contains the persona's focus areas, review questions, and output format. SKILL.md reads them and uses the content inline.

### personas/systems-architect.md

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

### personas/domain-expert.md

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

### personas/standards-compliance.md

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

### personas/adversarial-path-tracer.md

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

### personas/build-runtime-verifier.md

```markdown
# Build & Runtime Verifier (BRV)

**Focus:** Does this code actually run? Verified by execution, not reading.

This persona is dispatched as a sub-agent (needs Bash tool access).
See agents/review-build-runtime-verifier.md for the agent definition.

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

---

## Templates (3 files)

### templates/review.md

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

### templates/context.md

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

### templates/fix-plan.md

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

---

## SKILL.md Orchestrator Design (~550 lines)

### Section Breakdown

| Section | Lines | Content |
|---------|-------|---------|
| Frontmatter + intro | 15 | Name, description, allowed-tools (includes Agent) |
| Shared context + script shorthand | 10 | Reference to shared-context.md, `${CLAUDE_PLUGIN_ROOT}` pattern |
| Subcommands table + examples | 40 | All 5 subcommands with args and examples |
| Storage structure + slug resolution | 30 | Directory layout, slug rules, disambiguation |
| Step 0: Bootstrap + forge detection | 20 | Venv check, repo-id, forge CLI |
| Severity + status definitions | 25 | Finding-level + document-level status enums, severity definitions |
| **`new` subcommand** | 120 | Resolve → diff → context → read persona refs → run 4 inline personas → dispatch BRV agent → assemble review.md |
| **`update` subcommand** | 120 | Preflight → delta → read persona refs → run 4 inline personas with prior findings context → dispatch BRV → classify → update docs |
| **`fix` subcommand** | 100 | Preflight → list findings → dispatch planner → resolve conflicts → dispatch executors → squash → update docs |
| `list` + `view` | 30 | Read metadata, present tables |
| State transition matrix | 20 | 7x7 matrix (reference for inline classification) |
| Finding matching heuristics | 15 | Exact → function → semantic → new |
| Backward compatibility | 15 | Pre-versioned review migration |
| Cross-referencing protocol | 10 | Notes linkage |
| **Total** | **~570** |

### How Inline Personas Work

For the `new` and `update` subcommands, SKILL.md reads the persona reference files and uses them as inline instructions:

```markdown
### Step 5: Write review.md — Multi-Persona Review

Read the persona reference files at `${CLAUDE_PLUGIN_ROOT}/skills/code-review/personas/`.

For each of the four inline personas (Systems Architect, Domain Expert, Standards Compliance, Adversarial Path Tracer):
1. Read the persona's reference file for focus areas and review questions
2. Review the diff through that persona's lens
3. Write the findings section with the persona's ID prefix (SA, DE, SC, APT)

These four run sequentially in the current context — they benefit from seeing each other's findings. The Adversarial Path Tracer runs LAST so it can trace paths flagged by other personas.

After the four inline personas complete, dispatch the Build & Runtime Verifier as a sub-agent:

Agent(subagent_type="codebase-notes:review-build-runtime-verifier", prompt="<changed files list + stat summary + repo toolchain info>")

The BRV returns its section. Insert it as section 5 of review.md.
```

### How Fix Flow Works

```markdown
### Fix Subcommand Flow

**Phase 0: Pre-flight** (script calls)
1. Run `review-preflight --check-fix` — validates branch match, clean tree
2. Check for existing fix-plan.md

**Phase 1: Gather findings** (script call)
3. Run `review-status --action list-findings` — get JSON of all findings
4. Filter by --scope (critical / default / all)

**Phase 2: Plan** (sub-agent)
5. Dispatch fix-planner agent with findings JSON + diff
6. Planner returns structured fix-plan.md
7. Present plan to user, resolve conflicts interactively

**Phase 3: Execute** (sub-agents, sequential)
8. Record PRE_FIX_SHA
9. For each cluster:
   a. Dispatch fix-executor with cluster details + prior cluster changes
   b. If fail → ask user (retry/skip/stop)
   c. If pass → continue
10. Squash: `git reset --soft $PRE_FIX_SHA && git commit`

**Phase 4: Update docs** (script calls)
11. Update finding statuses in review.md
12. Run `review-status --action regenerate-fixlog`
13. Run `review-frontmatter --action update --set last_fix_sha=<sha>`
```

---

## Key Differences from Full Sub-Agent Approach

| Aspect | Full Sub-Agent | Hybrid (this spec) |
|--------|---------------|---------------------|
| Cross-persona synergy | Lost (isolated contexts) | Preserved (shared context) |
| Execution speed | Parallel but with setup overhead | Streaming, BRV parallel |
| Token cost | ~3-5x (diff duplicated 5x) | ~1.3x (only BRV gets separate context) |
| User visibility | Silence then wall of text | Continuous streaming |
| Classification in update | Ambiguous (personas can't match) | Clear (inline personas do matching) |
| Maintainability | Best (each persona independent file) | Good (persona refs separate, SKILL.md reads them) |
| BRV isolation | Yes | Yes (sub-agent) |
| Fix isolation | Yes | Yes (sub-agents) |

---

## Status Vocabulary

**Document-level** (hyphenated, set by orchestrator):
`review-in-progress`, `reviewed`, `review-updated`, `fixes-applied`, `merged`, `abandoned`

**Finding-level** (single words, set during classification):
`new`, `persists`, `resolved`, `missed`, `regressed`, `fixed`, `deferred`

State transitions enforced by `review-status --action validate-transition` script.

---

## Migration from Current Implementation

1. Create `agents/` directory with 3 agent files (BRV, fix-planner, fix-executor)
2. Create `skills/code-review/personas/` with 5 reference files
3. Create `skills/code-review/templates/` with 3 template files
4. Rewrite `skills/code-review/SKILL.md` as hybrid orchestrator (~550 lines)
5. Existing `scripts/code_review.py` — unchanged
6. Existing `scripts/__main__.py` — unchanged
7. Existing `scripts/context_index.py` — unchanged

No changes to scripts or infrastructure — only the skill layer is restructured.

---

## Review Findings Addressed

From the multi-persona spec review (30 findings total):

| Finding | Resolution |
|---------|------------|
| PA-1: subagent_type syntax | Only 3 agents now; verify `codebase-notes:review-build-runtime-verifier` syntax |
| PA-2: `background: false` invalid | Removed from spec — not a frontmatter field |
| DX-1: Parallel may be slower | 4 personas inline (no agent overhead), only BRV dispatched |
| DX-2: Context isolation kills synergy | 4 personas share context, only BRV isolated |
| DX-3: 3-5x cost | ~1.3x cost (only BRV duplicates context) |
| DX-4: No visibility | 4 personas stream inline, only BRV is async |
| DX-8: Memory noise | Memory only on BRV (useful for test/build commands) |
| OD-1: No diff size budget | BRV gets stat summary only (reads files itself); inline personas use existing large-diff strategy |
| OD-4/OD-11: Classification ambiguous | Inline personas do their own classification with full context of prior findings |
| OD-8: 5x diff duplication | Only BRV gets separate context (stat summary, not full diff) |
