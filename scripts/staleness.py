"""Staleness checking for codebase notes.

Parses YAML frontmatter from .md files, runs git diff to detect changes
since the tracked commit, and outputs a structured staleness report.
Supports caching and --all-repos mode.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class StalenessStatus(Enum):
    """Status of a note's freshness."""
    FRESH = "FRESH"
    STALE = "STALE"
    NO_TRACKING = "NO_TRACKING"


@dataclass
class NoteReport:
    """Staleness report for a single note."""
    note_path: str
    status: StalenessStatus
    changed_files: list[str] = field(default_factory=list)
    commit: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "note_path": self.note_path,
            "status": self.status.value,
            "changed_files": self.changed_files,
            "commit": self.commit,
            "message": self.message,
        }


def parse_frontmatter(filepath: Path) -> Optional[dict]:
    """Parse YAML frontmatter from a markdown file."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if not text.startswith("---"):
        return None

    lines = text.split("\n")
    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        return None

    frontmatter_text = "\n".join(lines[1:closing_idx])
    try:
        return yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None


def check_note_staleness(note_path: Path, repo_root: Path) -> NoteReport:
    """Check staleness of a single note by running git diff for each tracked path."""
    fm = parse_frontmatter(note_path)
    if fm is None or "git_tracked_paths" not in fm:
        return NoteReport(
            note_path=str(note_path),
            status=StalenessStatus.NO_TRACKING,
            message="no git_tracked_paths in frontmatter",
        )

    all_changed: list[str] = []
    last_commit = None
    had_errors = False

    for entry in fm["git_tracked_paths"]:
        path = entry.get("path", "")
        commit = entry.get("commit", "")
        if not path or not commit:
            continue
        last_commit = commit

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", commit, "HEAD", "--", path],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                changed = result.stdout.strip().split("\n")
                all_changed.extend(changed)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            had_errors = True

    if all_changed:
        return NoteReport(
            note_path=str(note_path),
            status=StalenessStatus.STALE,
            changed_files=all_changed,
            commit=last_commit,
            message=f"{len(all_changed)} files changed since {last_commit}",
        )

    msg = "0 files changed" + (" (some checks failed)" if had_errors else "")
    return NoteReport(
        note_path=str(note_path),
        status=StalenessStatus.FRESH,
        commit=last_commit,
        message=msg,
    )


def check_all_notes(notes_dir: Path, repo_root: Path) -> list[NoteReport]:
    """Check staleness of all .md files in a notes directory."""
    reports: list[NoteReport] = []
    if not notes_dir.is_dir():
        return reports

    for md_file in sorted(notes_dir.rglob("*.md")):
        reports.append(check_note_staleness(md_file, repo_root))

    return reports


# --- Caching ---

CACHE_TTL_SECONDS = 600  # 10 minutes


def _cache_path(repo_notes_dir: Path) -> Path:
    return repo_notes_dir / ".staleness_cache"


def save_cache(repo_notes_dir: Path, reports: list[NoteReport]) -> None:
    cache_file = _cache_path(repo_notes_dir)
    data = {
        "timestamp": time.time(),
        "reports": [r.to_dict() for r in reports],
    }
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_cache(repo_notes_dir: Path) -> Optional[list[dict]]:
    cache_file = _cache_path(repo_notes_dir)
    if not cache_file.is_file():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data.get("reports")
    except (json.JSONDecodeError, OSError):
        return None


def is_cache_valid(repo_notes_dir: Path, ttl: int = CACHE_TTL_SECONDS) -> bool:
    cache_file = _cache_path(repo_notes_dir)
    if not cache_file.is_file():
        return False
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        ts = data.get("timestamp", 0)
        return (time.time() - ts) < ttl
    except (json.JSONDecodeError, OSError):
        return False


def check_all_repos(repo_notes_root: Path) -> dict[str, list[NoteReport]]:
    """Check staleness for all repos in ~/.claude/repo_notes/."""
    from scripts.repo_id import get_repo_id

    results: dict[str, list[NoteReport]] = {}
    if not repo_notes_root.is_dir():
        return results

    for repo_dir in sorted(repo_notes_root.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue

        repo_id = repo_dir.name
        repo_paths_file = repo_dir / ".repo_paths"

        valid_clone = _find_valid_clone(repo_paths_file, repo_id)
        if valid_clone is None:
            print(f"WARNING: {repo_id} — no valid clone path found, skipping")
            results[repo_id] = []
            continue

        notes_dir = repo_dir / "notes"
        reports = check_all_notes(notes_dir, valid_clone)
        results[repo_id] = reports

    return results


def _find_valid_clone(repo_paths_file: Path, expected_repo_id: str) -> Optional[Path]:
    """Find the first valid clone path from a .repo_paths file."""
    if not repo_paths_file.is_file():
        return None

    from scripts.repo_id import get_repo_id

    lines = repo_paths_file.read_text(encoding="utf-8").strip().split("\n")
    valid_paths: list[str] = []
    first_valid: Optional[Path] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        clone_path = Path(line)
        if not clone_path.is_dir():
            continue
        if not (clone_path / ".git").exists():
            continue

        try:
            resolved_id = get_repo_id(clone_path)
        except Exception:
            continue

        if resolved_id != expected_repo_id:
            continue

        valid_paths.append(line)
        if first_valid is None:
            first_valid = clone_path

    # Prune invalid paths by rewriting the file (with locking)
    if valid_paths != [l.strip() for l in lines if l.strip()]:
        import fcntl
        import os
        lock_file = repo_paths_file.parent / ".repo_paths.lock"
        lock_file.touch(exist_ok=True)
        fd = os.open(str(lock_file), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            repo_paths_file.write_text(
                "\n".join(valid_paths) + "\n", encoding="utf-8"
            )
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    return first_valid


def generate_staleness_report(reports: list[NoteReport]) -> str:
    """Generate a Dataview-compatible markdown report with YAML frontmatter."""
    from datetime import date
    today = date.today().isoformat()
    lines = [
        "---",
        f"staleness_check: {today}",
        f"total_notes: {len(reports)}",
        f"stale_count: {sum(1 for r in reports if r.status == StalenessStatus.STALE)}",
        f"fresh_count: {sum(1 for r in reports if r.status == StalenessStatus.FRESH)}",
        "---",
        "# Staleness Report",
        "",
        "| Note | Status | Changed Files | Commit |",
        "|------|--------|---------------|--------|",
    ]
    for r in reports:
        note_name = Path(r.note_path).as_posix()
        changed = ", ".join(r.changed_files[:5])
        if len(r.changed_files) > 5:
            changed += f" (+{len(r.changed_files) - 5} more)"
        commit = r.commit or "—"
        lines.append(f"| {note_name} | {r.status.value} | {changed} | {commit} |")
    return "\n".join(lines) + "\n"


def write_staleness_report(vault_dir: Path, reports: list[NoteReport]) -> Path:
    """Write a staleness report to vault_dir/meta/staleness-report.md."""
    meta_dir = vault_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    report_path = meta_dir / "staleness-report.md"
    report_path.write_text(generate_staleness_report(reports), encoding="utf-8")
    return report_path


def _find_valid_clone_from_list(clone_paths: list[str], expected_repo_id: str) -> Optional[Path]:
    """Given a list of clone path strings, return the first valid one matching expected_repo_id."""
    from scripts.repo_id import get_repo_id
    for path_str in clone_paths:
        clone_path = Path(path_str)
        if not clone_path.is_dir() or not (clone_path / ".git").exists():
            continue
        try:
            if get_repo_id(str(clone_path)) == expected_repo_id:
                return clone_path
        except Exception:
            continue
    return None


def check_all_vaults(vaults_base: Path) -> dict[str, list[NoteReport]]:
    """Check staleness for all vaults in the given base directory."""
    from scripts.vault import read_vault_config
    results: dict[str, list[NoteReport]] = {}
    if not vaults_base.is_dir():
        return results
    for vault_dir in sorted(vaults_base.iterdir()):
        if not vault_dir.is_dir() or vault_dir.name.startswith("."):
            continue
        config = read_vault_config(vault_dir)
        if config is None:
            continue
        repo_id = config.get("repo_id", vault_dir.name)
        clone_paths = config.get("clone_paths", [])
        valid_clone = _find_valid_clone_from_list(clone_paths, repo_id)
        if valid_clone is None:
            print(f"WARNING: {repo_id} — no valid clone path found, skipping")
            results[repo_id] = []
            continue
        notes_dir = vault_dir / "notes"
        reports = check_all_notes(notes_dir, valid_clone)
        write_staleness_report(vault_dir, reports)
        results[repo_id] = reports
    return results


def format_report(reports: list[NoteReport]) -> str:
    """Format a list of NoteReports as a human-readable string."""
    lines: list[str] = []
    for r in reports:
        note_name = Path(r.note_path).name
        if r.status == StalenessStatus.FRESH:
            lines.append(f"FRESH: {note_name} ({r.message})")
        elif r.status == StalenessStatus.STALE:
            lines.append(f"STALE: {note_name} ({r.message})")
            for f in r.changed_files:
                lines.append(f"  - {f}")
        elif r.status == StalenessStatus.NO_TRACKING:
            lines.append(f"NO_TRACKING: {note_name} ({r.message})")
    return "\n".join(lines)


def run(args) -> int:
    try:
        from scripts.vault import VAULTS_BASE

        if getattr(args, "all_repos", False):
            results = check_all_vaults(VAULTS_BASE)
            for repo_id, reports in results.items():
                print(f"\n=== {repo_id} ===")
                print(format_report(reports))
            return 0

        explicit_id = getattr(args, "repo_id", None)
        if explicit_id:
            from scripts.vault import get_vault_dir
            vault_dir = get_vault_dir(explicit_id)
            notes_dir = vault_dir / "notes"
        else:
            from scripts.repo_id import get_repo_dir, get_notes_dir
            vault_dir = get_repo_dir()
            notes_dir = get_notes_dir()

        if not getattr(args, "no_cache", False) and is_cache_valid(vault_dir):
            cached = load_cache(vault_dir)
            if cached:
                print("(cached)")
                for r in cached:
                    print(f"  {r['status']}: {Path(r['note_path']).name}")
                return 0

        from scripts.repo_id import _resolve_cwd
        repo_root = Path(_resolve_cwd())

        reports = check_all_notes(notes_dir, repo_root)
        save_cache(vault_dir, reports)
        write_staleness_report(vault_dir, reports)

        if getattr(args, "json", False):
            print(json.dumps([r.to_dict() for r in reports], indent=2))
        else:
            print(format_report(reports))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
