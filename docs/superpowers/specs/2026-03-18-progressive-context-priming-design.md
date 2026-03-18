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
| Index refresh | PostToolUse hook on Write and Edit, filtered to repo_notes paths | Keeps index fresh when notes are created/updated during session |
| Staleness in index | Yes, from cached staleness data | Enables proactive "notes are stale" surfacing at near-zero cost |

## Components

### 1. Compact Index Generator (`scripts context-index`)

New Python script added to the CLI. Produces a token-efficient index of all notes across all four content directories.

**Command:**
```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts context-index
```

**Flags:**
- `--repo-id REPO_ID` — explicit repo ID override (consistent with other CLI commands).
- `--filter-stdin` — reads PostToolUse JSON from stdin, extracts the written file path, and exits silently (no output) if the path is not inside `~/.claude/repo_notes/`. Used by the PostToolUse hook to avoid noisy re-injection on unrelated writes.
- `--json-envelope` — wraps the output in the Claude Code hook JSON format (`hookSpecificOutput.additionalContext`). Used by both hooks.

**Output format (the content inside `additionalContext`):**
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

- Reads frontmatter from each `.md` file to extract `git_tracked_paths` for the tracked paths column. Extracts title from the first `# heading` line.
- Staleness: loads the staleness cache file (`~/.claude/repo_notes/<repo_id>/.staleness_cache`) directly — does NOT run fresh git checks. If cache is missing or expired, shows `—` instead of FRESH/STALE.
- One-line description: reads `00-overview.md`, extracts the first paragraph after the "What is this?" heading (or first paragraph after frontmatter if no such heading).
- Directories that don't exist or are empty are omitted from output.
- Script exits with code 0 and empty output if: no git repo detected, no repo_notes directory exists, or `--filter-stdin` is set and the file path is not in repo_notes.
- When `--json-envelope` is set, wraps the markdown output in the Claude Code JSON format: `{"hookSpecificOutput": {"hookEventName": "<event>", "additionalContext": "<escaped content>"}}`. When not set, outputs raw markdown (useful for CLI debugging).

### 2. Hook Output Format

Claude Code hooks must output JSON to inject context. Raw stdout text is silently ignored. The required format for context injection is:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "...escaped markdown content..."
  }
}
```

The `context-index` script handles this internally via the `--json-envelope` flag. The hook shell commands use a thin wrapper script (`hooks/context-prime`) that:
1. Resolves `REPO_ROOT` from git
2. Calls the Python script with appropriate flags
3. Exits silently on any failure

### 3. Hook Configuration

**`hooks/hooks.json`:**
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/context-prime\" session-start",
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/context-prime\" post-tool-use",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**`hooks/context-prime` (bash script):**
```bash
#!/usr/bin/env bash
set -euo pipefail

EVENT="$1"

# Resolve repo root — hooks may run from any cwd
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
export REPO_ROOT

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${PLUGIN_ROOT}/scripts"

if [ "$EVENT" = "session-start" ]; then
  uv run python -m scripts context-index --json-envelope 2>/dev/null || true
elif [ "$EVENT" = "post-tool-use" ]; then
  uv run python -m scripts context-index --filter-stdin --json-envelope 2>/dev/null || true
fi
```

**Behavior:**

- **SessionStart** with `startup` matcher: fires only on fresh session start, not on `clear` or `compact`. If `startup` is not a valid standalone matcher value, the script should check the event type from stdin and exit early for non-startup events.
- **PostToolUse** with `Write|Edit` matcher: fires after both Write and Edit tool calls. The `--filter-stdin` flag reads the tool input JSON from stdin to check whether the file path is inside `~/.claude/repo_notes/`. If not, exits silently with no output.
- **Timeout**: 15s for SessionStart (cold venv start), 10s for PostToolUse (venv should be warm). Prevents slow hooks from blocking conversation.
- **Failure handling**: all paths exit 0 on failure — hooks must never break the session.

### 4. PostToolUse Filtering

The PostToolUse hook receives JSON on stdin with tool input details. For Write/Edit, this includes:

```json
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/Users/karthik/.claude/repo_notes/org--repo/notes/01-auth/02-new-topic.md",
    "content": "..."
  }
}
```

The `--filter-stdin` flag in context-index:
1. Reads JSON from stdin
2. Extracts `tool_input.file_path`
3. Checks if the path starts with `~/.claude/repo_notes/`
4. If yes: generates and outputs the full refreshed index
5. If no: exits with code 0 and no output (no context injected)

This ensures the hook fires quickly and silently for the vast majority of Write/Edit calls that are unrelated to notes.

### 5. Progressive Reading Protocol

The compact index gives Claude a map. Claude's natural conversation behavior handles the rest:

1. **Layer 1 — Compact index** (injected automatically): Claude sees all topics, paths, and staleness status.
2. **Layer 2 — Topic index.md** (read on demand): when a topic becomes relevant, Claude reads the topic's `index.md` to see subtopics and their descriptions.
3. **Layer 3 — Specific note** (read on demand): Claude reads the specific subtopic note relevant to the conversation.

No special instructions or protocol enforcement needed beyond the footer line in the index output. Claude already knows how to use the Read tool.

### 6. Staleness Surfacing

When Claude sees a STALE status in the index for a note relevant to the current conversation, it can proactively inform the user:

> "The auth notes are stale (3 files changed since last update) — want me to update them while we're here?"

This is a behavioral suggestion embedded in the index footer, not enforced by code. Claude decides when it's appropriate based on conversation context.

## What This Does NOT Do

- Does not read note content at session start — only the compact index
- Does not change how existing skills work — they still run their own Step 0
- Does not require new skills or slash commands
- Does not run fresh git staleness checks — uses cached data only
- Does not fire on `clear` or `compact` — only fresh `startup`
- Does not inject on every Write/Edit — only writes to repo_notes paths

## File Changes

| File | Change |
|------|--------|
| `scripts/context_index.py` | New — compact index generator with `--filter-stdin`, `--json-envelope`, `--repo-id` flags |
| `scripts/__main__.py` | Add `context-index` command registration |
| `hooks/hooks.json` | New — SessionStart and PostToolUse hook configuration |
| `hooks/context-prime` | New — bash wrapper script that dispatches to context-index |
| `references/shared-context.md` | Update Section 4: add note that auto-priming handles the initial overview load for repos with notes. Section 4.1 "Read Notes First" remains as the manual protocol for when auto-priming isn't available or when a skill needs deeper context. Add a new subsection 4.0 "Auto-Priming (hook-based)" explaining that the compact index is injected at session start and Claude should use it as a navigation aid. |
| `tests/test_context_index.py` | New — tests for index generation, stdin filtering, JSON envelope output |

## Edge Cases

- **No notes for this repo**: script outputs nothing, hook succeeds silently.
- **No git repo**: `git rev-parse` fails, wrapper script exits 0.
- **Staleness cache missing/expired**: status column shows `—` instead of FRESH/STALE.
- **Very large note collections**: index is one row per note file. At 100 notes (~150-200 lines with headers), still well within token budget. Each PostToolUse refresh re-injects the full index — for repos with many notes and frequent note writes, cumulative token cost could add up. Acceptable for v1; future optimization could emit a shorter "index updated, N notes" confirmation instead of the full table.
- **Multiple clones of same repo**: repo ID is the same, so notes and index are shared. The `REPO_ROOT` from each clone resolves to the same repo_notes directory.
- **PostToolUse with non-notes Write/Edit**: `--filter-stdin` flag filters these out silently.
- **Hook cwd not in a git repo**: `git rev-parse --show-toplevel` fails, wrapper exits 0. This handles cases where Claude Code runs hooks from its own working directory rather than the user's repo.
- **`startup` matcher validity**: if `startup` alone is not a valid matcher (only the combined `startup|clear|compact` works), the wrapper script can check the event type from stdin and exit early for non-startup events. Implementation should test this during development and adjust accordingly.
