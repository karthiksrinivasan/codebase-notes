"""Generate a compact, token-efficient index of all codebase notes for a repo.

Used by hooks to inject context at session start and after note changes.
"""

import json
import sys
from pathlib import Path
from typing import Optional


def _extract_title(filepath: Path) -> str:
    """Extract the first # heading from a markdown file."""
    try:
        for line in filepath.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return filepath.stem


def _extract_tracked_paths(filepath: Path) -> str:
    """Extract git_tracked_paths from YAML frontmatter as a compact string."""
    from scripts.staleness import parse_frontmatter

    fm = parse_frontmatter(filepath)
    if fm is None or "git_tracked_paths" not in fm:
        return ""
    paths = fm["git_tracked_paths"]
    if not paths:
        return ""
    return ", ".join(entry.get("path", "") for entry in paths if entry.get("path"))


def _extract_overview_description(overview_path: Path) -> str:
    """Extract a one-line description from notes/00-overview.md."""
    if not overview_path.is_file():
        return ""
    try:
        text = overview_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

    lines = text.splitlines()
    # Skip frontmatter
    start = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                start = i + 1
                break

    # Look for "What is this?" heading first
    found_heading = False
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if stripped.lower().startswith("## what is this"):
            found_heading = True
            start = i + 1
            break

    # Get the first non-empty paragraph line after the chosen start
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if stripped and not stripped.startswith("#"):
            return stripped

    return ""


def _load_staleness_map(repo_dir: Path) -> dict[str, str]:
    """Load staleness cache and return a dict mapping note_path -> status string."""
    from scripts.staleness import load_cache

    cached = load_cache(repo_dir)
    if cached is None:
        return {}
    result: dict[str, str] = {}
    for report in cached:
        note_path = report.get("note_path", "")
        status = report.get("status", "")
        if note_path and status:
            result[note_path] = status
    return result


def _build_notes_table(
    section_dir: Path,
    repo_dir: Path,
    staleness_map: dict[str, str],
) -> list[str]:
    """Build table rows for the notes/ directory."""
    rows: list[str] = []
    for md_file in sorted(section_dir.rglob("*.md")):
        if md_file.name == "RULES.md":
            continue
        rel = md_file.relative_to(repo_dir)
        title = _extract_title(md_file)
        tracked = _extract_tracked_paths(md_file)

        # Staleness: note_path in cache is relative to the notes/ directory
        note_rel = str(md_file.relative_to(section_dir))
        status = staleness_map.get(note_rel, "\u2014")

        rows.append(f"| {rel} | {title} | {status} | {tracked} |")
    return rows


def _build_research_table(
    section_dir: Path,
    repo_dir: Path,
    staleness_map: dict[str, str],
) -> list[str]:
    """Build table rows for the research/ directory."""
    rows: list[str] = []
    for md_file in sorted(section_dir.rglob("*.md")):
        if md_file.name == "RULES.md":
            continue
        rel = md_file.relative_to(repo_dir)
        title = _extract_title(md_file)

        note_rel = str(md_file.relative_to(section_dir))
        status = staleness_map.get(note_rel, "\u2014")

        rows.append(f"| {rel} | {title} | {status} |")
    return rows


def _build_projects_table(section_dir: Path, repo_dir: Path) -> list[str]:
    """Build table rows for the projects/ directory."""
    rows: list[str] = []
    for md_file in sorted(section_dir.rglob("*.md")):
        if md_file.name == "RULES.md":
            continue
        rel = md_file.relative_to(repo_dir)
        title = _extract_title(md_file)
        rows.append(f"| {rel} | {title} |")
    return rows


def _build_commits_table(section_dir: Path, repo_dir: Path) -> list[str]:
    """Build table rows for the commits/ directory."""
    rows: list[str] = []
    for md_file in sorted(section_dir.rglob("*.md")):
        if md_file.name == "RULES.md":
            continue
        rel = md_file.relative_to(repo_dir)
        # Author from parent directory name (slug)
        author = md_file.parent.name
        # Area from filename (without extension)
        area = md_file.stem
        rows.append(f"| {rel} | {author} | {area} |")
    return rows


def _build_code_reviews_table(section_dir: Path, repo_dir: Path) -> list[str]:
    """Build table rows for the code-reviews/ directory."""
    rows: list[str] = []
    for review_dir in sorted(section_dir.iterdir()):
        if not review_dir.is_dir() or review_dir.name.startswith("."):
            continue
        context_file = review_dir / "context.md"
        review_file = review_dir / "review.md"
        identifier = review_dir.name
        title = _extract_title(context_file) if context_file.is_file() else identifier
        has_review = "yes" if review_file.is_file() else "no"
        if context_file.is_file():
            rel_context = context_file.relative_to(repo_dir)
        else:
            rel_context = (section_dir / identifier / "context.md").relative_to(repo_dir)
        rows.append(f"| {rel_context} | {title} | {has_review} |")
    return rows


def _generate_index(repo_id: str, repo_dir: Path) -> str:
    """Generate the full markdown index content."""
    staleness_map = _load_staleness_map(repo_dir)

    # Overview description
    overview_path = repo_dir / "notes" / "00-overview.md"
    description = _extract_overview_description(overview_path)

    parts: list[str] = []
    parts.append(f"# Codebase Notes: {repo_id}")
    if description:
        parts.append(description)
    parts.append("")

    # notes/
    notes_dir = repo_dir / "notes"
    if notes_dir.is_dir():
        rows = _build_notes_table(notes_dir, repo_dir, staleness_map)
        if rows:
            parts.append("## notes/")
            parts.append("| Path | Title | Status | Tracked Paths |")
            parts.append("|------|-------|--------|---------------|")
            parts.extend(rows)
            parts.append("")

    # research/
    research_dir = repo_dir / "research"
    if research_dir.is_dir():
        rows = _build_research_table(research_dir, repo_dir, staleness_map)
        if rows:
            parts.append("## research/")
            parts.append("| Path | Title | Status |")
            parts.append("|------|-------|--------|")
            parts.extend(rows)
            parts.append("")

    # projects/
    projects_dir = repo_dir / "projects"
    if projects_dir.is_dir():
        rows = _build_projects_table(projects_dir, repo_dir)
        if rows:
            parts.append("## projects/")
            parts.append("| Path | Title |")
            parts.append("|------|-------|")
            parts.extend(rows)
            parts.append("")

    # commits/
    commits_dir = repo_dir / "commits"
    if commits_dir.is_dir():
        rows = _build_commits_table(commits_dir, repo_dir)
        if rows:
            parts.append("## commits/")
            parts.append("| Path | Author | Area |")
            parts.append("|------|--------|------|")
            parts.extend(rows)
            parts.append("")

    # code-reviews/
    code_reviews_dir = repo_dir / "code-reviews"
    if code_reviews_dir.is_dir():
        rows = _build_code_reviews_table(code_reviews_dir, repo_dir)
        if rows:
            parts.append("## code-reviews/")
            parts.append("| Path | Title | Reviewed |")
            parts.append("|------|-------|----------|")
            parts.extend(rows)
            parts.append("")

    parts.append("---")
    parts.append(f"Notes root: ~/.claude/repo_notes/{repo_id}/")
    parts.append("To explore a topic: read its index.md first, then read specific subtopics as needed.")
    parts.append("When a relevant note is STALE, mention it to the user and offer to update.")

    return "\n".join(parts)


def _wrap_json_envelope(content: str) -> str:
    """Wrap content in a Claude Code hook JSON envelope."""
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": content,
        }
    }
    return json.dumps(envelope)


def _filter_stdin() -> bool:
    """Read PostToolUse JSON from stdin, return True if path is inside repo_notes."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return False

    file_path = ""
    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path", "")

    if not file_path:
        return False

    repo_notes_dir = str(Path.home() / ".claude" / "repo_notes")
    return file_path.startswith(repo_notes_dir)


def run(args) -> int:
    try:
        # Handle --filter-stdin: exit silently if path is not inside repo_notes
        if getattr(args, "filter_stdin", False):
            if not _filter_stdin():
                return 0

        from scripts.repo_id import resolve_repo_id, get_repo_dir

        # Resolve repo ID
        explicit_id = getattr(args, "repo_id", None)
        if explicit_id:
            repo_id = explicit_id
            repo_dir = Path.home() / ".claude" / "repo_notes" / explicit_id
        else:
            try:
                repo_id = resolve_repo_id()
            except Exception:
                return 0
            repo_dir = get_repo_dir()

        if not repo_dir.is_dir():
            return 0

        content = _generate_index(repo_id, repo_dir)

        if getattr(args, "json_envelope", False):
            print(_wrap_json_envelope(content))
        else:
            print(content)

        return 0
    except Exception:
        # Silent failure — hooks should not break sessions
        return 0
