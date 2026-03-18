---
name: codebase-notes
description: Generate, explore, and maintain a hierarchical knowledge base of structured notes for any codebase. Notes are stored centrally at ~/.claude/repo_notes/<repo_id>/ and shared across all clones of the same repo. Use this skill when the user wants to understand a codebase, create documentation notes, explore a repo progressively, build a knowledge graph, or asks to "learn about this codebase", "create notes", "explore this repo", "document this project", or "help me understand this code". Also triggers for requests to update existing notes, add diagrams, dive deeper into specific areas, or when any agent needs codebase context. On activation, always run Step 0 to resolve the notes path and check for existing notes.
---

# Codebase Notes

Build and maintain a hierarchical knowledge base that helps humans progressively understand a codebase. Notes are structured as an explorable knowledge graph — start broad, dive deep on demand, always navigable. Notes are stored centrally at `~/.claude/repo_notes/<repo_id>/notes/` and shared across all clones of the same repository.

---

## 1. Core Philosophy

**Notes are the primary context source.** When any agent (including you) needs to understand part of the codebase, notes should be read FIRST — before exploring code. Notes are pre-digested context that saves tokens and time. Code exploration is the fallback for when notes don't cover what's needed. Every time you learn something new from code, update the relevant note so the next agent doesn't have to re-explore.

**Notes are a knowledge graph, not a document dump.** Each note is a node with links to parent, siblings, and children. The user navigates by choosing what to explore next — you present options, they pick, you go deeper.

**Diagrams argue, text explains.** Every note gets at least one Excalidraw diagram showing architecture or data flow. Text supplements with tables, schemas, and key file references. Never use ASCII art for diagrams — always Excalidraw.

**Text must stand alone.** Diagrams enhance but don't replace text. Every architecture section needs enough written description that a reader with broken images still understands the system. A diagram without a text summary below it is incomplete.

**Capture what code can't tell you.** Focus on architecture, data flow, integration points, and design decisions. Don't repeat what `git log` or reading the source would tell you directly. Notes should answer "why is it built this way?" and "how do the pieces fit together?"

**Self-contained skill.** All deterministic operations (repo ID resolution, scaffolding, staleness checking, navigation links, rendering, commit history, cron) are handled by Python scripts bundled with this skill. Claude handles content writing, summarization, exploration decisions, and diagram JSON creation.

---

## 2. Script Invocation

All scripts are invoked with the same pattern. Always `cd` into the scripts directory first, then run via `uv`:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts <command> [args]
```

### Command Reference

| Command | Description | Example |
|---------|-------------|---------|
| `repo-id` | Print the repo ID for the current git repo | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id` |
| `scaffold` | Create notes directory structure for current repo | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts scaffold` |
| `stale` | Check all notes for staleness | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale` |
| `stale --all-repos` | Check staleness across all repos | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale --all-repos` |
| `stale --no-cache` | Force fresh staleness check (skip cache) | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale --no-cache` |
| `nav` | Rebuild all navigation links in notes | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav` |
| `render` | Render all .excalidraw files to .png | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render` |
| `commits` | Generate commit history notes | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts commits --author "Name"` |
| `auto-update` | Run staleness check + Claude update | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts auto-update` |
| `auto-update --all-repos` | Auto-update all repos | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts auto-update --all-repos` |
| `cron --install` | Install cron auto-update schedule | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts cron --install` |
| `cron --uninstall` | Remove cron auto-update schedule | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts cron --uninstall` |
| `migrate` | Migrate v1 notes to v2 centralized location | `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts migrate --from docs/notes` |

### Commits Command Options

| Flag | Default | Description |
|------|---------|-------------|
| `--author` | (required) | Author name or email to filter by |
| `--since` | `4w` | Time range (e.g., `2w`, `3m`, `1y`) |
| `--path` | (all paths) | Path filter for git log |
| `--repo-id` | (auto-detected) | Override repo ID |

### Cron Command Options

| Flag | Default | Description |
|------|---------|-------------|
| `--install` | — | Install the cron schedule |
| `--uninstall` | — | Remove the cron schedule |
| `--interval` | `6h` | How often to run (e.g., `6h`, `12h`) |

---

## 3. Step 0: Auto-Setup and Notes Resolution

**This step is MANDATORY. Run it BEFORE doing anything else.** The skill must always know where notes live before any exploration, reading, or writing happens. Every conversation that activates this skill starts here.

### 0.1 Bootstrap Scripts

Ensure the Python environment is ready:

```bash
cd ~/.claude/skills/codebase-notes/scripts && test -d .venv || uv sync
```

If `.venv` doesn't exist, `uv sync` will create it and install all dependencies (PyYAML, Pillow). This only needs to happen once, but always check.

### 0.2 Resolve Notes Path

Run the `repo-id` command to determine where notes are stored for this repo:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

This prints the repo ID (e.g., `anthropics--claude-code`). Notes for this repo live at:

```
~/.claude/repo_notes/<repo_id>/notes/
```

For example: `~/.claude/repo_notes/anthropics--claude-code/notes/`

The repo ID is derived from the git remote URL. All clones of the same repo share the same notes directory. If no git remote exists, a hash-based local ID is used.

**Store this path mentally — every subsequent operation reads from and writes to this location.**

### 0.3 Check for Existing Notes

After resolving the notes path, check if notes already exist:

**If the notes directory has content (contains .md files):** Run the staleness checker to see what's fresh and what needs updating:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale
```

This outputs a report showing FRESH, STALE, or NO_TRACKING for each note. Present the results to the user along with the Knowledge Map from `00-overview.md`. Ask what they want to do: explore more, update stale notes, add detail, etc.

**If the notes directory is empty or doesn't exist:** Run scaffold to create the initial structure:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts scaffold
```

This creates the notes directory with a skeleton `00-overview.md` and a `RULES.md` copied from the skill's template. Then proceed to Phase 1.

### 0.4 Check for v1 Notes

If no centralized notes exist, check whether this repo has v1 notes (stored inside the repo itself at paths like `docs/notes`, `notes`, or `docs/knowledge`). Look for a `00-overview.md` file in those locations.

**If v1 notes are found**, offer to migrate them:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts migrate --from docs/notes
```

The migration copies all `.md`, `.excalidraw`, and `.png` files to the centralized location, preserving directory structure. It reports any broken links that pointed outside the notes directory. The original files are NOT deleted — the user can remove them manually.

After migration, re-run Step 0.3 to load the migrated notes.

---

## 4. Context Priming Protocol

Whenever you need to understand part of the codebase — whether for exploration, answering questions, debugging, or feature work — follow this order:

### 4.1 Read Notes First (cheap, pre-digested context)

After resolving the notes path in Step 0, read notes in this order:

1. Read `00-overview.md` in the notes directory to understand the full system map
2. Read the relevant topic's `index.md` to understand the subsystem
3. Read the specific note for the area you need

Notes contain architecture, data flow, schemas, config, key files, and diagrams. This is 10-100x cheaper than re-exploring source code and gives you the "why" that code alone can't.

### 4.2 Fall Back to Code Exploration (when notes are insufficient)

If notes don't cover what you need — a specific function signature, a recently added feature, an edge case — then explore the code. Use the Key Files tables in notes as starting points rather than grepping blindly.

### 4.3 Update Notes with What You Learned (pay it forward)

After learning something new from code exploration, update the relevant note:

- **Minor addition**: Edit the existing note to add the new information
- **New sub-topic**: Create a child note if the topic warrants its own page
- **Correction**: Fix any stale information in existing notes
- **New topic**: Create a new topic folder if the area isn't covered at all

This keeps notes as a living cache of codebase understanding. Every agent session that explores code should leave the notes better than it found them.

### When to Use This Protocol

- **Starting a new conversation**: Run Step 0, then read `00-overview.md`
- **Before exploring code**: Check if notes already cover it
- **After any code exploration**: Update notes with new findings
- **When answering questions about the codebase**: Cite notes, not just code
- **When debugging**: Read the relevant system's note first to understand architecture
- **Working on a feature or bug**: Read notes on the relevant area for context, then update notes if you learned something new

---

## 5. Phase 1: Initialize

When starting fresh (no notes exist after Step 0), create the foundation.

### 5.1 Explore the Repository

Before writing anything, understand the repo:

- Read README.md, CLAUDE.md, any onboarding docs
- Check `ls` at root for top-level structure
- Identify languages (pyproject.toml, Cargo.toml, go.mod, package.json)
- Identify build tools (justfile, Makefile, mise.toml, docker-compose)
- Identify the major systems/packages

### 5.2 Write the Overview

The overview (`00-overview.md`) in the notes directory must contain:

1. **Navigation bar** at top linking to all topic folders created so far
2. **"What is this?"** — one paragraph describing the repo
3. **Architecture section** — Excalidraw diagram + text description of how major systems connect. The text description is mandatory even if the diagram renders perfectly — it serves as fallback and adds detail the diagram can't.
4. **Languages and Build Tools** — what's used and how
5. **Top-Level Packages** — table of directories, what they do, primary language
6. **Knowledge Map** — table of all topics with exploration status and links

Update the skeleton `00-overview.md` that `scaffold` created with this content.

### 5.3 Present Topics

After writing the overview, present the Knowledge Map to the user as numbered options. Let them choose what to explore. This is the interactive loop.

**Topic numbers in the Knowledge Map (1, 2, 3...) don't need to match folder numbers (01-, 02-, 03-).** Folders are numbered in the order they're created. The Knowledge Map orders topics by logical grouping.

---

## 6. Phase 2: Explore (The Core Loop)

The user picks a topic, you explore it, write notes, and present new options.

### 6.1 Dispatch Explore Agent

For each topic, dispatch a sub-agent with a detailed prompt. The quality of notes depends heavily on the explore prompt being specific. Use this template:

```
Very thoroughly explore <path>. I need a deep understanding of:

1. **What is it?** Read any README, pyproject.toml, and top-level files.
2. **Architecture**: Main modules/packages, how it's structured.
3. **Core logic**: Key classes, functions, data structures. What does each do?
4. **Data flow**: How does data enter, transform, and exit?
5. **Integration points**: How does it connect to other parts of the monorepo?
6. **Configuration**: Env vars, config files, defaults.
7. **API surface**: Endpoints, gRPC services, MCP tools, CLI commands.
8. **Schemas**: Database models, protobuf definitions, Pydantic models.
9. **Testing**: How is it tested? Key fixtures?
10. **Deployment**: How is it deployed?

Read ALL key source files. Give me specifics — function signatures, class names,
config fields, actual processing logic — not just labels.
```

Use `subagent_type: "Explore"` for the Agent tool.

### 6.2 Write Notes from Results

Follow the note structure (see Section 10). Key rules:

- Lead with "What is it?" paragraph
- Prefer tables for structured data
- Include a Key Files table at the bottom
- Create Excalidraw diagram(s) — see Section 11
- Add text description for every diagram
- Set `git_tracked_paths` in frontmatter to the source paths explored, with the current commit hash

### 6.3 Update Parents

After writing a note:

- Add link in parent `index.md` sub-topics list
- Update sibling Prev/Next navigation links
- Update `00-overview.md` Knowledge Map and navigation bar

Or run the nav script to rebuild all links automatically:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav
```

### 6.4 Present Options

Always present navigation options after writing notes:

```
Where to next?
- Dive into sub-topic X, Y, or Z
- Go back to overview
- Explore a different top-level topic (1-N)
- Go deeper on [specific thing mentioned in the notes]
```

The user's choices determine what gets explored. Never explore everything unprompted.

### 6.5 Parallel Exploration

When the user asks to explore multiple topics at once, dispatch multiple Explore agents simultaneously. Write notes as results arrive — don't wait for all to complete.

After parallel exploration completes, run the nav script to fix all navigation links at once:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav
```

---

## 7. Phase 3: Update and Maintain

### 7.1 Staleness Detection

Run the staleness checker to identify notes that need updating:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale
```

The checker parses `git_tracked_paths` frontmatter from each note, runs `git diff` against the tracked commit hash, and reports:

- **FRESH** — no files changed since the note was written
- **STALE** — files changed in the tracked paths since the note's commit
- **NO_TRACKING** — note has no `git_tracked_paths` frontmatter

Results are cached for 10 minutes. Use `--no-cache` to force a fresh check.

Focus on: new files/modules, changed APIs, renamed functions, new integrations.

### 7.2 Update In-Place

When updating stale notes:

- Prefer updating existing notes over creating new ones
- Read the current note to understand what it covers
- Check the changed files to understand what's different
- Update note content to reflect the current state of the code
- Update the `git_tracked_paths` commit hashes in frontmatter
- Update `last_updated` date in frontmatter
- Update diagrams if architecture changed
- Update Knowledge Map status in `00-overview.md`

### 7.3 Add Detail

When the user asks to go deeper:

- Read the existing note to understand current coverage
- Explore code for the specific area they want
- Either expand the existing note or create a child note in a subfolder
- Always update parent links and git tracking frontmatter
- Run `nav` to rebuild navigation links if you created new files

---

## 8. Commit History

Generate notes that track what has changed in the codebase over time, grouped by author and path.

### Generate Commit Notes

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts commits --author "Jane Doe" --since 4w
```

This runs `git log`, groups commits by author and path prefix, and writes markdown files to:

```
~/.claude/repo_notes/<repo_id>/notes/commits/<author-slug>/<path-slug>.md
```

Each file contains a YAML frontmatter header, a summary placeholder (for Claude to fill), and a table of commits with date, message, and hash.

### Summarize Commit Notes

After generating commit notes, read the markdown file and write a narrative summary in the `## Summary` section. Focus on themes, patterns, and the story of what changed — not just listing commits.

### When to Use

- User asks "What has changed recently?"
- User wants to understand a teammate's recent work
- Onboarding to a codebase and want to see recent activity
- Before updating stale notes, to understand what changed and why

### Path Filtering

Narrow to a specific area of the codebase:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts commits --author "Jane Doe" --since 2w --path src/api
```

---

## 9. Cron Auto-Updates

Automatically keep notes fresh by scheduling periodic staleness checks and Claude-powered updates.

### Install

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts cron --install --interval 6h
```

On macOS, this installs a launchd plist at `~/Library/LaunchAgents/com.codebase-notes.auto-update.plist`. On Linux, it adds a crontab entry. The default interval is every 6 hours.

### What It Does

When triggered, the auto-update process:

1. Acquires a PID-based lock file to prevent concurrent runs
2. Scans all repos in `~/.claude/repo_notes/` for stale notes
3. Selects the top 5 most-stale repos (by number of changed files)
4. For each, spawns a non-interactive `claude -p` session with the update prompt
5. Each session has a 10-minute timeout
6. Logs all activity to `~/.claude/repo_notes/cron.log`
7. Releases the lock

### Uninstall

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts cron --uninstall
```

### Monitoring

Check the cron log:

```bash
cat ~/.claude/repo_notes/cron.log
```

Run a manual update to test:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts auto-update --all-repos
```

Or for a single repo:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts auto-update
```

---

## 10. Note Structure

### Directory Layout

Notes are stored at `~/.claude/repo_notes/<repo_id>/notes/`:

```
notes/
├── 00-overview.md
├── RULES.md
├── 01-topic-name/
│   ├── index.md
│   ├── 01-subtopic.md
│   ├── 01-subtopic.excalidraw
│   ├── 01-subtopic.png
│   ├── 02-subtopic.md
│   └── 03-deep-topic/
│       ├── index.md
│       ├── 01-detail.md
│       └── ...
├── 02-topic-name/
│   └── ...
└── commits/
    └── author-slug/
        └── path-slug.md
```

**Naming:** Folders `NN-topic-name/`, files `NN-subtopic.md`. Each folder has `index.md`. Diagrams sit alongside notes with matching names. Multiple diagrams per note use suffixes: `01-thing-architecture.excalidraw`, `01-thing-dataflow.excalidraw`.

### Note Template

Every note follows this structure:

```markdown
---
git_tracked_paths:
  - path: relative/path/to/source/directory/
    commit: abc1234
last_updated: YYYY-MM-DD
---
# Title

> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)

## What is it?

One paragraph summary.

## Architecture / Overview

![Description](./note-name.png)

Text description of what the diagram shows — how components connect, data flow,
key relationships. This must stand alone without the image.

## [Main sections — tables, schemas, config, API surfaces]

## Key Files

| File | Purpose |
|------|---------|
| `path/to/file.py` | What it does |
```

### Frontmatter

The `git_tracked_paths` frontmatter links the note to the source code directories it documents. Multiple paths can be tracked per note. The `commit` is the short hash from `git log -1 --format=%h -- <path>` at the time the note was written or last updated.

### Navigation Bar

Every note starts with a navigation line after the frontmatter and title:

```markdown
> **Navigation:** Up: [Parent](../index.md) | Prev: [Sibling](./01-prev.md) | Next: [Sibling](./03-next.md)
```

Index files additionally have a Sub-topics line:

```markdown
> **Sub-topics:** [Child A](./01-child-a.md) | [Child B](./02-child-b.md)
```

All links are **relative paths**.

### Content Rules

- **Tables over prose** for structured data (config, endpoints, schemas)
- **Code snippets** only for schemas, key data structures, non-obvious patterns
- **No filler** — no "In this section we will..."
- **No ASCII art** for diagrams — always Excalidraw. ASCII is only acceptable for directory tree listings.
- **Text fallback** for every diagram — written description below that stands alone
- **Cross-referencing** — when a concept spans multiple code areas, define it once in the note matching the code location, cross-reference from others with relative links
- **Mirror codebase structure** — note hierarchy should reflect the source code organization

---

## 11. Diagrams

Every note needs at least one Excalidraw diagram. Notes covering multiple concepts should have multiple.

### Creating Diagrams

1. Create `.excalidraw` JSON section-by-section (not all at once — large diagrams hit token limits)
2. Save the JSON file alongside the note with a matching name (e.g., `01-subtopic.excalidraw`)
3. Render all diagrams:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render
```

4. View the PNG with the Read tool to verify it looks correct
5. Fix issues and re-render until clean
6. Embed in the note with `![description](./filename.png)`

**The renderer outputs `filename.png` (NOT `filename.excalidraw.png`). Always reference `.png` only.**

The render command finds all `.excalidraw` files in the notes directory, skips any that already have an up-to-date `.png`, and renders the rest using a built-in Pillow-based renderer.

### Diagram Types

| Note Type | Diagram Style |
|-----------|--------------|
| Overview/Index | Hub-and-spoke or layered architecture |
| Service/Component | Data flow (request lifecycle, event pipeline) |
| Workflow/Process | State machine or timeline |
| Config/Reference | Hierarchy tree or ecosystem map |

### Style Rules

- `roughness: 0`, `fontFamily: 3`, `opacity: 100`
- Descriptive string IDs (`"backend_rect"`, `"arrow_to_mongo"`)
- Shapes need `boundElements` referencing text; text needs `containerId`
- Arrows need `startBinding`/`endBinding` with `{elementId, focus: 0, gap: 2}`
- Use semantic colors: blue for services, green for data stores, orange for external, purple for async
- Background: white (`#ffffff`)
- Stroke: `#1e1e1e` for borders, colored for arrows between systems

### Image Path Conflicts

Some markdown viewers (like md-serve with Next.js routing) can't serve images whose filename matches a page route. If a root-level image doesn't render, rename it (e.g., `00-overview.png` to `00-overview-architecture.png`).

---

## 12. Parallelization Patterns

### Multiple Topics

When the user asks to explore several topics at once:

```
Launch N Explore agents simultaneously (one per topic)
Write notes as results arrive — don't wait for all to complete
Run nav script after all agents finish to rebuild all links
```

### Batch Diagrams

When creating diagrams across multiple notes:

```
Launch N sub-agents (one per note group) to create .excalidraw JSON
After all complete, render everything in one pass:
```

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render
```

Sub-agents creating diagrams may lack bash permissions — always render centrally after they complete.

### Diving into All Sub-Topics

When the user says "explore everything under topic X":

```
Read the topic's index.md to identify sub-topics
Launch N Explore agents (one per sub-topic)
Write sub-topic notes as results arrive
Update parent index.md with links
Run nav script to fix all navigation
```

---

## 13. Knowledge Map

The Knowledge Map is a table in `00-overview.md` that tracks all topics and their exploration status.

### Format

```markdown
## Knowledge Map

| # | Topic | Status | Notes |
|---|-------|--------|-------|
| 1 | Authentication — login, OAuth, sessions | FRESH | [01-auth/](./01-auth/index.md) |
| 2 | API Layer — REST endpoints, middleware | STALE (5 files) | [02-api/](./02-api/index.md) |
| 3 | Database — models, migrations, queries | — | _not yet explored_ |
| 4 | Background Jobs — workers, queues | FRESH | [04-jobs/](./04-jobs/index.md) |
```

### Update Rules

- **New exploration**: Change `_not yet explored_` to a folder link with FRESH status
- **Staleness check**: Update status column with FRESH, STALE (N files), or NO_TRACKING
- **Sub-topics explored**: Optionally add indented rows with `  ↳ sub-topic`
- **New topics discovered**: Add new rows to the table
- **New topic folders**: Add link to Navigation bar at top of overview

### Generating the Map

After running the staleness checker, update the Knowledge Map to reflect current status. The staleness output gives you FRESH/STALE/NO_TRACKING for each note — map those to the Status column.

---

## 14. v1 to v2 Migration

### What Changed

| Aspect | v1 | v2 |
|--------|----|----|
| Storage location | Inside repo (e.g., `docs/notes`) | Centralized (`~/.claude/repo_notes/<repo_id>/notes/`) |
| Shared across clones | No | Yes — same repo ID, same notes |
| Staleness detection | Manual bash loops | Python script with caching |
| Navigation links | Manual management | Automated via `nav` script |
| Diagram rendering | External skill dependency | Built-in Pillow renderer |
| Commit history | Not supported | `commits` script with author/path grouping |
| Auto-updates | Not supported | Cron-based with Claude |
| Gitignore needed | Yes | No — notes are outside the repo |

### Migration Command

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts migrate --from docs/notes
```

This will:
1. Resolve the repo ID for the current directory
2. Copy all `.md`, `.excalidraw`, and `.png` files preserving directory structure
3. Report any links that point outside the notes directory (need manual fixing)
4. Leave the original directory untouched

### Manual Migration

If the automated migration doesn't handle your case:

1. Run `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id` to get the repo ID
2. Run `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts scaffold` to create the target structure
3. Manually copy your notes to `~/.claude/repo_notes/<repo_id>/notes/`
4. Fix any relative links that now point to the wrong location
5. Run `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav` to rebuild navigation
6. Run `cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts render` to re-render diagrams

---

## 15. Quick Reference

| User Says | Action |
|-----------|--------|
| "Help me understand this repo" | Step 0 (resolve notes path) -> check for existing notes -> Phase 1 or resume |
| "Create notes for this codebase" | Step 0 -> scaffold -> Phase 1 |
| "Explore topic X" | Step 0 -> read existing notes on X -> dispatch Explore agent for gaps -> write/update notes |
| "Dive into X, Y, Z in parallel" | Step 0 -> dispatch multiple Explore agents simultaneously -> write notes as results arrive |
| "Go back to overview" | Present Knowledge Map with current staleness status |
| "Update the notes" | Step 0 -> run `stale` -> Phase 3: update stale notes in-place |
| "Add diagrams" | Create Excalidraw JSON -> run `render` -> embed PNGs in notes |
| "Go deeper on X" | Read existing note -> explore code for gaps -> create child note or expand |
| "Add more detail" | Re-explore with deeper focus, expand note or create sub-notes |
| "What changed recently?" | Run `commits --author "Name" --since 4w` -> summarize results |
| "Keep notes up to date automatically" | Run `cron --install` -> explain what it does |
| "Migrate my old notes" | Run `migrate --from <path>` -> verify results -> clean up broken links |
| "Research topic X" / "Find papers on Y" | Step 0 -> check research/ dir -> web search/fetch -> create research notes grouped by topic |
| "Summarize this paper/URL" | Step 0 -> fetch content -> create research note with project context mapping |
| _(any task needing codebase context)_ | Step 0 -> read `00-overview.md` + relevant topic notes -> then code |
| "Fix bug in X" / "Add feature to Y" | Step 0 -> read notes on X/Y for context -> work on code -> update notes with new findings |
| "How does X work?" | Step 0 -> read notes on X -> answer from notes -> if insufficient, explore code and update notes |

## 16. Research Notes

Research notes capture knowledge from **external resources** — papers, articles, blog posts, competitive analysis, tutorials — organized by topic. They live in `~/.claude/repo_notes/<repo_id>/notes/research/`.

### Structure

```
research/
├── index.md                        # Research overview — all topics with paper counts
├── 01-{broad-topic}/
│   ├── index.md                    # Topic overview + paper/article index table
│   ├── 01-{paper-or-article}.md    # Individual resource note
│   └── 01-{sub-group}/            # Sub-grouping for large topics (>5 papers)
│       ├── index.md
│       └── 01-{paper}.md
```

### When to Create Research Notes

- User asks to research a topic or technology
- User provides URLs to papers/articles to summarize
- Competitive analysis is needed
- Understanding foundational techniques that inform the codebase

### Paper/Article Note Format

Each research note uses frontmatter:

```yaml
---
type: research-paper
source_url: https://...
relevance: foundational|competitive|adjacent|overview
date_added: YYYY-MM-DD
---
```

Required sections: Core Contribution, Technical Approach, Key Results, **Project Context** (how it maps to our codebase).

### Topic Grouping

Group by broad domain first, sub-group by theme when topics grow large. The topic `index.md` contains a paper index table and cross-cutting insights. See RULES.md "Research Notes" section for full template.

### Invoking Research

```bash
# Use the research subcommand
/codebase-notes:research "autonomous labs" --source https://example.com/paper
```
