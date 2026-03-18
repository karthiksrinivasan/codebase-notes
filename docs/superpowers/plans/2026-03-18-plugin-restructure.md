# Codebase Notes Plugin Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure codebase-notes from a single skill with command files into a Claude Code plugin with individual skills per command, enabling colon-separated invocation (`/codebase-notes:update`) and smaller context per invocation.

**Architecture:** Move from `SKILL.md` + `commands/*.md` to `skills/*/SKILL.md`. Extract shared context (script invocation, Step 0, note structure, diagram rules) into `references/shared-context.md`. Each skill's SKILL.md includes only its focused instructions plus a reference to shared context. Add `package.json` for plugin registration.

**Tech Stack:** Claude Code plugin system, markdown skill files, Python scripts (unchanged)

---

### Task 1: Create package.json

**Files:**
- Create: `package.json`

- [ ] **Step 1: Create the plugin manifest**

```json
{
  "name": "codebase-notes",
  "version": "2.0.0",
  "type": "module"
}
```

- [ ] **Step 2: Commit**

```bash
git add package.json
git commit -m "feat: add package.json for plugin registration"
```

---

### Task 2: Create shared-context.md

Extract shared sections from SKILL.md into a reference file that each skill can point to.

**Files:**
- Create: `references/shared-context.md`

- [ ] **Step 1: Create `references/shared-context.md`**

Extract these sections from the current SKILL.md into the shared context file:
- Script invocation pattern (Section 2 — the `REPO_CWD=$(pwd) && cd ...` pattern and command reference table)
- Step 0: Auto-Setup and Notes Resolution (Section 3 — bootstrap, resolve, check existing, check v1)
- Context Priming Protocol (Section 4 — read notes first, fall back to code, update notes)
- Note Structure (Section 10 — directory layout, template, frontmatter, navigation, content rules)
- Diagrams (Section 11 — creating, types, style rules)
- Parallelization Patterns (Section 12)
- Knowledge Map (Section 13)

The file should be self-contained reference material. Each skill will instruct Claude to read this file at the start.

**Path resolution:** Script paths must be dynamic based on where the plugin is installed. Use the skill's own SKILL.md location to derive the plugin root. Each skill should include a preamble like:

```
## Plugin Root Resolution
This skill's SKILL.md location tells you the plugin root. From `skills/<name>/SKILL.md`, the plugin root is `../../`. All script invocations and reference file reads use this resolved root.
```

In `shared-context.md`, use `<plugin_root>` as a placeholder in all paths (e.g., `<plugin_root>/scripts`, `<plugin_root>/references/`). Each skill resolves `<plugin_root>` from its own location.

- [ ] **Step 2: Commit**

```bash
git add references/shared-context.md
git commit -m "feat: extract shared context from SKILL.md into references/"
```

---

### Task 3: Create the `skills/` directory with all 10 skill SKILL.md files

Each command becomes its own skill. The old `commands/*.md` content becomes `skills/*/SKILL.md` with proper frontmatter (`name`, `description`). Each skill:
1. Has focused `name` and `description` fields in frontmatter
2. Contains its own instructions (from the corresponding command file)
3. References shared-context.md for common patterns
4. Lists its own `allowed-tools`

**Files:**
- Create: `skills/init/SKILL.md`
- Create: `skills/explore/SKILL.md`
- Create: `skills/update/SKILL.md`
- Create: `skills/check/SKILL.md` (merge of old check + status)
- Create: `skills/answer/SKILL.md`
- Create: `skills/diagram/SKILL.md`
- Create: `skills/research/SKILL.md`
- Create: `skills/commits/SKILL.md` (was commit-explore)
- Create: `skills/migrate/SKILL.md`
- Create: `skills/cron/SKILL.md`

- [ ] **Step 1: Create `skills/init/SKILL.md`**

Frontmatter:
```yaml
---
name: init
description: Initialize codebase notes for the current repository. Bootstraps scripts, resolves repo identity, scaffolds the notes directory, and writes the initial overview with architecture diagrams.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"]
---
```

Body: content from `commands/init.md` (without the old frontmatter), plus a line at the top saying:
```
**Shared context:** Read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines.
```

Also inline the core philosophy from Section 1 of SKILL.md as a brief section, since `init` is the entry point where users first encounter the skill.

- [ ] **Step 2: Create `skills/explore/SKILL.md`**

Frontmatter:
```yaml
---
name: explore
description: Explore a codebase topic in depth and write structured notes with architecture diagrams. Dispatches Explore agents, writes notes following the capture matrix, and presents options for deeper exploration.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"]
---
```

Body: content from `commands/explore.md`.

- [ ] **Step 3: Create `skills/update/SKILL.md`**

Frontmatter:
```yaml
---
name: update
description: Update stale codebase notes by detecting code changes since last update, re-exploring affected areas, and refreshing note content in-place.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"]
---
```

Body: content from `commands/update.md`.

- [ ] **Step 4: Create `skills/check/SKILL.md`**

Merge `commands/check.md` and `commands/status.md` into one skill. The `check` command shows the Knowledge Map with staleness status and suggests actions.

Frontmatter:
```yaml
---
name: check
description: Show the knowledge map with staleness status for all codebase notes. Reports which notes are fresh, stale, or untracked, with actionable suggestions.
allowed-tools: ["Read", "Bash", "Glob"]
---
```

Body: merged content from check.md and status.md. Include `--all-repos`, `--no-cache`, `--json`, `--verbose` flags.

- [ ] **Step 5: Create `skills/answer/SKILL.md`**

Frontmatter:
```yaml
---
name: answer
description: Answer questions about the codebase using pre-built notes as primary context. Reads relevant notes first, falls back to code exploration only when needed, and updates notes with new findings.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"]
---
```

Body: content from `commands/answer.md`.

- [ ] **Step 6: Create `skills/diagram/SKILL.md`**

Frontmatter:
```yaml
---
name: diagram
description: Add or update Excalidraw architecture diagrams for codebase notes. Creates and renders diagrams to PNG with proper styling and text descriptions.
allowed-tools: ["Read", "Write", "Bash", "Glob", "Agent"]
---
```

Body: content from `commands/diagram.md`.

- [ ] **Step 7: Create `skills/research/SKILL.md`**

Frontmatter:
```yaml
---
name: research
description: Research external topics and create structured notes from papers, articles, blog posts, and web resources. Organized by topic in a dedicated research/ directory with relevance tagging.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch", "WebSearch"]
---
```

Body: content from `commands/research.md`.

- [ ] **Step 8: Create `skills/commits/SKILL.md`**

Frontmatter:
```yaml
---
name: commits
description: Explore recent git commit history and generate structured notes grouped by author and code area. Useful for understanding what changed recently, onboarding, or release notes.
allowed-tools: ["Read", "Write", "Bash", "Glob"]
---
```

Body: content from `commands/commit-explore.md`.

- [ ] **Step 9: Create `skills/migrate/SKILL.md`**

Frontmatter:
```yaml
---
name: migrate
description: Migrate v1 codebase notes (stored in-repo at docs/notes/) to the v2 centralized location at ~/.claude/repo_notes/. Copies files, preserves structure, and reports broken links.
allowed-tools: ["Read", "Bash", "Glob"]
---
```

Body: content from `commands/migrate.md`.

- [ ] **Step 10: Create `skills/cron/SKILL.md`**

This skill doesn't have a dedicated command file currently — the cron instructions are in SKILL.md Section 9. Extract into its own skill.

Frontmatter:
```yaml
---
name: cron
description: Set up automatic cron-based updates for codebase notes. Installs a launchd plist (macOS) or crontab entry (Linux) to periodically check and refresh stale notes.
allowed-tools: ["Read", "Bash"]
---
```

Body: extract from SKILL.md Section 9 (Cron Auto-Updates).

- [ ] **Step 11: Commit all skills**

```bash
git add skills/
git commit -m "feat: create individual skills for plugin structure"
```

---

### Task 4: Remove old SKILL.md and commands/

**Files:**
- Delete: `SKILL.md`
- Delete: `commands/answer.md`
- Delete: `commands/check.md`
- Delete: `commands/commit-explore.md`
- Delete: `commands/diagram.md`
- Delete: `commands/explore.md`
- Delete: `commands/init.md`
- Delete: `commands/migrate.md`
- Delete: `commands/research.md`
- Delete: `commands/status.md`
- Delete: `commands/update.md`

- [ ] **Step 1: Remove old files**

```bash
rm SKILL.md
rm -r commands/
```

- [ ] **Step 2: Commit**

```bash
git add -u
git commit -m "refactor: remove old SKILL.md and commands/ directory"
```

---

### Task 5: Migrate from skill to plugin registration

The current symlink at `~/.claude/skills/codebase-notes` registers this as a standalone skill. Since this is now a plugin, remove the old symlink and register as a plugin.

- [ ] **Step 1: Remove the old skill symlink**

```bash
rm ~/.claude/skills/codebase-notes
```

- [ ] **Step 2: Register as a plugin in settings.json**

Add the plugin to `~/.claude/settings.json` under `enabledPlugins`. The exact key format depends on how local plugins are registered — check how other local plugins appear in the settings, or add as a local plugin path.

- [ ] **Step 3: Verify plugin is discoverable**

Start a new Claude session and run `/help` to confirm all 10 `codebase-notes:*` skills appear.

- [ ] **Step 4: Commit any settings changes if needed**

---

### Task 6: Update internal references

**Files:**
- Modify: `references/shared-context.md` — ensure all `/codebase-notes:` references use colon syntax
- Modify: `skills/check/SKILL.md` — update cross-references to use `/codebase-notes:update`, `/codebase-notes:explore`

- [ ] **Step 1: Search for old command syntax references**

Find all occurrences of `/codebase-notes ` (space-separated) in all files and update to colon syntax: `/codebase-notes:update`, `/codebase-notes:explore`, etc.

Also update the renamed command: `commit-explore` → `commits`. Any references to `/codebase-notes:commit-explore` become `/codebase-notes:commits`.

- [ ] **Step 2: Commit**

```bash
git add -u
git commit -m "fix: update all command references to colon syntax"
```

---

### Task 7: Verify and test

- [ ] **Step 1: Run tests to ensure scripts still work**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 171 tests pass (scripts are unchanged).

- [ ] **Step 2: Verify plugin structure**

```bash
ls skills/*/SKILL.md
```

Expected: 10 SKILL.md files.

- [ ] **Step 3: Verify shared-context.md exists and is complete**

```bash
wc -l references/shared-context.md
```

Expected: comprehensive reference file covering all shared patterns.

- [ ] **Step 4: Verify no orphaned files**

```bash
test ! -f SKILL.md && echo "Old SKILL.md removed"
test ! -d commands && echo "Old commands/ removed"
```

- [ ] **Step 5: Start a new Claude session and test `/codebase-notes:check`**

Manual verification that the plugin is discoverable and skills work.
