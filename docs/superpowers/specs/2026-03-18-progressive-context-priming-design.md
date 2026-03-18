# Progressive Context Priming — Design Spec

## Problem

Every codebase-notes skill currently runs its own "Step 0" to resolve the notes path and read the overview. Outside of skill invocations, Claude has no awareness that notes exist for the current repo. Users must explicitly invoke a skill to benefit from pre-built notes context. This wastes the notes investment — Claude re-explores code that's already documented.

## Solution

A hook-based system that automatically injects a lightweight navigation index at session start, then keeps it fresh as notes change during the session. Claude lazily reads deeper note content as conversation demands, using a three-layer progressive narrowing strategy: compact index -> topic index.md -> specific subtopic note.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger mechanism | SessionStart + PostToolUse hooks | Automatic, no user action needed |
| Initial context | Compact generated index, not raw overview | Token-efficient, covers all 4 directories |
| Progressive loading | Two-step: index.md first, then subtopics | Minimizes token waste on irrelevant content |
| Index refresh | PostToolUse hook on Write, filtered to repo_notes paths | Keeps index fresh when notes are created/updated during session |
| Staleness in index | Yes, from cached staleness data | Enables proactive "notes are stale" surfacing at near-zero cost |

## Components

### 1. Compact Index Generator (`scripts context-index`)

New Python script added to the CLI. Produces a token-efficient index of all notes across all four content directories.

**Command:**
```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts context-index
```

**Flags:**
- `--if-notes-changed` — only output if the triggering file write was inside `~/.claude/repo_notes/`. Used by the PostToolUse hook to avoid noisy re-injection on unrelated writes. Checks the `CLAUDE_TOOL_INPUT` environment variable (set by Claude Code for PostToolUse hooks) for the written file path.

**Output format:**
```
# Codebase Notes: <repo_id>
<one-line repo description extracted from 00-overview.md "What is this?" section>

## notes/
| Path | Title | Status | Tracked Paths |
|------|-------|--------|---------------|
| notes/01-auth/index.md | Authentication | FRESH | src/auth/ |
| notes/01-auth/01-oauth.md | OAuth Flow | STALE (3) | src/auth/oauth/ |
| notes/02-api/index.md | API Layer | FRESH | src/api/ |

## research/
| Path | Title | Status |
|------|-------|--------|
| research/01-vectors/index.md | Vector Databases | FRESH |

## projects/
| Path | Title |
|------|-------|
| projects/auth-redesign/index.md | Auth Redesign |

## commits/
| Path | Author | Area |
|------|--------|------|
| commits/alice/backend.md | Alice | Backend |

---
Notes root: ~/.claude/repo_notes/<repo_id>/
To explore a topic: read its index.md first, then read specific subtopics as needed.
When a relevant note is STALE, mention it to the user and offer to update.
```

**Implementation details:**

- Reads frontmatter from each `.md` file: extracts title from first `# heading`, `git_tracked_paths` for tracked paths column, `last_updated` for potential use.
- Staleness: loads the staleness cache file (`~/.claude/repo_notes/<repo_id>/.staleness_cache`) directly — does NOT run fresh git checks. If cache is missing or expired, shows `—` instead of FRESH/STALE.
- One-line description: reads `00-overview.md`, extracts the first paragraph after the "What is this?" heading (or first paragraph after frontmatter if no such heading).
- Directories that don't exist or are empty are omitted from output.
- Script exits with code 0 and empty output if: no git repo detected, no repo_notes directory exists, or `--if-notes-changed` flag is set and the written path is not in repo_notes.

### 2. SessionStart Hook

Fires on fresh conversation startup. Runs context-index and injects the compact index as additional context.

**Hook configuration (`hooks/hooks.json`):**
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) && cd \"${CLAUDE_PLUGIN_ROOT}/scripts\" && uv run python -m scripts context-index 2>/dev/null || true"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) && cd \"${CLAUDE_PLUGIN_ROOT}/scripts\" && uv run python -m scripts context-index --if-notes-changed 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

**Behavior:**
- `startup` matcher: only fires on fresh session start, NOT on `clear` or `compact` events. This avoids re-injecting the full index when context is compacted (the index from startup is already in the conversation).
- `|| true`: ensures hook never causes a session start failure for repos without notes.
- Output from the script becomes additional context visible to Claude.

### 3. PostToolUse Hook on Write

Fires after every Write tool call. The context-index script with `--if-notes-changed` checks whether the written file is inside `~/.claude/repo_notes/` and only outputs the refreshed index if so.

**Filtering mechanism:**

Claude Code sets environment variables for PostToolUse hooks that describe the tool input. The script inspects the file path from `CLAUDE_TOOL_INPUT` (JSON containing `file_path`). If the path doesn't start with the repo_notes base directory, the script exits silently.

**Why Write only (not Edit):**
New notes are created with Write. Edits to existing notes don't change the index structure (title and path remain the same). If an edit changes a note's title, the index will be slightly stale until the next Write — acceptable trade-off for avoiding hook noise on every Edit.

### 4. Progressive Reading Protocol

The compact index gives Claude a map. Claude's natural conversation behavior handles the rest:

1. **Layer 1 — Compact index** (injected automatically): Claude sees all topics, paths, and staleness status.
2. **Layer 2 — Topic index.md** (read on demand): when a topic becomes relevant, Claude reads the topic's `index.md` to see subtopics and their descriptions.
3. **Layer 3 — Specific note** (read on demand): Claude reads the specific subtopic note relevant to the conversation.

No special instructions or protocol enforcement needed beyond the footer line in the index output. Claude already knows how to use the Read tool.

### 5. Staleness Surfacing

When Claude sees a STALE status in the index for a note relevant to the current conversation, it can proactively inform the user:

> "The auth notes are stale (3 files changed since last update) — want me to update them while we're here?"

This is a behavioral suggestion embedded in the index footer, not enforced by code. Claude decides when it's appropriate based on conversation context.

## What This Does NOT Do

- Does not read note content at session start — only the compact index
- Does not change how existing skills work — they still run their own Step 0
- Does not require new skills or slash commands
- Does not run fresh git staleness checks — uses cached data only
- Does not fire on `clear` or `compact` — only fresh `startup`
- Does not inject on every Write — only writes to repo_notes paths

## File Changes

| File | Change |
|------|--------|
| `scripts/context_index.py` | New — compact index generator |
| `scripts/__main__.py` | Add `context-index` command registration |
| `hooks/hooks.json` | New — SessionStart and PostToolUse hooks |
| `references/shared-context.md` | Update Section 4 to reference auto-priming |
| `tests/test_context_index.py` | New — tests for the index generator |

## Edge Cases

- **No notes for this repo**: script outputs nothing, hook succeeds silently.
- **No git repo**: `git rev-parse` fails, `|| true` prevents hook failure.
- **Staleness cache missing/expired**: status column shows `—` instead of FRESH/STALE.
- **Very large note collections**: index is one row per note file. Even 100 notes is ~100 lines — well within token budget.
- **Multiple clones of same repo**: repo ID is the same, so notes and index are shared. The `REPO_ROOT` from each clone resolves to the same repo_notes directory.
- **PostToolUse with non-notes Write**: `--if-notes-changed` flag filters these out silently.
