---
name: cron
description: Set up automatic cron-based updates for codebase notes. Installs a launchd plist (macOS) or crontab entry (Linux) to periodically check and refresh stale notes.
allowed-tools: ["Read", "Bash"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/cron/SKILL.md` → plugin root is `../../`.

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
REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts cron --install --interval 6h
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
REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts cron --uninstall
```

## Monitoring

Check the cron log:

```bash
cat ~/.claude/repo_notes/cron.log
```

Run a manual update to test:

```bash
REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts auto-update --all-repos
```

Or for a single repo:

```bash
REPO_CWD=$(pwd) && cd <plugin_root>/scripts && uv run python -m scripts auto-update
```
