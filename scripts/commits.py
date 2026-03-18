"""Git commit history extraction, grouping, and markdown generation.

Runs git log, groups commits by author and path prefix, outputs markdown
files to ~/.claude/repo_notes/<repo_id>/commits/<author>/<path-slug>.md.
"""

import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class Commit:
    """A single parsed git commit."""
    hash: str
    author: str
    email: str
    date: str
    subject: str


def parse_git_log_output(raw: str) -> list[Commit]:
    """Parse output of git log --format='%H|%an|%ae|%ad|%s' into Commit objects.

    Lines that don't match the expected 5-field pipe format are silently skipped.
    """
    commits: list[Commit] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|", maxsplit=4)
        if len(parts) != 5:
            continue
        commits.append(Commit(
            hash=parts[0].strip(),
            author=parts[1].strip(),
            email=parts[2].strip(),
            date=parts[3].strip(),
            subject=parts[4].strip(),
        ))
    return commits


def group_commits_by_author(commits: list[Commit]) -> dict[str, list[Commit]]:
    """Group a list of commits by author name."""
    grouped: dict[str, list[Commit]] = defaultdict(list)
    for c in commits:
        grouped[c.author].append(c)
    return dict(grouped)


def group_by_path_prefix(paths: list[str], depth: int = 2) -> dict[str, list[str]]:
    """Group file paths by their prefix up to `depth` directory levels.

    Files at the root level are grouped under '.'.
    """
    grouped: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        parts = Path(p).parts
        if len(parts) <= depth:
            prefix = str(Path(*parts[:-1])) if len(parts) > 1 else "."
        else:
            prefix = str(Path(*parts[:depth]))
        grouped[prefix].append(p)
    return dict(grouped)


# ---------------------------------------------------------------------------
# Slug + frontmatter helpers
# ---------------------------------------------------------------------------

def path_to_slug(path: str) -> str:
    """Convert a path like 'src/api/' to a filename slug like 'src-api'."""
    cleaned = path.strip("/").strip()
    if not cleaned or cleaned == ".":
        return "root"
    return re.sub(r"[/\\]+", "-", cleaned)


def parse_frontmatter(md: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a markdown string (between --- delimiters)."""
    match = re.match(r"^---\n(.*?)\n---", md, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def _format_date_short(date_str: str) -> str:
    """Extract a short date like '2026-03-10' from git's verbose date format."""
    # Try to parse git's default date format
    for fmt in ("%a %b %d %H:%M:%S %Y %z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Fallback: return as-is truncated
    return date_str.strip()[:10]


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def generate_commit_markdown(
    author: str,
    email: str,
    path_filter: str,
    commits: list[Commit],
    date_range: str,
) -> str:
    """Generate a complete markdown file with frontmatter, commit table, and summary placeholder.

    Args:
        author: Author display name.
        email: Author email.
        path_filter: Path scope (e.g., 'src/api/').
        commits: List of Commit objects to include.
        date_range: Human-readable date range string (e.g., '2026-02-18 to 2026-03-18').

    Returns:
        Complete markdown string.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    path_display = path_filter if path_filter and path_filter != "." else "(all paths)"

    frontmatter = yaml.dump(
        {
            "author": author,
            "author_email": email,
            "path_filter": path_filter,
            "date_range": date_range,
            "last_updated": today,
        },
        default_flow_style=False,
        sort_keys=False,
    ).strip()

    lines = [
        f"---\n{frontmatter}\n---",
        f"# {author} — {path_display}",
        "",
        "## Summary",
        "",
        "[Claude-generated narrative summary — to be filled by Claude]",
        "",
        "## Commits",
        "",
        "| Date | Message | Hash |",
        "|------|---------|------|",
    ]

    for c in commits:
        short_date = _format_date_short(c.date)
        short_hash = c.hash[:8]
        # Escape pipes in subject
        safe_subject = c.subject.replace("|", "\\|")
        lines.append(f"| {short_date} | {safe_subject} | `{short_hash}` |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Merge / deduplication
# ---------------------------------------------------------------------------

def _extract_commit_hashes_from_table(md: str) -> set[str]:
    """Extract all commit hashes (short, 8-char) from the markdown commit table."""
    hashes: set[str] = set()
    for match in re.finditer(r"`([0-9a-f]{8})`", md):
        hashes.add(match.group(1))
    return hashes


def _extract_sections(md: str) -> dict[str, str]:
    """Split markdown into: 'frontmatter', 'summary', 'commits_header', 'commits_table', 'rest'."""
    sections: dict[str, str] = {}

    # Frontmatter
    fm_match = re.match(r"^(---\n.*?\n---)\n", md, re.DOTALL)
    if fm_match:
        sections["frontmatter"] = fm_match.group(1)
        remainder = md[fm_match.end():]
    else:
        sections["frontmatter"] = ""
        remainder = md

    # Split at ## Summary and ## Commits
    summary_match = re.search(r"(## Summary\n.*?)(?=\n## Commits)", remainder, re.DOTALL)
    if summary_match:
        sections["pre_summary"] = remainder[:summary_match.start()]
        sections["summary"] = summary_match.group(1)
    else:
        sections["pre_summary"] = remainder
        sections["summary"] = "## Summary\n\n[Claude-generated narrative summary — to be filled by Claude]\n"

    commits_match = re.search(r"(## Commits\n.*)", remainder, re.DOTALL)
    if commits_match:
        sections["commits"] = commits_match.group(1)
    else:
        sections["commits"] = ""

    return sections


def merge_commits_into_existing(
    existing_md: str,
    new_commits: list[Commit],
    date_range: str,
) -> str:
    """Merge new commits into an existing markdown file, deduplicating by hash.

    Preserves the existing Summary section (which Claude may have written).
    Updates frontmatter date_range and last_updated.
    """
    existing_hashes = _extract_commit_hashes_from_table(existing_md)
    sections = _extract_sections(existing_md)

    # Filter to only truly new commits
    unique_new = [c for c in new_commits if c.hash[:8] not in existing_hashes]

    # Build new table rows from unique new commits
    new_rows: list[str] = []
    for c in unique_new:
        short_date = _format_date_short(c.date)
        short_hash = c.hash[:8]
        safe_subject = c.subject.replace("|", "\\|")
        new_rows.append(f"| {short_date} | {safe_subject} | `{short_hash}` |")

    # Rebuild commits section: existing table + new rows
    commits_section = sections.get("commits", "")
    if new_rows:
        # Append new rows before the trailing empty line
        commits_section = commits_section.rstrip("\n")
        commits_section += "\n" + "\n".join(new_rows) + "\n"

    # Update frontmatter
    fm = parse_frontmatter(existing_md)
    fm["date_range"] = date_range
    fm["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    new_frontmatter = "---\n" + yaml.dump(fm, default_flow_style=False, sort_keys=False).strip() + "\n---"

    # Reassemble
    result = (
        new_frontmatter + "\n"
        + sections.get("pre_summary", "")
        + sections["summary"] + "\n"
        + commits_section
    )
    return result


# ---------------------------------------------------------------------------
# Git subprocess wrapper
# ---------------------------------------------------------------------------

def run_git_log(
    since: Optional[str] = None,
    path: Optional[str] = None,
    cwd: Optional[str] = None,
) -> list[Commit]:
    """Run git log and return parsed commits.

    Args:
        since: Git --since value (default '4w').
        path: Optional path filter for git log.
        cwd: Working directory for git command.

    Returns:
        List of Commit objects (empty on error).
    """
    since = since or "4w"
    cmd = [
        "git", "log",
        "--format=%H|%an|%ae|%ad|%s",
        f"--since={since}",
    ]
    if path:
        cmd.append("--")
        cmd.append(path)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        if result.returncode != 0:
            return []
        return parse_git_log_output(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_changed_files_for_commit(commit_hash: str, cwd: Optional[str] = None) -> list[str]:
    """Get list of files changed in a commit."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _author_to_dirname(author: str) -> str:
    """Convert author name to a safe directory name."""
    return re.sub(r"[^\w\s-]", "", author).strip().replace(" ", "-").lower()


# ---------------------------------------------------------------------------
# Lazy imports for repo_id (avoids circular imports at module level)
# ---------------------------------------------------------------------------

def _resolve_repo_id(cwd: Optional[str] = None) -> str:
    from scripts.repo_id import resolve_repo_id as _resolve
    return _resolve(cwd=cwd)


def _get_notes_dir(repo_id: str) -> Path:
    """Return repo base dir for repo_id (parent of 'commits/' and 'notes/' dirs)."""
    return Path.home() / ".claude" / "repo_notes" / repo_id


# Public aliases used by tests for patching
resolve_repo_id = _resolve_repo_id
get_notes_dir = _get_notes_dir


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def run_commits_command(
    author: Optional[str] = None,
    since: Optional[str] = None,
    path: Optional[str] = None,
    repo_id: Optional[str] = None,
    cwd: Optional[str] = None,
    depth: int = 2,
) -> None:
    """Main entry point for the 'commits' CLI command.

    Fetches git log, groups by author and path prefix, writes markdown files.
    Supports merge mode: if output file exists, deduplicates commits.
    """
    rid = repo_id or resolve_repo_id(cwd=cwd)
    notes_base = get_notes_dir(rid)
    commits_dir = notes_base / "commits"
    commits_dir.mkdir(parents=True, exist_ok=True)

    # Fetch commits
    all_commits = run_git_log(since=since, path=path, cwd=cwd)
    if not all_commits:
        print("No commits found.")
        return

    # Group by author
    by_author = group_commits_by_author(all_commits)

    # Filter to specific author if requested
    if author:
        if author in by_author:
            by_author = {author: by_author[author]}
        else:
            # Try case-insensitive match
            matched = {k: v for k, v in by_author.items() if k.lower() == author.lower()}
            if matched:
                by_author = matched
            else:
                print(f"No commits found for author: {author}")
                return

    # Compute date range
    since_val = since or "4w"
    today = datetime.now().strftime("%Y-%m-%d")
    # Approximate start date from --since
    date_range = f"last {since_val} to {today}"
    if all_commits:
        dates = [c.date for c in all_commits]
        first_short = _format_date_short(dates[-1])
        last_short = _format_date_short(dates[0])
        date_range = f"{first_short} to {last_short}"

    # For each author, group their commits by path prefix and write files
    for auth_name, auth_commits in by_author.items():
        auth_dir = commits_dir / _author_to_dirname(auth_name)
        auth_dir.mkdir(parents=True, exist_ok=True)

        # If we have a specific path filter, use it as the slug directly
        if path:
            slug = path_to_slug(path)
            _write_commit_file(
                auth_dir, slug, auth_name, auth_commits[0].email,
                path, auth_commits, date_range,
            )
        else:
            # Group by path prefix (we use "root" for all since we don't have per-commit files here)
            slug = "all"
            _write_commit_file(
                auth_dir, slug, auth_name, auth_commits[0].email,
                ".", auth_commits, date_range,
            )

    print(f"Generated commit notes for {len(by_author)} author(s) in {commits_dir}")


def _write_commit_file(
    auth_dir: Path,
    slug: str,
    author: str,
    email: str,
    path_filter: str,
    commits: list[Commit],
    date_range: str,
) -> None:
    """Write or merge a commit markdown file."""
    out_file = auth_dir / f"{slug}.md"

    if out_file.exists():
        existing_md = out_file.read_text(encoding="utf-8")
        merged = merge_commits_into_existing(existing_md, commits, date_range)
        out_file.write_text(merged, encoding="utf-8")
    else:
        md = generate_commit_markdown(
            author=author,
            email=email,
            path_filter=path_filter,
            commits=commits,
            date_range=date_range,
        )
        out_file.write_text(md, encoding="utf-8")


def run(args) -> int:
    """CLI entry point called from __main__.py."""
    run_commits_command(
        author=getattr(args, "author", None),
        since=getattr(args, "since", None),
        path=getattr(args, "path", None) or None,
        repo_id=getattr(args, "repo_id", None),
    )
    return 0
