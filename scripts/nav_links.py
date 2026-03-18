"""Deterministic navigation link rebuilding for codebase notes.

Walks the notes directory tree, computes correct Up/Prev/Next/Sub-topics
links for each .md file based on its position, and inserts or replaces
navigation lines. Idempotent — running twice produces the same result.
"""

import re
import sys
from pathlib import Path
from typing import Optional

# Patterns match lines starting with > **Navigation:** or > **Sub-topics:**
NAV_PATTERN = re.compile(
    r"^>\s*\*\*navigation:\*\*",
    re.IGNORECASE,
)
SUBTOPICS_PATTERN = re.compile(
    r"^>\s*\*\*sub-topics:\*\*",
    re.IGNORECASE,
)

EXCLUDED_FILES = {"RULES.md", "rules.md"}


def build_notes_tree(notes_dir: Path) -> list[dict]:
    """Build a sorted list of note entries at the top level of a directory."""
    return _build_level(notes_dir)


def _build_level(directory: Path) -> list[dict]:
    """Recursively build the tree for a single directory level."""
    entries: list[dict] = []

    if not directory.is_dir():
        return entries

    items = sorted(directory.iterdir())

    for item in items:
        if item.name in EXCLUDED_FILES:
            continue

        if item.is_file() and item.suffix == ".md":
            if item.name == "index.md":
                continue
            entries.append({
                "path": item,
                "children": [],
                "is_index": False,
            })

        elif item.is_dir():
            index_file = item / "index.md"
            if index_file.is_file():
                children = _build_level(item)
                entries.append({
                    "path": index_file,
                    "children": children,
                    "is_index": True,
                })
            else:
                for child_md in sorted(item.glob("*.md")):
                    if child_md.name not in EXCLUDED_FILES:
                        entries.append({
                            "path": child_md,
                            "children": [],
                            "is_index": False,
                        })

    return entries


def compute_nav_links(note_path: Path, notes_dir: Path) -> dict:
    """Compute navigation links for a given note file."""
    parent_dir = note_path.parent
    is_index = note_path.name == "index.md"

    if is_index:
        sibling_dir = parent_dir.parent
    else:
        sibling_dir = parent_dir

    siblings = _build_level(sibling_dir)

    my_idx = None
    for i, entry in enumerate(siblings):
        if entry["path"].resolve() == note_path.resolve():
            my_idx = i
            break

    # Compute up link
    up: Optional[str] = None
    if is_index:
        grandparent = parent_dir.parent
        if grandparent == notes_dir:
            overview = notes_dir / "00-overview.md"
            if overview.is_file():
                up = _relative_link(note_path, overview)
        else:
            gp_index = grandparent / "index.md"
            if gp_index.is_file():
                up = _relative_link(note_path, gp_index)
    elif parent_dir == notes_dir:
        if note_path.name != "00-overview.md":
            overview = notes_dir / "00-overview.md"
            if overview.is_file():
                up = _relative_link(note_path, overview)
    else:
        folder_index = parent_dir / "index.md"
        if folder_index.is_file() and folder_index.resolve() != note_path.resolve():
            up = _relative_link(note_path, folder_index)

    # Compute prev/next
    prev_link: Optional[str] = None
    next_link: Optional[str] = None
    if my_idx is not None:
        if my_idx > 0:
            prev_link = _relative_link(note_path, siblings[my_idx - 1]["path"])
        if my_idx < len(siblings) - 1:
            next_link = _relative_link(note_path, siblings[my_idx + 1]["path"])

    # Compute subtopics (for index.md only)
    subtopics: list[tuple[str, str]] = []
    if is_index:
        children = _build_level(parent_dir)
        for child in children:
            label = _label_from_path(child["path"])
            rel = _relative_link(note_path, child["path"])
            subtopics.append((label, rel))

    return {
        "up": up,
        "prev": prev_link,
        "next": next_link,
        "subtopics": subtopics,
        "is_index": is_index,
    }


def _relative_link(from_file: Path, to_file: Path) -> str:
    """Compute relative path from one file to another."""
    try:
        rel = to_file.resolve().relative_to(from_file.resolve().parent)
        return "./" + str(rel)
    except ValueError:
        import os
        return os.path.relpath(to_file.resolve(), from_file.resolve().parent)


def _label_from_path(file_path: Path) -> str:
    """Generate a human-readable label from a note path."""
    if file_path.name == "index.md":
        name = file_path.parent.name
    else:
        name = file_path.stem

    stripped = re.sub(r"^\d+-", "", name)
    return stripped.replace("-", " ").title()


def format_nav_line(links: dict) -> str:
    """Format navigation links as a blockquote line."""
    parts: list[str] = []
    if links["up"]:
        parts.append(f"Up: [Parent]({links['up']})")
    if links["prev"]:
        parts.append(f"Prev: [Previous]({links['prev']})")
    if links["next"]:
        parts.append(f"Next: [Next]({links['next']})")

    if not parts:
        return ""

    return "> **Navigation:** " + " | ".join(parts)


def format_subtopics_line(subtopics: list[tuple[str, str]]) -> str:
    """Format sub-topics as a blockquote line."""
    if not subtopics:
        return ""
    parts = [f"[{label}]({path})" for label, path in subtopics]
    return "> **Sub-topics:** " + " | ".join(parts)


def _find_frontmatter_end(lines: list[str]) -> int:
    """Find the line index of the closing --- of YAML frontmatter."""
    if not lines or lines[0].strip() != "---":
        return -1

    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return i

    return -1


def insert_or_replace_nav(file_path: Path, nav_line: str, subtopics_line: str) -> bool:
    """Insert or replace navigation/sub-topics lines in a markdown file."""
    text = file_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    nav_idx: Optional[int] = None
    sub_idx: Optional[int] = None

    for i, line in enumerate(lines):
        if NAV_PATTERN.match(line):
            nav_idx = i
        elif SUBTOPICS_PATTERN.match(line):
            sub_idx = i

    new_lines = list(lines)
    modified = False

    lines_to_insert: list[str] = []
    if nav_line:
        lines_to_insert.append(nav_line)
    if subtopics_line:
        lines_to_insert.append(subtopics_line)

    if not lines_to_insert:
        indices_to_remove = sorted(
            [i for i in [nav_idx, sub_idx] if i is not None],
            reverse=True,
        )
        for idx in indices_to_remove:
            new_lines.pop(idx)
            modified = True
        if modified:
            file_path.write_text("\n".join(new_lines), encoding="utf-8")
        return modified

    if nav_idx is not None or sub_idx is not None:
        indices_to_remove = sorted(
            [i for i in [nav_idx, sub_idx] if i is not None],
            reverse=True,
        )
        insert_point = min(i for i in [nav_idx, sub_idx] if i is not None)
        for idx in indices_to_remove:
            new_lines.pop(idx)
        for j, line in enumerate(lines_to_insert):
            new_lines.insert(insert_point + j, line)
        modified = True
    else:
        fm_end = _find_frontmatter_end(lines)
        if fm_end >= 0:
            insert_point = fm_end + 1
        else:
            insert_point = 0

        if insert_point < len(new_lines) and new_lines[insert_point].strip():
            lines_to_insert.append("")

        for j, line in enumerate(lines_to_insert):
            new_lines.insert(insert_point + j, line)
        modified = True

    new_text = "\n".join(new_lines)
    if new_text == text:
        return False

    file_path.write_text(new_text, encoding="utf-8")
    return modified


def _collect_all_md_files(notes_dir: Path) -> list[Path]:
    """Collect all .md files in the notes directory, excluding RULES.md."""
    files: list[Path] = []
    for md_file in sorted(notes_dir.rglob("*.md")):
        if md_file.name in EXCLUDED_FILES:
            continue
        files.append(md_file)
    return files


def rebuild_all_nav_links(notes_dir: Path) -> list[str]:
    """Rebuild navigation links for all .md files in notes_dir."""
    modified_files: list[str] = []

    all_files = _collect_all_md_files(notes_dir)

    for md_file in all_files:
        links = compute_nav_links(md_file, notes_dir)

        nav_line = format_nav_line(links)
        subtopics_line = ""
        if links["is_index"]:
            subtopics_line = format_subtopics_line(links["subtopics"])

        was_modified = insert_or_replace_nav(md_file, nav_line, subtopics_line)
        if was_modified:
            modified_files.append(str(md_file))

    return modified_files


def run(args) -> int:
    try:
        from pathlib import Path as _Path
        from scripts.repo_id import get_notes_dir
        explicit_id = getattr(args, "repo_id", None)
        if explicit_id:
            notes_dir = _Path.home() / ".claude" / "repo_notes" / explicit_id / "notes"
        else:
            notes_dir = get_notes_dir()
        if not notes_dir.is_dir():
            print(f"Notes directory not found: {notes_dir}", file=sys.stderr)
            return 1
        modified = rebuild_all_nav_links(notes_dir)
        if modified:
            print(f"Updated {len(modified)} files:")
            for f in modified:
                print(f"  {f}")
        else:
            print("All navigation links up to date.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
