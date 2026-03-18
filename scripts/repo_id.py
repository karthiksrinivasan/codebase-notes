"""Resolve the repo ID from git remote URL or local path fallback."""

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path


def _sanitize_dirname(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def _parse_remote_url(url: str) -> str:
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    url = url.rstrip("/")

    # SSH with protocol: ssh://git@host:port/org/repo
    m = re.match(r"ssh://[^@]+@[^:/]+(?::\d+)?/(.+)", url)
    if m:
        return m.group(1).replace("/", "--")

    # SSH shorthand: git@host:org/repo
    m = re.match(r"[^@]+@[^:]+:(.+)", url)
    if m:
        return m.group(1).replace("/", "--")

    # HTTPS: https://host/org/repo
    m = re.match(r"https?://[^/]+/(.+)", url)
    if m:
        return m.group(1).replace("/", "--")

    raise ValueError(f"Cannot parse git remote URL: {url}")


def resolve_repo_id(cwd: str | None = None) -> str:
    if cwd is None:
        cwd = os.getcwd()
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True, cwd=cwd,
        )
        return _parse_remote_url(result.stdout.strip())
    except subprocess.CalledProcessError:
        dirname = _sanitize_dirname(os.path.basename(cwd))
        path_hash = hashlib.sha256(cwd.encode()).hexdigest()[:8]
        return f"local--{dirname}--{path_hash}"


def get_repo_id(cwd: str | None = None) -> str:
    """Alias for resolve_repo_id — used by other modules."""
    return resolve_repo_id(cwd=cwd)


def get_notes_dir(cwd: str | None = None) -> Path:
    """Return the centralized notes directory for the repo at cwd."""
    repo_id = resolve_repo_id(cwd=cwd)
    return Path.home() / ".claude" / "repo_notes" / repo_id / "notes"


def get_repo_dir(cwd: str | None = None) -> Path:
    """Return the centralized repo directory for the repo at cwd."""
    repo_id = resolve_repo_id(cwd=cwd)
    return Path.home() / ".claude" / "repo_notes" / repo_id


def run(args) -> int:
    try:
        print(resolve_repo_id())
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
