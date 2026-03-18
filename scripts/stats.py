"""Display statistics for codebase notes directories."""

import sys
from pathlib import Path

from scripts.repo_id import get_repo_dir


def _count_dir(base: Path) -> dict:
    """Count sections (subfolders), files, lines, and words under a directory."""
    if not base.is_dir():
        return {"sections": 0, "files": 0, "lines": 0, "words": 0}

    sections = 0
    files = 0
    lines = 0
    words = 0

    for item in sorted(base.rglob("*")):
        if item.is_dir():
            # Only count direct children as sections
            if item.parent == base:
                sections += 1
        elif item.is_file() and item.suffix == ".md":
            files += 1
            try:
                text = item.read_text(encoding="utf-8")
                lines += text.count("\n")
                words += len(text.split())
            except (OSError, UnicodeDecodeError):
                pass

    return {"sections": sections, "files": files, "lines": lines, "words": words}


def collect_stats(repo_dir: Path) -> dict:
    """Collect stats for all four directories under a repo."""
    dirs = {
        "notes": repo_dir / "notes",
        "research": repo_dir / "research",
        "commits": repo_dir / "commits",
        "projects": repo_dir / "projects",
    }
    result = {}
    for name, path in dirs.items():
        result[name] = _count_dir(path)
    return result


def format_stats(stats: dict, repo_id: str) -> str:
    """Format stats into a readable table."""
    lines = []
    lines.append(f"Codebase Notes Stats — {repo_id}")
    lines.append("=" * len(lines[0]))
    lines.append("")
    lines.append(f"{'Directory':<12} {'Sections':>8} {'Files':>8} {'Lines':>8} {'Words':>8}")
    lines.append(f"{'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    totals = {"sections": 0, "files": 0, "lines": 0, "words": 0}
    for name in ("notes", "research", "commits", "projects"):
        s = stats[name]
        lines.append(f"{name:<12} {s['sections']:>8} {s['files']:>8} {s['lines']:>8} {s['words']:>8}")
        for k in totals:
            totals[k] += s[k]

    lines.append(f"{'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    lines.append(f"{'TOTAL':<12} {totals['sections']:>8} {totals['files']:>8} {totals['lines']:>8} {totals['words']:>8}")
    return "\n".join(lines)


def format_json(stats: dict, repo_id: str) -> str:
    """Format stats as JSON."""
    import json
    return json.dumps({"repo_id": repo_id, **stats}, indent=2)


def run(args) -> int:
    try:
        repo_dir = get_repo_dir()
        repo_id = repo_dir.name

        if not repo_dir.is_dir():
            print(f"No notes found for {repo_id}", file=sys.stderr)
            return 1

        stats = collect_stats(repo_dir)

        if getattr(args, "json", False):
            print(format_json(stats, repo_id))
        else:
            print(format_stats(stats, repo_id))

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
