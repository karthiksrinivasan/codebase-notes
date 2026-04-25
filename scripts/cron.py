"""Cron installation/uninstall, auto-update orchestration, and lock file management.

Provides:
- acquire_lock / release_lock for .cron.lock PID-based locking
- install/uninstall launchd plist (macOS) or crontab (Linux)
- auto_update: staleness check -> spawn claude for stale notes
- auto_update_all_repos: iterate all repos
"""

import datetime
import os
import platform
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.vault import VAULTS_BASE, read_vault_config

REPO_NOTES_BASE = Path.home() / ".claude" / "repo_notes"
LOCK_FILE = VAULTS_BASE / ".cron.lock"
LOG_FILE = VAULTS_BASE / "cron.log"
SCRIPTS_DIR = Path.home() / ".claude" / "skills" / "codebase-notes" / "scripts"
SKILL_MD = Path.home() / ".claude" / "skills" / "codebase-notes" / "SKILL.md"
PLIST_LABEL = "com.codebase-notes.auto-update"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

MAX_REPOS_PER_RUN = 5
PER_REPO_TIMEOUT = 600  # 10 minutes


# --- Lock file management ---


def acquire_lock(lock_path: Path = LOCK_FILE) -> bool:
    """Acquire a PID-based lock file.

    Returns True if lock acquired, False if another live process holds it.
    Removes stale locks (dead processes or non-numeric content).
    """
    if lock_path.exists():
        try:
            pid_str = lock_path.read_text().strip()
            pid = int(pid_str)
        except (ValueError, OSError):
            # Garbage content — treat as stale
            lock_path.unlink(missing_ok=True)
        else:
            # Check if process is alive
            try:
                os.kill(pid, 0)  # Signal 0 = check existence
                return False  # Process is alive, cannot acquire
            except OSError:
                # Process is dead — stale lock
                lock_path.unlink(missing_ok=True)

    # Write our PID
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))
    return True


def release_lock(lock_path: Path = LOCK_FILE) -> None:
    """Release the lock file by removing it."""
    lock_path.unlink(missing_ok=True)


def log_message(message: str, log_path: Path = LOG_FILE) -> None:
    """Append a timestamped message to the cron log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


# --- Plist / crontab generation ---


def generate_plist_content(interval_hours: int = 6) -> str:
    """Generate launchd plist XML content for auto-update scheduling.

    Args:
        interval_hours: How often to run, in hours. Converted to seconds for launchd.

    Returns:
        Complete plist XML string.
    """
    interval_seconds = interval_hours * 3600
    # Use /bin/bash -c so we can cd first
    # NOTE: &amp;&amp; is XML-escaped && — required for valid plist XML. Do not "fix" to &&.
    command = f"cd {SCRIPTS_DIR} &amp;&amp; uv run python -m scripts auto-update --all-repos"

    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{PLIST_LABEL}</string>
            <key>ProgramArguments</key>
            <array>
                <string>/bin/bash</string>
                <string>-c</string>
                <string>{command}</string>
            </array>
            <key>WorkingDirectory</key>
            <string>{SCRIPTS_DIR}</string>
            <key>StartInterval</key>
            <integer>{interval_seconds}</integer>
            <key>StandardOutPath</key>
            <string>{LOG_FILE}</string>
            <key>StandardErrorPath</key>
            <string>{LOG_FILE}</string>
            <key>RunAtLoad</key>
            <false/>
        </dict>
        </plist>
    """)


def generate_crontab_entry(interval_hours: int = 6) -> str:
    """Generate a crontab line for Linux fallback.

    Args:
        interval_hours: How often to run, in hours.

    Returns:
        Single crontab line string.
    """
    return f"0 */{interval_hours} * * * cd {SCRIPTS_DIR} && uv run python -m scripts auto-update --all-repos >> {LOG_FILE} 2>&1"


CRONTAB_MARKER = "# codebase-notes-auto-update"


def install_cron(interval_hours: int = 6) -> str:
    """Install cron schedule. Uses launchd on macOS, crontab on Linux.

    Returns:
        Human-readable message about what was installed.
    """
    system = platform.system()

    if system == "Darwin":
        # macOS: write plist and load it
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        content = generate_plist_content(interval_hours)
        PLIST_PATH.write_text(content)
        subprocess.run(
            ["launchctl", "load", str(PLIST_PATH)],
            check=False,
            capture_output=True,
        )
        return f"Installed launchd plist at {PLIST_PATH} (every {interval_hours}h)"

    elif system == "Linux":
        # Linux: add crontab entry
        entry = generate_crontab_entry(interval_hours)
        tagged_entry = f"{entry} {CRONTAB_MARKER}"

        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True
        )
        existing = result.stdout if result.returncode == 0 else ""

        # Remove any existing codebase-notes entry
        lines = [
            line for line in existing.splitlines()
            if CRONTAB_MARKER not in line
        ]
        lines.append(tagged_entry)

        # Write new crontab
        new_crontab = "\n".join(lines) + "\n"
        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True,
        )
        return f"Installed crontab entry (every {interval_hours}h)"

    else:
        return f"Unsupported platform: {system}. Manually schedule: cd {SCRIPTS_DIR} && uv run python -m scripts auto-update --all-repos"


def uninstall_cron() -> str:
    """Remove cron schedule.

    Returns:
        Human-readable message about what was removed.
    """
    system = platform.system()

    if system == "Darwin":
        if PLIST_PATH.exists():
            subprocess.run(
                ["launchctl", "unload", str(PLIST_PATH)],
                check=False,
                capture_output=True,
            )
            PLIST_PATH.unlink()
            return f"Removed launchd plist at {PLIST_PATH}"
        return "No plist found to remove."

    elif system == "Linux":
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True
        )
        if result.returncode != 0:
            return "No crontab found."

        lines = [
            line for line in result.stdout.splitlines()
            if CRONTAB_MARKER not in line
        ]
        new_crontab = "\n".join(lines) + "\n" if lines else ""
        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True,
        )
        return "Removed crontab entry for codebase-notes."

    else:
        return f"Unsupported platform: {system}"


# --- Auto-update orchestration ---


def build_update_prompt(stale_entries: list[dict], repo_id: str) -> str:
    """Build the prompt string sent to claude for updating stale notes.

    Args:
        stale_entries: List of dicts with keys: note, changed_files, files_changed
        repo_id: The repo identifier

    Returns:
        Prompt string for claude -p
    """
    from scripts.vault import get_vault_dir
    notes_dir = get_vault_dir(repo_id) / "notes"
    lines = [
        f"You are updating codebase notes for repo '{repo_id}'.",
        f"Notes are at: {notes_dir}",
        "",
        "The following notes are STALE and need updating:",
        "",
    ]

    for entry in stale_entries:
        lines.append(f"### {entry['note']} ({entry['files_changed']} files changed)")
        lines.append("Changed files:")
        for f in entry["changed_files"]:
            lines.append(f"  - {f}")
        lines.append("")

    lines.extend([
        "For each stale note:",
        "1. Read the current note",
        "2. Check the changed files listed above to understand what changed",
        "3. Update the note content to reflect the current state of the code",
        "4. Update the git_tracked_paths commit hashes in frontmatter",
        "5. Update last_updated date",
        "",
        "Do NOT create new notes. Only update the listed stale notes.",
    ])

    return "\n".join(lines)


def spawn_claude_for_repo(
    prompt: str,
    working_dir: Path,
    timeout: int = PER_REPO_TIMEOUT,
) -> dict:
    """Spawn a non-interactive claude session to update notes.

    Args:
        prompt: The update prompt
        working_dir: Directory to run claude from (a valid git clone)
        timeout: Max seconds to wait

    Returns:
        Dict with keys: status ("success", "timeout", "error"), message
    """
    cmd = [
        "claude",
        "-p", prompt,
        "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
        "-C", str(SKILL_MD),
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(working_dir),
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {"status": "success", "message": result.stdout[:500]}
        else:
            return {"status": "error", "message": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": f"Killed after {timeout}s"}
    except FileNotFoundError:
        return {"status": "error", "message": "claude CLI not found"}


def select_top_stale_repos(
    repos: list[dict],
    max_repos: int = MAX_REPOS_PER_RUN,
) -> list[dict]:
    """Select the top N stale repos sorted by severity (most changed files first).

    Args:
        repos: List of dicts with repo_id, total_changed_files, stale_notes, clone_path
        max_repos: Maximum number of repos to return

    Returns:
        Top repos sorted by total_changed_files descending.
    """
    sorted_repos = sorted(repos, key=lambda r: r["total_changed_files"], reverse=True)
    return sorted_repos[:max_repos]


def get_all_stale_repos() -> list[dict]:
    """Scan all repos in REPO_NOTES_BASE and return staleness info.

    Delegates to staleness.py for actual checking. Returns a list of dicts
    for repos that have at least one stale note, including a valid clone_path.
    """
    from scripts.staleness import check_all_notes, StalenessStatus, _find_valid_clone

    stale_repos: list[dict] = []
    if not REPO_NOTES_BASE.exists():
        return stale_repos

    for repo_dir in REPO_NOTES_BASE.iterdir():
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue

        repo_id = repo_dir.name
        notes_dir = repo_dir / "notes"
        repo_paths_file = repo_dir / ".repo_paths"

        clone_path = _find_valid_clone(repo_paths_file, repo_id)
        if clone_path is None:
            log_message(f"{repo_id}: skipped — no valid clone path")
            continue

        reports = check_all_notes(notes_dir, clone_path)
        stale_entries = []
        for r in reports:
            if r.status == StalenessStatus.STALE:
                stale_entries.append({
                    "note": r.note_path,
                    "changed_files": r.changed_files,
                    "files_changed": len(r.changed_files),
                })

        if stale_entries:
            total_changed = sum(e["files_changed"] for e in stale_entries)
            stale_repos.append({
                "repo_id": repo_id,
                "total_changed_files": total_changed,
                "stale_notes": stale_entries,
                "clone_path": str(clone_path),
            })

    return stale_repos


def get_all_stale_vaults(vaults_base: Path | None = None) -> list[dict]:
    """Scan all vaults and return staleness info."""
    from scripts.staleness import check_all_notes, StalenessStatus, _find_valid_clone_from_list

    base = vaults_base or VAULTS_BASE
    stale_repos = []
    if not base.is_dir():
        return stale_repos

    for vault_dir in sorted(base.iterdir()):
        if not vault_dir.is_dir() or vault_dir.name.startswith("."):
            continue
        config = read_vault_config(vault_dir)
        if config is None:
            continue
        repo_id = config.get("repo_id", vault_dir.name)
        clone_paths = config.get("clone_paths", [])
        clone_path = _find_valid_clone_from_list(clone_paths, repo_id)
        if clone_path is None:
            log_message(f"{repo_id}: skipped — no valid clone path")
            continue
        notes_dir = vault_dir / "notes"
        reports = check_all_notes(notes_dir, clone_path)
        stale_entries = []
        for r in reports:
            if r.status == StalenessStatus.STALE:
                stale_entries.append({
                    "note": r.note_path,
                    "changed_files": r.changed_files,
                    "files_changed": len(r.changed_files),
                })
        if stale_entries:
            total_changed = sum(e["files_changed"] for e in stale_entries)
            stale_repos.append({
                "repo_id": repo_id,
                "total_changed_files": total_changed,
                "stale_notes": stale_entries,
                "clone_path": str(clone_path),
            })
    return stale_repos


def auto_update_all_repos() -> None:
    """Main entry point for cron-triggered auto-update of all repos.

    Acquires lock, checks staleness, spawns claude for top stale repos,
    logs outcomes, releases lock.
    """
    if not acquire_lock(LOCK_FILE):
        log_message("Skipped: previous run still active (lock held)")
        return

    try:
        log_message("Auto-update started")
        stale_repos = get_all_stale_vaults()

        if not stale_repos:
            log_message("No stale repos found")
            return

        selected = select_top_stale_repos(stale_repos)
        log_message(f"Processing {len(selected)} of {len(stale_repos)} stale repos")

        for repo in selected:
            repo_id = repo["repo_id"]
            clone_path = Path(repo["clone_path"])
            prompt = build_update_prompt(repo["stale_notes"], repo_id)

            log_message(f"{repo_id}: starting update ({repo['total_changed_files']} files changed)")
            result = spawn_claude_for_repo(prompt, clone_path)
            log_message(f"{repo_id}: {result['status']} — {result['message'][:200]}")

    except Exception as e:
        log_message(f"Auto-update error: {e}")
    finally:
        release_lock(LOCK_FILE)
        log_message("Auto-update finished")


def auto_update_single_repo(repo_id: str) -> None:
    """Run auto-update for a single repo.

    Args:
        repo_id: The repo identifier.
    """
    from scripts.staleness import check_all_notes, StalenessStatus, _find_valid_clone

    repo_dir = REPO_NOTES_BASE / repo_id
    notes_dir = repo_dir / "notes"
    repo_paths_file = repo_dir / ".repo_paths"

    clone_path = _find_valid_clone(repo_paths_file, repo_id)
    if clone_path is None:
        print(f"Error: no valid clone path for {repo_id}", file=sys.stderr)
        return

    reports = check_all_notes(notes_dir, clone_path)
    stale_entries = []
    for r in reports:
        if r.status == StalenessStatus.STALE:
            stale_entries.append({
                "note": r.note_path,
                "changed_files": r.changed_files,
                "files_changed": len(r.changed_files),
            })

    if not stale_entries:
        print(f"No stale notes for {repo_id}")
        return

    prompt = build_update_prompt(stale_entries, repo_id)
    print(f"Updating {len(stale_entries)} stale notes for {repo_id}...")
    result = spawn_claude_for_repo(prompt, clone_path)
    print(f"Result: {result['status']} — {result['message'][:200]}")


# --- Interval parsing ---


def parse_interval(interval: str | None) -> int:
    """Parse interval string like '6h' into integer hours.

    Args:
        interval: String like '6h', '12h'. None defaults to 6.

    Returns:
        Integer hours.

    Raises:
        ValueError: If format is not Nh.
    """
    if interval is None:
        return 6

    match = re.fullmatch(r"(\d+)h", interval)
    if not match:
        raise ValueError(f"Invalid interval format '{interval}'. Expected format: Nh (e.g., 6h, 12h)")
    return int(match.group(1))


# --- CLI helpers ---


def handle_cron(install: bool, uninstall: bool, interval: str | None) -> None:
    """Handle the 'cron' CLI command.

    Args:
        install: Whether --install was passed.
        uninstall: Whether --uninstall was passed.
        interval: Interval string like '6h', or None for default.
    """
    if install:
        hours = parse_interval(interval)
        result = install_cron(interval_hours=hours)
        print(result)
    elif uninstall:
        result = uninstall_cron()
        print(result)
    else:
        print("Usage: cron --install [--interval=6h] | cron --uninstall", file=sys.stderr)
        sys.exit(1)


def handle_auto_update(repo_id: str | None, all_repos: bool) -> None:
    """Handle the 'auto-update' CLI command.

    Args:
        repo_id: Specific repo ID, or None to resolve from cwd.
        all_repos: Whether --all-repos was passed.
    """
    if all_repos:
        auto_update_all_repos()
    elif repo_id:
        auto_update_single_repo(repo_id)
    else:
        # Resolve from current directory
        from scripts.repo_id import get_repo_id
        resolved_id = get_repo_id()
        auto_update_single_repo(resolved_id)


# --- Entry points for __main__.py dispatch ---


def run_cron(args) -> int:
    """Entry point for 'cron' subcommand."""
    try:
        handle_cron(
            install=getattr(args, "install", False),
            uninstall=getattr(args, "uninstall", False),
            interval=getattr(args, "interval", None),
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_auto_update(args) -> int:
    """Entry point for 'auto-update' subcommand."""
    try:
        handle_auto_update(
            repo_id=getattr(args, "repo_id", None),
            all_repos=getattr(args, "all_repos", False),
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
