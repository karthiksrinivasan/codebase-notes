# Codebase Notes v2 — Design Spec

## Summary

Complete overhaul of the codebase-notes skill as a **standalone, self-contained skill** with no dependencies on other skills. Changes:

- **Centralized, repo-keyed notes** at `~/.claude/repo_notes/<org>--<repo>/` accessible from any clone
- **Python CLI scripts** (`uv run python -m scripts <cmd>`) for all deterministic operations, auto-bootstrapped via uv
- **Commit history knowledge graph** — author-grouped, path-scoped, Claude-summarized commit notes
- **Cron-based auto-updates** — background staleness detection + Claude-powered note refresh
- **Richer content rules** — context-dependent capture (what+how, what+why, what+when) with mandatory diagrams
- **Self-contained diagram rendering** — built-in Excalidraw renderer, no external skill dependency

---

## 1. Centralized Notes Location

### Directory Structure

```
~/.claude/repo_notes/
└── <repo_id>/
    ├── .repo_paths              # known clone paths (for cron)
    ├── update-log.md            # auto-update history
    ├── notes/
    │   ├── 00-overview.md
    │   ├── RULES.md
    │   ├── 01-topic/
    │   │   ├── index.md
    │   │   ├── 01-subtopic.md
    │   │   ├── 01-subtopic.excalidraw
    │   │   ├── 01-subtopic.png
    │   │   └── ...
    │   └── ...
    └── commits/
        ├── <author>/
        │   ├── <path-slug>.md       # e.g., src-api.md
        │   └── ...
        └── ...
```

### Repo ID Resolution

Derived from `git remote get-url origin`:

| Remote URL | Repo ID |
|-----------|---------|
| `git@github.com:anthropics/claude-code.git` | `anthropics--claude-code` |
| `https://github.com/org/repo.git` | `org--repo` |
| `git@gitlab.com:org/sub/repo.git` | `org--sub--repo` |
| No remote (local-only) | `local--<dirname>--<path_hash>` |

Rules:
- Use `origin` remote only
- Strip host — only `org/repo` portion
- Replace `/` with `--`, strip `.git` suffix
- Nested groups (GitLab) flatten: `org/sub/repo` → `org--sub--repo`
- No remote: `local--<directory_name>--<first 8 chars of sha256(absolute_path)>` to avoid collisions

### Cross-Clone Access

Any clone of the same repo resolves to the same `repo_id`, so notes are shared. The skill always resolves the notes path via `uv run python -m scripts repo-id` before any read/write.

### Clone Path Registry (`.repo_paths`)

Each time the skill runs from a clone, the scaffold or staleness script appends the current working directory to `~/.claude/repo_notes/<repo_id>/.repo_paths` (deduplicated). This file is:
- Used by `--all-repos` cron mode to find a valid git checkout for each repo
- Validated on read: paths that no longer exist, aren't valid git repos, or whose `git remote get-url origin` no longer resolves to the expected repo_id are pruned automatically
- Written with file locking (`fcntl.flock`) to handle concurrent access from multiple Claude sessions

---

## 2. Python Scripts Package

### Location

```
~/.claude/skills/codebase-notes/scripts/
├── pyproject.toml
├── __init__.py
├── __main__.py          # CLI dispatcher
├── repo_id.py           # git remote → repo ID
├── scaffold.py          # create notes dir, copy RULES, generate skeleton
├── staleness.py         # check notes vs git, output report (with caching)
├── nav_links.py         # deterministically rebuild all navigation
├── render.py            # find & render .excalidraw → .png (self-contained)
├── commits.py           # git log → grouped by author/path → markdown
└── cron.py              # orchestrate auto-updates (with locking + timeouts)
```

### Auto-Setup

On first skill invocation, SKILL.md instructs Claude to run:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv sync
```

This installs the scripts package and its dependencies into a local `.venv`. Subsequent runs use `uv run python -m scripts <cmd>` from the `scripts/` directory.

The skill includes a check: if `scripts/.venv` doesn't exist, run setup first. This is a one-time operation.

Note: The scripts directory lives inside the skill directory (`~/.claude/skills/codebase-notes/scripts/`). Since the skill is symlinked from the development repo, the scripts are always at both locations. All script invocations use the absolute path `~/.claude/skills/codebase-notes/scripts/`.

### Lockfile Strategy

`uv.lock` is committed to the repo alongside `pyproject.toml`. This ensures reproducible installs across machines. The `uv sync` command reads the lockfile and installs exact pinned versions. If `uv.lock` is missing (e.g., first clone before it was added), `uv sync` generates it from `pyproject.toml` — this is safe since the dependency set is small and pinned in `pyproject.toml` with version bounds.

### CLI Interface

```
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts <command> [options]

Commands:
  repo-id                         Print the repo ID for the current git repo
  scaffold                        Create notes directory structure for current repo
  stale [--repo-id ID]            Check all notes for staleness, output report
  stale --all-repos               Check all repos in ~/.claude/repo_notes/
  nav [--repo-id ID]              Rebuild all navigation links deterministically
  render [--repo-id ID]           Find and render unrendered .excalidraw → .png
  commits --author=X [--since=4w] [--path=src/] [--repo-id ID]
                                  Generate commit history notes for author/path
  auto-update [--repo-id ID]      Run staleness check + spawn Claude for stale notes
  auto-update --all-repos         Auto-update all repos
  cron --install [--interval=6h]  Install launchd/crontab entry
  cron --uninstall                Remove cron entry
```

All commands auto-resolve `--repo-id` from the current git repo if not provided.

The `commits` command defaults to `--since=4w` if not specified, preventing unbounded output.

### Dependencies

Minimal — specified in `pyproject.toml`:
- `pyyaml` — for frontmatter parsing
- `Pillow` — for Excalidraw rendering (self-contained, no external skill needed)
- Standard library only for everything else: `subprocess`, `pathlib`, `json`, `re`, `argparse`, `datetime`, `hashlib`, `fcntl`

### Script Details

#### `repo_id.py`
- Parse `git remote get-url origin` via subprocess
- Handle SSH (`git@host:org/repo.git`) and HTTPS (`https://host/org/repo.git`) formats
- Fallback to `local--<dirname>--<hash>` if no remote
- Output: print repo ID string to stdout

#### `scaffold.py`
- Create `~/.claude/repo_notes/<repo_id>/notes/` and `commits/`
- Copy `RULES-template.md` → `RULES.md` (from skill's `references/` dir)
- Create empty `00-overview.md` skeleton with frontmatter
- Register current clone path in `.repo_paths`
- Idempotent — safe to run repeatedly

#### `staleness.py`
- Parse YAML frontmatter from all `.md` files in notes dir
- For each `git_tracked_paths` entry, run `git diff --name-only <commit> HEAD -- <path>`
- Output structured report:
  ```
  FRESH: 01-api/index.md (0 files changed)
  STALE: 02-models/index.md (7 files changed since abc1234)
    - src/models/user.py (modified)
    - src/models/auth.py (new)
    ...
  NO_TRACKING: 03-config/index.md (no git_tracked_paths in frontmatter)
  ```
- `--all-repos` mode: iterate `~/.claude/repo_notes/*/`, validate `.repo_paths`, skip repos with no valid clone path (with warning)
- **Caching**: Write staleness result to `~/.claude/repo_notes/<repo_id>/.staleness_cache` with timestamp. On subsequent runs within 10 minutes, return cached result instead of re-running git diffs. Use `--no-cache` to force fresh check.

#### `nav_links.py`
- Walk the notes directory tree
- For each `.md` file, compute correct Up/Prev/Next/Sub-topics links based on file position
- Matching: find lines starting with `> **Navigation:**` or `> **Sub-topics:**` (case-insensitive, whitespace-tolerant regex)
- If no navigation line found: insert one after the frontmatter block (after the closing `---`)
- If found: replace in-place
- Handle index.md files (get Sub-topics line) vs regular notes
- Idempotent — running twice produces same result
- Output: list of files modified

#### `render.py`
- **Self-contained renderer** — no dependency on excalidraw-diagram skill
- Built-in Python Excalidraw-to-PNG renderer using Pillow
- Find all `.excalidraw` files in notes dir
- For each, check if corresponding `.png` exists and is newer
- If not, render to PNG
- Report what was rendered
- Fallback: if rendering fails for a complex diagram, output a warning (not an error) and skip

#### `commits.py`
- Run `git log --format="%H|%an|%ae|%ad|%s" --since=<since> -- <path>`
- Default `--since=4w` if not specified
- Group commits by author
- Group each author's commits by path prefix (configurable depth, default: 2 levels)
- Output markdown files to `~/.claude/repo_notes/<repo_id>/commits/<author>/<path-slug>.md`
- Each file contains: frontmatter (author, path_filter, date_range), commit table, placeholder `## Summary` section for Claude to fill
- Claude will later read the raw note and add narrative summary + cross-references

#### `cron.py`
- **Install/uninstall**: Create/remove launchd plist (macOS) or crontab entry
- **Lock file**: `~/.claude/repo_notes/.cron.lock` — if lock exists and process is still running, skip this invocation
- **Per-repo timeout**: 10-minute timeout per Claude invocation. Kill and log if exceeded.
- **Max concurrent repos**: Process repos sequentially (not parallel) to avoid resource exhaustion
- **Max repos per run**: Process at most 5 stale repos per cron invocation. Prioritize by staleness severity (most changed files first). Remaining repos get picked up next run.
- **Claude invocation**: Use `claude -p "<prompt>" --allowedTools "Read,Write,Edit,Bash,Glob,Grep" -C ~/.claude/skills/codebase-notes/SKILL.md` from the repo's working directory
  - This runs Claude non-interactively with file write permissions
  - The `-C` flag loads the skill as context so Claude knows how to write notes
  - The prompt includes: which notes are stale, what files changed (actual file names from staleness report), and instructions to read the current note, check the diffs, and update
- **Logging**: Append to `~/.claude/repo_notes/cron.log` with timestamps, repo_id, outcome (success/timeout/error/skipped)

---

## 3. Commit History Knowledge Graph

### Structure

```
~/.claude/repo_notes/<repo_id>/commits/
├── alice/
│   ├── src-api.md           # Alice's work on src/api/
│   ├── src-models.md        # Alice's work on src/models/
│   └── ...
└── bob/
    ├── src-api.md
    └── ...
```

### Note Format

```markdown
---
author: alice
author_email: alice@company.com
path_filter: src/api/
date_range: 2026-02-01 to 2026-03-18
last_updated: 2026-03-18
---
# Alice — src/api/

> **See also:** [Bob's work on src/api/](../bob/src-api.md) | [API architecture notes](../../notes/03-api/index.md)

## Summary

[Claude-generated narrative: what Alice worked on, key changes, architectural decisions]

## Commits

| Date | Message | Files |
|------|---------|-------|
| 2026-03-15 | Refactor auth middleware to JWT | 4 files |
| 2026-03-10 | Add rate limiting to /users endpoint | 2 files |
| ... | ... | ... |
```

### Cross-Referencing

- Commit notes link to codebase notes for the same path (`../../notes/03-api/index.md`)
- Codebase notes can link back to commit history for "who changed this recently"
- Author notes within the same path cross-link (`../bob/src-api.md`)

### Generation Flow

1. `uv run python -m scripts commits --author=alice --since=4w --path=src/api/` generates raw markdown with commit table
2. Claude reads the raw note and adds the Summary section (narrative synthesis)
3. Claude adds cross-reference links to existing codebase notes

### Retention

Commit notes are append-only within their date range. When `--since` is used on a subsequent run, the script merges new commits into the existing file (deduplicating by commit hash). Old commit notes are not automatically deleted — the user can prune manually or the cron job can archive notes older than a configurable threshold (default: never).

---

## 4. Cron-Based Auto-Updates

### Setup

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts cron --install --interval=6h
```

This creates a launchd plist (macOS) or crontab entry:
- Runs every 6 hours (configurable via `--interval`)
- Executes `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts auto-update --all-repos`
- Logs to `~/.claude/repo_notes/cron.log`

### Auto-Update Flow

```
cron triggers
  → check lock file (~/.claude/repo_notes/.cron.lock)
    → if locked and process alive: skip, log "skipped: previous run still active"
    → if locked and process dead: remove stale lock, continue
  → acquire lock
  → scripts/cron.py
    → staleness.py --all-repos --no-cache
      → for each repo_id in ~/.claude/repo_notes/:
        → validate .repo_paths (prune missing dirs + verify remote matches repo_id)
        → if no valid clone path: warn and skip
        → run git diff checks from first valid clone
    → sort stale repos by severity (most changed files first)
    → take top 5 stale repos
    → for each stale repo:
      → construct prompt with:
        - list of stale notes
        - actual changed file names per note
        - instruction to read current note, check code changes, update note
      → spawn: claude -p "<prompt>" --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
               -C ~/.claude/skills/codebase-notes/SKILL.md
        (cwd = first valid clone path for this repo)
      → 10-minute timeout per repo
      → log outcome
  → release lock
```

### Skill-Internal Staleness (on every invocation)

When the skill activates (Step 0), before doing anything:

1. Run `uv run python -m scripts repo-id` to resolve notes path
2. Register current clone path in `.repo_paths`
3. Run `uv run python -m scripts stale` (uses 10-minute cache by default)
4. If stale notes exist, present report to user: "These notes are stale: ... Update them first?"
5. User chooses to update or proceed with stale notes

---

## 5. Content Rules (RULES.md Overhaul)

The current RULES-template.md captures "what" uniformly. The new version uses context-dependent capture rules.

### Capture Matrix

| Content Type | Capture | Example |
|-------------|---------|---------|
| Architecture decisions | **What + Why** — the decision and the reasoning/constraints behind it | "Uses event sourcing (why: audit trail is a legal requirement)" |
| Implementation patterns | **What + How** — the pattern and concrete usage with code references | "Rate limiting via token bucket — see `RateLimiter` class in `src/middleware/rate.py`" |
| Data flow | **What + Where** — the transformation and the files/services involved | "Request → AuthMiddleware → Router → Handler → DB. Auth in `middleware/auth.py`, routing in `api/routes.py`" |
| Configuration | **What + When** — the setting and when/why you'd change it | "`MAX_RETRIES=3` — increase for flaky external APIs, decrease for fast-fail local dev" |
| Integration points | **What + Who** — the boundary and what's on both sides | "gRPC boundary between agent-service (Go) and model-service (Python)" |
| Error handling | **What + What-If** — the happy path and failure modes | "Circuit breaker on external API calls — opens after 5 failures, half-open retry after 30s" |
| Lifecycle/Deployment | **What + When** — the process and its triggers/schedule | "DB migrations run on deploy via `alembic upgrade head` — must complete before app starts" |
| Schemas/Models | **What + Constraints** — the shape and validation rules | "User model: email unique, password bcrypt hashed, created_at auto-set" |

### How Claude Selects the Right Rule

Notes contain mixed content types. The capture matrix is not "pick one per note" — it's "apply the right lens to each paragraph." The RULES.md will include concrete examples showing a single note that uses multiple capture strategies:

```markdown
## Authentication Middleware

**Architecture decision (What + Why):**
JWT-based stateless auth, replacing session cookies.
Why: horizontal scaling requirement — sessions required sticky sessions or shared Redis.

**Implementation pattern (What + How):**
Middleware chain in `src/middleware/auth.py`. `JWTValidator` class decodes token,
`PermissionChecker` validates scopes. Applied via `@require_auth(scopes=["read"])` decorator.

**Error handling (What + What-If):**
Expired tokens return 401 with `token_expired` error code. Malformed tokens return 401
with `invalid_token`. Rate-limited after 10 failed attempts per IP (429).
```

### Diagram Rules (Enhanced)

Every note MUST include at least one Excalidraw diagram. The diagram type should match the content:

| Content Type | Diagram Style |
|-------------|--------------|
| Architecture decisions | Before/after comparison or decision tree |
| Data flow | Pipeline/sequence diagram with transformation labels |
| Integration points | Boundary diagram showing both sides + protocol |
| Error handling | State machine (happy path + failure modes) |
| Lifecycle | Timeline or swimlane |
| Overview | Hub-and-spoke or layered architecture |

### Anti-Patterns (Explicit)

The RULES.md should explicitly call out what NOT to write:

- No "this module handles..." without saying HOW or WHY
- No listing files without saying what's INTERESTING about them
- No describing config fields without saying WHEN you'd change them
- No architecture diagrams that are just labeled boxes with no arrows showing flow
- No "see code for details" — if it's worth mentioning, capture the insight
- No prose-heavy explanations where a table would be clearer
- No copying docstrings or README content verbatim — synthesize and add insight

---

## 6. SKILL.md Changes

### Standalone Design

This skill is **self-contained**. It does NOT depend on:
- `excalidraw-diagram` skill (rendering is built into `scripts/render.py`)
- Any other installed skill or plugin
- Any external service or API

The only external dependencies are:
- `git` (for repo operations)
- `uv` (for Python script management)
- `claude` CLI (for cron auto-updates only)

### What Gets Removed

- All inline bash snippets for staleness checking (→ `scripts/staleness.py`)
- All inline bash for navigation link management (→ `scripts/nav_links.py`)
- The manual repo-root-relative path resolution (→ `scripts/repo_id.py`)
- Batch rendering bash loops (→ `scripts/render.py`)
- References to `excalidraw-diagram` skill for rendering
- Default `docs/notes/` location — replaced with centralized `~/.claude/repo_notes/`

### What Gets Added

- Auto-setup section: check for `.venv`, run `uv sync` if missing
- Script invocation instructions: `uv run python -m scripts <cmd>` for each operation
- Centralized path resolution: always start with `repo-id` to find notes
- Commit history section: how to generate and summarize commit notes
- Updated content rules pointing to the new capture matrix
- Cron setup instructions
- Migration section for v1 → v2

### What Stays the Same

- Core philosophy (notes as primary context, knowledge graph, diagrams argue)
- Context priming protocol (read notes → fall back to code → update notes)
- Explore agent dispatching pattern
- Note template structure (with updated frontmatter for centralized paths)
- Parallelization patterns
- Knowledge Map concept

---

## 7. Auto-Setup Flow

On first skill invocation for a repo:

```
1. Check: does scripts/.venv exist?
   NO  → cd ~/.claude/skills/codebase-notes/scripts && uv sync
   YES → continue

2. Run: uv run python -m scripts repo-id
   → prints e.g. "anthropics--claude-code"
   → registers current clone path in .repo_paths

3. Check: does ~/.claude/repo_notes/<repo_id>/notes/ exist?
   NO  → uv run python -m scripts scaffold
         (creates dirs, copies RULES.md, creates 00-overview.md skeleton)
   YES → uv run python -m scripts stale
         (check freshness, present report)

4. Proceed with normal skill flow (Phase 1 or resume)
```

---

## 8. v1 → v2 Migration

### Detection

When the skill activates and finds notes at the old location (`{repo_root}/docs/notes/` or other common paths), it should:

1. Detect existing v1 notes by checking:
   - `docs/notes/00-overview.md`
   - `notes/00-overview.md`
   - `docs/knowledge/00-overview.md`
2. If found, inform the user: "Found existing notes at `docs/notes/`. Migrate to centralized location at `~/.claude/repo_notes/<repo_id>/notes/`?"

### Migration Script

```bash
uv run python -m scripts migrate --from docs/notes/
```

This:
- Copies all `.md`, `.excalidraw`, `.png` files to the centralized location
- Updates internal relative links that reference repo-relative paths
- Preserves all frontmatter
- Does NOT delete the old directory (user decides)
- Reports any links that couldn't be automatically updated

### Fallback

If the user declines migration, the skill works with notes at the old location for that session. The skill does not force migration — it's opt-in.

---

## 9. Excalidraw Rendering (Self-Contained)

### Built-in Renderer

`scripts/render.py` includes a self-contained Excalidraw JSON → PNG renderer using Pillow. It handles:

- Rectangles, ellipses, diamonds, lines, arrows
- Text elements (bound to shapes or free-standing)
- Basic styling: fill colors, stroke colors, font sizes
- Arrow bindings (start/end connections to shapes)

### Font Handling

The renderer bundles a monospace font (`DejaVu Sans Mono` or similar permissively-licensed font) in `scripts/fonts/`. Font selection:

| Excalidraw `fontFamily` | Rendered Font |
|--------------------------|---------------|
| 1 (Virgil/hand-drawn) | Bundled monospace (no hand-drawn font needed — `roughness: 0` means clean style) |
| 2 (Helvetica/normal) | System Arial/Helvetica with fallback to bundled monospace |
| 3 (Cascadia/code) | Bundled monospace |

Text bounding boxes are computed from actual font metrics (via `Pillow.ImageFont.getbbox`) before rendering, so labels are correctly sized to fit within their containing shapes. If a bundled font is missing or corrupt, the renderer falls back to Pillow's built-in bitmap font and logs a warning.

### Limitations

The built-in renderer handles ~90% of diagrams used in codebase notes (architecture boxes, arrows, labels). For complex diagrams (hand-drawn style, complex curves), it renders a best-effort approximation. This is acceptable because:
- Notes diagrams are architectural/structural, not artistic
- Text fallback is always present below each diagram
- Font metrics are computed from actual fonts, so text sizing is accurate

### Style Defaults

- `roughness: 0` (clean/modern lines)
- `fontFamily: 3` (monospace)
- White background
- Semantic colors: blue for primary components, green for data stores, orange for external services, red for error paths

---

## 10. File Inventory

### New Files to Create

| File | Purpose |
|------|---------|
| `scripts/pyproject.toml` | uv project config with pyyaml + Pillow dependencies |
| `scripts/__init__.py` | Package marker |
| `scripts/__main__.py` | CLI dispatcher (argparse) |
| `scripts/repo_id.py` | Git remote → repo ID resolution |
| `scripts/scaffold.py` | Create centralized notes directory |
| `scripts/staleness.py` | Freshness checking with caching |
| `scripts/nav_links.py` | Deterministic navigation rebuilding |
| `scripts/render.py` | Self-contained Excalidraw → PNG renderer |
| `scripts/fonts/DejaVuSansMono.ttf` | Bundled monospace font for diagram text rendering |
| `scripts/commits.py` | Commit history extraction and grouping |
| `scripts/cron.py` | Cron installation and auto-update orchestration |
| `scripts/migrate.py` | v1 → v2 notes migration |

### Files to Modify

| File | Changes |
|------|---------|
| `SKILL.md` | Complete rewrite: replace bash with script calls, add auto-setup, centralized paths, commits section, migration, standalone rendering |
| `references/RULES-template.md` | Overhaul: capture matrix with examples, enhanced diagram rules, explicit anti-patterns, mixed-content-type examples |

---

## 11. Open Questions (Resolved)

| Question | Decision |
|---------|----------|
| Where do notes live? | `~/.claude/repo_notes/<repo_id>/` |
| How is repo identified? | `origin` remote, `org--repo` format, `local--<dir>--<hash>` fallback |
| What does Python handle? | All deterministic ops: paths, staleness, nav, render, commits, cron |
| What does Claude handle? | Content writing, summarization, diagram JSON, exploration decisions |
| How are notes auto-updated? | Cron (every 6h) + skill-internal staleness check on invocation |
| How are scripts bootstrapped? | `uv sync` on first run, detected by absence of `.venv` |
| What content rules apply? | Context-dependent capture matrix (what+how, what+why, etc.) |
| How do commits fit? | Separate `commits/` tree, author-grouped, path-scoped, cross-referenced |
| External skill dependencies? | None — fully standalone, self-contained rendering |
| v1 migration? | Opt-in migration script, old location works as fallback |
| Cron safety? | Lock file, 10-min timeout per repo, max 5 repos per run, sequential |
| Clone path staleness? | Validated and pruned on every read of `.repo_paths` (includes remote verification) |
| Staleness check latency? | 10-minute cache, `--no-cache` to force fresh |
| Commit retention? | Append-only, no auto-deletion, manual pruning |
| `--since` default? | 4 weeks for commits command |
| Font handling? | Bundled monospace font, system fallback for Helvetica, Pillow bitmap as last resort |
| Lockfile strategy? | `uv.lock` committed to repo for reproducible installs |
