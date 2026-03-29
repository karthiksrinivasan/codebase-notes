---
name: cron
version: 2.23.0
description: Set up automatic cron-based updates for codebase notes. Installs a launchd plist (macOS) or crontab entry (Linux) to periodically check and refresh stale notes. Use when the user says "auto-update notes", "schedule note updates", "keep notes fresh automatically", "install cron for notes", or wants periodic automatic staleness checks.
allowed-tools: ["Read", "Bash"]
---

**Shared context:** Before starting, read `${CLAUDE_PLUGIN_ROOT}/references/shared-context.md` for script invocation patterns, note structure rules, and diagram guidelines.

# Cron Auto-Updates

Automatically keep notes fresh by scheduling periodic staleness checks and Claude-powered updates.

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--install` | No | Install the cron schedule (default action) |
| `--uninstall` | No | Remove the cron schedule |
| `--interval INTERVAL` | No | How often to run (default: `6h`). Examples: `6h`, `12h`, `24h` |

**Examples:**
- `/codebase-notes:cron --install` — Install auto-updates every 6 hours
- `/codebase-notes:cron --install --interval 12h` — Install with 12-hour interval
- `/codebase-notes:cron --uninstall` — Remove auto-updates

---

You are setting up or removing automatic cron-based updates for codebase notes.

## Install

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts cron --install --interval 6h
```

Adjust `--interval` based on user input (default: 6h).

On macOS, this installs a launchd plist at `~/Library/LaunchAgents/com.codebase-notes.auto-update.plist`. On Linux, it adds a crontab entry.

## What It Does

When triggered, the auto-update process:

1. Acquires a PID-based lock file to prevent concurrent runs
2. Scans all repos in `~/.claude/repo_notes/` for stale notes
3. Selects the top 5 most-stale repos (by number of changed files)
4. For each, spawns a non-interactive `claude -p` session with the update prompt
5. Each session has a 10-minute timeout
6. Logs all activity to `~/.claude/repo_notes/cron.log`
7. Releases the lock

## Uninstall

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts cron --uninstall
```

## Monitoring

Check the cron log:

```bash
cat ~/.claude/repo_notes/cron.log
```

Run a manual update to test:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts auto-update --all-repos
```

Or for a single repo:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd ${CLAUDE_PLUGIN_ROOT}/scripts && uv run python -m scripts auto-update
```
