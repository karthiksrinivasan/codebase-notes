"""Migrate v1 notes (repo-local) to v2 centralized location.

v1 notes lived at:
  - docs/notes/
  - notes/
  - docs/knowledge/

v2 notes live at:
  - ~/.claude/repo_notes/<repo_id>/notes/
"""

import json
import os
import re
import shutil
from pathlib import Path

from scripts.vault import repo_id_to_slug, VAULTS_BASE

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

# v2→v3 migration regexes
NN_PREFIX_RE = re.compile(r"^\d{2}-(.+)$")
NAV_BAR_RE = re.compile(r"^>\s*\*\*(navigation|sub-topics):\*\*.*$", re.IGNORECASE)
MD_LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")


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


# ---------------------------------------------------------------------------
# v2 → v3 migration (repo_notes → Obsidian vault)
# ---------------------------------------------------------------------------


def strip_nn_prefix(name: str) -> str:
    """Strip NN- prefix from a file or directory name.

    Examples:
        "01-auth" → "auth"
        "12-api-endpoints" → "api-endpoints"
        "index" → "index"  (no match, returned unchanged)
    """
    m = NN_PREFIX_RE.match(name)
    return m.group(1) if m else name


def build_rename_map(source_dir: Path) -> dict[str, str]:
    """Walk source_dir recursively and build old_name→new_name for prefixed entries.

    Only entries whose name changes after stripping the NN- prefix are included.
    """
    rename_map: dict[str, str] = {}
    for root, dirs, files in os.walk(source_dir):
        for name in files:
            stem = Path(name).stem
            suffix = Path(name).suffix
            new_name = strip_nn_prefix(stem) + suffix
            if new_name != name:
                rename_map[name] = new_name
        for name in dirs:
            new_name = strip_nn_prefix(name)
            if new_name != name:
                rename_map[name] = new_name
    return rename_map


def convert_relative_link_to_wikilink(
    label: str,
    url: str,
    rename_map: dict[str, str],
) -> str | None:
    """Convert a markdown relative link to an Obsidian wikilink.

    Returns None for external URLs and anchor links (caller keeps original).
    For .png files → ``![[stem.png]]`` (Excalidraw plugin auto-exports PNGs).
    For .md files → ``[[target|label]]`` or ``[[target]]`` if label matches stem.
    Strips NN- prefixes from all path components.
    """
    if _is_external_url(url) or _is_anchor_link(url):
        return None

    p = Path(url)
    suffix = p.suffix.lower()

    if suffix == ".png":
        stem = strip_nn_prefix(p.stem)
        return f"![[{stem}.png]]"

    # Build path components, stripping NN- prefixes and skipping . / ..
    parts = list(p.parts)
    clean_parts: list[str] = []
    for part in parts[:-1]:  # directories
        if part in (".", ".."):
            continue
        clean_parts.append(strip_nn_prefix(part))

    # Handle the filename
    filename = parts[-1]
    # Check rename_map for the original filename
    if filename in rename_map:
        filename = rename_map[filename]
    stem = Path(filename).stem
    file_suffix = Path(filename).suffix

    # Strip NN-prefix from stem
    clean_stem = strip_nn_prefix(stem)

    if file_suffix == ".md":
        # Build target without .md extension
        target_parts = clean_parts + [clean_stem]
        target = "/".join(target_parts)

        if label == clean_stem:
            return f"[[{target}]]"
        return f"[[{target}|{label}]]"

    # Other file types: build full target with extension
    target_parts = clean_parts + [clean_stem + file_suffix]
    target = "/".join(target_parts)
    return f"[[{target}|{label}]]"


def strip_nav_bars(content: str) -> str:
    """Remove lines matching navigation/sub-topics bar pattern."""
    lines = content.splitlines(keepends=True)
    result = []
    for line in lines:
        if not NAV_BAR_RE.match(line.rstrip("\n").rstrip("\r")):
            result.append(line)
    return "".join(result)


def convert_links_in_content(content: str, rename_map: dict[str, str]) -> str:
    """Convert all markdown links in content to Obsidian wikilinks.

    External URLs and anchor links are preserved as-is.
    """
    def _replace(match: re.Match) -> str:
        bang = match.group(1)  # "!" for images, "" for regular links
        label = match.group(2)
        url = match.group(3)

        result = convert_relative_link_to_wikilink(label, url, rename_map)
        if result is None:
            # Keep original markdown link
            return match.group(0)
        return result

    return MD_LINK_RE.sub(_replace, content)


MIGRATE_DIRS = ["notes", "research", "projects", "commits", "code-reviews"]


def migrate_to_vault(
    source_dir: Path,
    repo_id: str,
    clone_path: str,
    dry_run: bool = False,
) -> dict:
    """Migrate v2 repo_notes to v3 Obsidian vault.

    Args:
        source_dir: Path to the v2 repo root (e.g., ~/.claude/repo_notes/<id>/).
                    Contains notes/, research/, projects/, commits/, code-reviews/.
        repo_id: The repository identifier.
        clone_path: Filesystem path to the git clone.
        dry_run: If True, compute and return the plan without writing.

    Returns:
        Summary dict with keys: vault_dir, files_copied, files_skipped, dry_run.
    """
    from scripts.scaffold import scaffold_vault

    slug = repo_id_to_slug(repo_id)
    vault_dir = VAULTS_BASE / slug

    files_copied = 0
    files_skipped = 0

    # Collect all source dirs that exist
    source_subdirs = []
    for dirname in MIGRATE_DIRS:
        subdir = source_dir / dirname
        if subdir.is_dir():
            source_subdirs.append((dirname, subdir))

    if dry_run:
        for dirname, subdir in source_subdirs:
            for root, _dirs, files in os.walk(subdir):
                for fname in files:
                    src = Path(root) / fname
                    if src.suffix == ".png":
                        files_skipped += 1
                    elif src.suffix in COPYABLE_EXTENSIONS:
                        files_copied += 1
        return {
            "vault_dir": vault_dir,
            "files_copied": files_copied,
            "files_skipped": files_skipped,
            "dry_run": True,
        }

    # 1. Scaffold vault
    scaffold_vault(vault_dir, repo_id, clone_path)

    # 2. Build rename map across all source dirs
    rename_map: dict[str, str] = {}
    for dirname, subdir in source_subdirs:
        rename_map.update(build_rename_map(subdir))

    # 3. Copy files from each source subdir into matching vault subdir
    overview_content = None
    for dirname, subdir in source_subdirs:
        for root, dirs, files in os.walk(subdir):
            rel_root = Path(root).relative_to(subdir)

            dest_parts = [strip_nn_prefix(part) for part in rel_root.parts]
            if dest_parts:
                dest_dir = vault_dir / dirname / Path(*dest_parts)
            else:
                dest_dir = vault_dir / dirname
            dest_dir.mkdir(parents=True, exist_ok=True)

            for fname in files:
                src_file = Path(root) / fname

                if src_file.suffix == ".png":
                    files_skipped += 1
                    continue

                if src_file.suffix not in COPYABLE_EXTENSIONS:
                    continue

                new_name = strip_nn_prefix(src_file.stem) + src_file.suffix
                dest_file = dest_dir / new_name

                if src_file.suffix == ".md":
                    content = src_file.read_text(encoding="utf-8")

                    if src_file.name == "00-overview.md":
                        overview_content = content

                    content = convert_links_in_content(content, rename_map)
                    content = strip_nav_bars(content)
                    dest_file.write_text(content, encoding="utf-8")
                else:
                    shutil.copy2(src_file, dest_file)

                files_copied += 1

    # 4. Seed wiki/hot.md from overview if available
    if overview_content is not None:
        hot_file = vault_dir / "wiki" / "hot.md"
        hot_file.parent.mkdir(parents=True, exist_ok=True)
        hot_file.write_text(
            f"---\nlast_updated: {__import__('datetime').date.today().isoformat()}\n---\n"
            f"# Hot Topics\n\n"
            f"Active threads, open questions, and things to watch.\n\n"
            f"_Seeded from overview during migration. Edit to reflect current priorities._\n",
            encoding="utf-8",
        )

    return {
        "vault_dir": vault_dir,
        "files_copied": files_copied,
        "files_skipped": files_skipped,
        "dry_run": False,
    }


def run_migrate_to_vault(args) -> int:
    """CLI entry point for v2→v3 vault migration.

    Scans ~/.claude/repo_notes/ for repos to migrate. Supports:
      --repo-id <id>   Migrate a specific repo.
      --all            Migrate all repos found in repo_notes.
      --dry-run        Show what would be done without writing.
    """
    import sys

    dry_run = getattr(args, "dry_run", False)
    repo_id_arg = getattr(args, "repo_id", None)
    migrate_all = getattr(args, "all", False)

    if not repo_id_arg and not migrate_all:
        print("Error: specify --repo-id <id> or --all", file=sys.stderr)
        return 1

    if not REPO_NOTES_BASE.is_dir():
        print(f"Error: {REPO_NOTES_BASE} does not exist", file=sys.stderr)
        return 1

    # Collect repos to migrate — pass repo root, not notes/ subdir
    repos: list[tuple[str, Path]] = []
    if repo_id_arg:
        repo_dir = REPO_NOTES_BASE / repo_id_arg
        if not repo_dir.is_dir():
            print(f"Error: {repo_dir} does not exist", file=sys.stderr)
            return 1
        repos.append((repo_id_arg, repo_dir))
    else:
        for item in sorted(REPO_NOTES_BASE.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            repos.append((item.name, item))

    if not repos:
        print("No repos found to migrate.")
        return 0

    for repo_id, repo_dir in repos:
        # Read clone_path from .repo_paths if available
        clone_path = str(repo_dir)
        repo_paths_file = repo_dir / ".repo_paths"
        if repo_paths_file.is_file():
            lines = [l.strip() for l in repo_paths_file.read_text().splitlines() if l.strip()]
            if lines:
                clone_path = lines[0]

        prefix = "[DRY RUN] " if dry_run else ""
        print(f"{prefix}Migrating {repo_id}...")
        result = migrate_to_vault(
            source_dir=repo_dir,
            repo_id=repo_id,
            clone_path=clone_path,
            dry_run=dry_run,
        )
        print(f"  Vault: {result['vault_dir']}")
        print(f"  Files copied: {result['files_copied']}")
        print(f"  Files skipped (PNG): {result['files_skipped']}")

    return 0
