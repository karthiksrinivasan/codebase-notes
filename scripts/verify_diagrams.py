"""Verify diagram coverage across all notes, research, commits, and projects.

Scans markdown files for sections that describe relationships or flows
and checks whether corresponding diagrams exist. Outputs a report of
notes and sections that are missing diagrams.
"""

import re
import sys
from pathlib import Path
from typing import Optional

from scripts.repo_id import get_repo_dir


# Sections that typically need diagrams
DIAGRAM_TRIGGER_HEADINGS = [
    "architecture",
    "overview",
    "data flow",
    "dataflow",
    "integration",
    "workflow",
    "process",
    "pipeline",
    "lifecycle",
    "state machine",
    "sequence",
    "topology",
    "deployment",
    "infrastructure",
    "system design",
    "technical approach",
    "how it works",
    "request flow",
    "event flow",
    "message flow",
]

# Relationship patterns in prose that suggest a diagram would help.
# These are checked against section content only (not tables or code blocks).
RELATIONSHIP_PATTERNS = [
    r"\b\w+\s+(?:connects?|sends?|receives?|calls?|triggers?|forwards?)\s+(?:to|from)\s+\w+",
    r"(?:layer|tier|stage|step|phase)\s+\d",
    r"(?:upstream|downstream)\s+(?:of|from|to)",
]


def _has_image_reference(text: str) -> bool:
    """Check if a text block contains a markdown image reference."""
    return bool(re.search(r"!\[.*?\]\(.*?\.png\)", text))


def _has_excalidraw_nearby(note_path: Path) -> list[str]:
    """Return list of .excalidraw files in the same directory as the note."""
    parent = note_path.parent
    return [f.name for f in parent.glob("*.excalidraw")]


def _extract_sections(text: str) -> list[dict]:
    """Extract markdown sections with their heading level, title, and content."""
    sections = []
    # Split on headings (## or ###)
    parts = re.split(r"^(#{2,3})\s+(.+)$", text, flags=re.MULTILINE)

    # parts[0] is content before first heading
    i = 1
    while i < len(parts):
        level = len(parts[i])  # number of #
        title = parts[i + 1].strip()
        content = parts[i + 2] if i + 2 < len(parts) else ""
        sections.append({
            "level": level,
            "title": title,
            "content": content,
        })
        i += 3

    return sections


def _strip_tables_and_code(text: str) -> str:
    """Remove markdown tables and code blocks to avoid false positives."""
    # Remove fenced code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Remove inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Remove table rows (lines starting with |)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)
    return text


def _section_needs_diagram(title: str, content: str) -> Optional[str]:
    """Check if a section likely needs a diagram. Returns reason or None."""
    title_lower = title.lower()

    # Check if heading matches known diagram-worthy patterns
    for trigger in DIAGRAM_TRIGGER_HEADINGS:
        if trigger in title_lower:
            return f"section heading '{title}' describes {trigger}"

    # Check prose content (not tables/code) for relationship patterns
    prose = _strip_tables_and_code(content)
    for pattern in RELATIONSHIP_PATTERNS:
        match = re.search(pattern, prose, re.IGNORECASE)
        if match:
            return f"content describes relationships: '{match.group(0).strip()[:60]}'"

    return None


def check_note(note_path: Path) -> list[dict]:
    """Check a single note for missing diagrams. Returns list of issues."""
    issues = []
    try:
        text = note_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues

    # Skip very short files (frontmatter-only, stubs)
    if len(text.strip()) < 100:
        return issues

    # Check if the note has ANY diagram at all
    has_any_image = _has_image_reference(text)
    excalidraw_files = _has_excalidraw_nearby(note_path)

    if not has_any_image and not excalidraw_files:
        issues.append({
            "note": str(note_path),
            "section": "(entire note)",
            "reason": "no diagrams found — every note should have at least one",
            "severity": "high",
        })

    # Check individual sections for missing diagrams
    sections = _extract_sections(text)
    for section in sections:
        reason = _section_needs_diagram(section["title"], section["content"])
        if reason and not _has_image_reference(section["content"]):
            issues.append({
                "note": str(note_path),
                "section": section["title"],
                "reason": reason,
                "severity": "medium" if has_any_image else "high",
            })

    return issues


def scan_directory(directory: Path) -> list[dict]:
    """Scan all markdown files in a directory tree for missing diagrams."""
    all_issues = []
    if not directory.exists():
        return all_issues

    for md_file in sorted(directory.rglob("*.md")):
        # Skip RULES.md and other meta files
        if md_file.name in ("RULES.md",):
            continue
        issues = check_note(md_file)
        all_issues.extend(issues)

    return all_issues


def format_report(issues: list[dict], repo_dir: Path) -> str:
    """Format issues into a readable report."""
    if not issues:
        return "All notes have adequate diagram coverage."

    lines = []
    lines.append(f"Found {len(issues)} diagram coverage issue(s):\n")

    high = [i for i in issues if i["severity"] == "high"]
    medium = [i for i in issues if i["severity"] == "medium"]

    if high:
        lines.append(f"### HIGH priority ({len(high)} issues) — notes with NO diagrams\n")
        for issue in high:
            rel_path = _relative_to(issue["note"], repo_dir)
            lines.append(f"  - **{rel_path}** [{issue['section']}]")
            lines.append(f"    Reason: {issue['reason']}")
        lines.append("")

    if medium:
        lines.append(f"### MEDIUM priority ({len(medium)} issues) — sections missing diagrams\n")
        for issue in medium:
            rel_path = _relative_to(issue["note"], repo_dir)
            lines.append(f"  - **{rel_path}** [{issue['section']}]")
            lines.append(f"    Reason: {issue['reason']}")
        lines.append("")

    lines.append("Run `/codebase-notes:diagram --all-missing` to create missing diagrams.")
    return "\n".join(lines)


def _relative_to(path_str: str, base: Path) -> str:
    """Make path relative to base for cleaner display."""
    try:
        return str(Path(path_str).relative_to(base))
    except ValueError:
        return path_str


def run(args) -> int:
    """Main entry point for the verify-diagrams command."""
    try:
        repo_dir = get_repo_dir()
    except Exception as e:
        print(f"Error resolving repo: {e}", file=sys.stderr)
        return 1

    notes_dir = repo_dir / "notes"
    research_dir = repo_dir / "notes" / "research"
    commits_dir = repo_dir / "commits"
    projects_dir = repo_dir / "projects"

    all_issues = []

    # Scan each area
    for label, directory in [
        ("notes", notes_dir),
        ("research", research_dir),
        ("commits", commits_dir),
        ("projects", projects_dir),
    ]:
        if directory.exists():
            issues = scan_directory(directory)
            all_issues.extend(issues)

    # Deduplicate: research is inside notes, so skip duplicates
    seen = set()
    deduped = []
    for issue in all_issues:
        key = (issue["note"], issue["section"])
        if key not in seen:
            seen.add(key)
            deduped.append(issue)

    report = format_report(deduped, repo_dir)
    print(report)

    if hasattr(args, "json") and args.json:
        import json
        print(json.dumps(deduped, indent=2))

    # Return non-zero if there are high-priority issues
    high_count = sum(1 for i in deduped if i["severity"] == "high")
    return 1 if high_count > 0 else 0
