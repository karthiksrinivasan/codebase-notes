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
            pass

    if all_changed:
        return NoteReport(
            note_path=str(note_path),
            status=StalenessStatus.STALE,
            changed_files=all_changed,
            commit=last_commit,
            message=f"{len(all_changed)} files changed since {last_commit}",
        )

    return NoteReport(
        note_path=str(note_path),
        status=StalenessStatus.FRESH,
        commit=last_commit,
        message="0 files changed",
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

    # Prune invalid paths by rewriting the file
    if valid_paths != [l.strip() for l in lines if l.strip()]:
        repo_paths_file.write_text(
            "\n".join(valid_paths) + "\n", encoding="utf-8"
        )

    return first_valid


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
        from scripts.repo_id import get_repo_dir, get_notes_dir

        if getattr(args, "all_repos", False):
            repo_notes_root = Path.home() / ".claude" / "repo_notes"
            results = check_all_repos(repo_notes_root)
            for repo_id, reports in results.items():
                print(f"\n=== {repo_id} ===")
                print(format_report(reports))
            return 0

        repo_dir = get_repo_dir()
        notes_dir = get_notes_dir()

        if not getattr(args, "no_cache", False) and is_cache_valid(repo_dir):
            cached = load_cache(repo_dir)
            if cached:
                print("(cached)")
                for r in cached:
                    print(f"  {r['status']}: {Path(r['note_path']).name}")
                return 0

        # Find a valid clone path
        import os
        repo_root = Path(os.getcwd())

        reports = check_all_notes(notes_dir, repo_root)
        save_cache(repo_dir, reports)
        print(format_report(reports))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
