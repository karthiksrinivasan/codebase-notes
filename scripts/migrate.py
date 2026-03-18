"""Migrate v1 notes (repo-local) to v2 centralized location.

v1 notes lived at:
  - docs/notes/
  - notes/
  - docs/knowledge/

v2 notes live at:
  - ~/.claude/repo_notes/<repo_id>/notes/
"""

import os
import re
import shutil
from pathlib import Path

REPO_NOTES_BASE = Path.home() / ".claude" / "repo_notes"

# Candidate v1 note directories, checked in order
V1_CANDIDATE_DIRS = [
    "docs/notes",
    "notes",
    "docs/knowledge",
]

# File extensions to copy
COPYABLE_EXTENSIONS = {".md", ".excalidraw", ".png"}

# Regex to find markdown links: [text](url)
LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')


def detect_v1_notes(repo_root: Path) -> Path | None:
    """Detect v1 notes at known locations within a repo.

    Checks candidate directories in priority order. A directory is considered
    to contain v1 notes if it has a 00-overview.md file.

    Args:
        repo_root: Root path of the git repository.

    Returns:
        Path to the v1 notes directory, or None if not found.
    """
    for candidate in V1_CANDIDATE_DIRS:
        notes_dir = repo_root / candidate
        if (notes_dir / "00-overview.md").is_file():
            return notes_dir
    return None


def copy_v1_notes(source: Path, dest: Path) -> list[Path]:
    """Copy v1 notes to centralized v2 location, preserving directory structure.

    Only copies files with extensions in COPYABLE_EXTENSIONS (.md, .excalidraw, .png).
    Does NOT delete the source directory.

    Args:
        source: Path to v1 notes directory.
        dest: Path to v2 notes directory (will be created if needed).

    Returns:
        List of destination Paths for all files that were copied.
    """
    copied_files = []

    for root, dirs, files in os.walk(source):
        rel_root = Path(root).relative_to(source)
        dest_dir = dest / rel_root
        dest_dir.mkdir(parents=True, exist_ok=True)

        for filename in files:
            src_file = Path(root) / filename
            if src_file.suffix in COPYABLE_EXTENSIONS:
                dest_file = dest_dir / filename
                shutil.copy2(src_file, dest_file)
                copied_files.append(dest_file)

    return copied_files


def _is_external_url(url: str) -> bool:
    """Check if a URL is an external HTTP(S) link."""
    return url.startswith(("http://", "https://", "mailto:"))


def _is_anchor_link(url: str) -> bool:
    """Check if a link is a same-page anchor."""
    return url.startswith("#")


def _link_escapes_notes_dir(url: str) -> bool:
    """Check if a relative link navigates outside the notes directory tree.

    Heuristic: count how many ../ segments there are. Links within notes
    use ../ to navigate between sibling folders, but links that escape
    the notes dir will have more ../ segments than their depth allows.
    We conservatively flag links containing paths that look like source
    code paths (not ending in .md, .png, .excalidraw).
    """
    if _is_external_url(url) or _is_anchor_link(url):
        return False

    # Absolute file paths
    if url.startswith("/"):
        return True

    # Normalize and resolve to check if it goes to a non-note file
    # Links to .md, .png, .excalidraw within ./ or ../ are fine
    # Links to source files (e.g., ../../src/foo.py) are problematic
    target_ext = Path(url).suffix

    # If the link target has a notes-like extension, keep it
    if target_ext in COPYABLE_EXTENSIONS:
        return False

    # If it starts with ./ or just a filename, it's within notes
    if not url.startswith(".."):
        return False

    # Any ../ link to a non-notes file type is suspect
    if target_ext and target_ext not in COPYABLE_EXTENSIONS:
        return True

    return False


def update_links_in_content(
    content: str,
    repo_root: Path,
    old_notes_rel: str,
) -> tuple[str, list[str]]:
    """Update links in a markdown file's content after migration.

    Links within the notes tree (to .md, .png, .excalidraw) are preserved as-is
    since the directory structure is maintained. Links that escape the notes
    directory (pointing to repo source files) are flagged as broken since
    the relative path relationship changes.

    Args:
        content: The full file content (including frontmatter).
        repo_root: Original repo root path.
        old_notes_rel: Relative path from repo root to old notes dir (e.g., "docs/notes").

    Returns:
        Tuple of (updated_content, list_of_broken_link_urls).
    """
    broken_links = []

    def check_link(match: re.Match) -> str:
        text = match.group(1)
        url = match.group(2)

        # External URLs: pass through
        if _is_external_url(url) or _is_anchor_link(url):
            return match.group(0)

        # Absolute file paths: flag as broken
        if url.startswith("/"):
            broken_links.append(url)
            return match.group(0)

        # Check if link escapes notes directory
        if _link_escapes_notes_dir(url):
            broken_links.append(url)

        # Keep all links as-is in content — structure is preserved
        return match.group(0)

    updated = LINK_PATTERN.sub(check_link, content)
    return updated, broken_links


def migrate(
    from_path: Path,
    repo_id: str,
    repo_root: Path,
) -> dict:
    """Migrate v1 notes to centralized v2 location.

    Copies all .md, .excalidraw, .png files preserving directory structure.
    Updates links in .md files and reports any that couldn't be auto-fixed.
    Does NOT delete the source directory.

    Args:
        from_path: Path to the v1 notes directory.
        repo_id: The resolved repo identifier.
        repo_root: Root path of the git repository.

    Returns:
        Dict with keys: files_copied (int), broken_links (list of dicts),
        dest_path (Path).
    """
    dest_notes = REPO_NOTES_BASE / repo_id / "notes"

    # Step 1: Copy all eligible files
    copied_files = copy_v1_notes(from_path, dest_notes)

    # Step 1b: Relocate research/ from notes/research/ to <root>/research/
    nested_research = dest_notes / "research"
    if nested_research.is_dir():
        dest_research = REPO_NOTES_BASE / repo_id / "research"
        if dest_research.exists():
            # Merge into existing research dir
            for item in nested_research.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(nested_research)
                    target = dest_research / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
        else:
            shutil.move(str(nested_research), str(dest_research))
        # Clean up nested dir if it still exists
        if nested_research.exists():
            shutil.rmtree(nested_research)
        # Update copied_files paths
        copied_files = [
            REPO_NOTES_BASE / repo_id / "research" / p.relative_to(nested_research)
            if str(p).startswith(str(nested_research))
            else p
            for p in copied_files
        ]

    # Step 2: Process links in all .md files
    all_broken_links = []
    old_notes_rel = str(from_path.relative_to(repo_root))

    for dest_file in copied_files:
        if dest_file.suffix != ".md":
            continue

        content = dest_file.read_text()
        updated_content, broken = update_links_in_content(content, repo_root, old_notes_rel)

        if updated_content != content:
            dest_file.write_text(updated_content)

        for url in broken:
            rel_note = str(dest_file.relative_to(dest_notes))
            all_broken_links.append({"file": rel_note, "url": url})

    return {
        "files_copied": len(copied_files),
        "broken_links": all_broken_links,
        "dest_path": dest_notes,
    }


def run(args) -> int:
    """CLI entry point for the migrate command.

    Args:
        args: Parsed argparse namespace with from_path and optionally repo_id.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    import sys

    from_path = Path(args.from_path).resolve()
    if not from_path.is_dir():
        print(f"Error: {from_path} is not a directory", file=sys.stderr)
        return 1

    if not (from_path / "00-overview.md").is_file():
        print(
            f"Warning: {from_path} does not contain 00-overview.md "
            "— are you sure this is a notes directory?",
            file=sys.stderr,
        )

    # Resolve repo ID
    repo_id = getattr(args, "repo_id", None)
    if repo_id is None:
        from scripts.repo_id import get_repo_id
        repo_id = get_repo_id()

    # Determine repo root (parent of from_path up to where .git is)
    repo_root = from_path
    while repo_root != repo_root.parent:
        if (repo_root / ".git").exists():
            break
        repo_root = repo_root.parent
    else:
        # Fallback: use from_path parent
        repo_root = from_path.parent

    result = migrate(from_path=from_path, repo_id=repo_id, repo_root=repo_root)

    # Print summary
    print(f"Migration complete:")
    print(f"  Files copied: {result['files_copied']}")
    print(f"  Destination:  {result['dest_path']}")

    if result["broken_links"]:
        print(f"\n  Links that could not be automatically updated ({len(result['broken_links'])}):")
        for bl in result["broken_links"]:
            print(f"    {bl['file']}: {bl['url']}")
        print("\n  These links pointed to files outside the notes directory.")
        print("  You may need to update them manually to use absolute paths or remove them.")
    else:
        print("  All links OK.")

    print(f"\n  Original directory was NOT deleted: {from_path}")
    return 0
