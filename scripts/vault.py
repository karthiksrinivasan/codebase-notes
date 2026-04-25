"""Vault resolution and management for Obsidian-based codebase notes."""

import json
import sys
from pathlib import Path
from typing import Optional

from scripts.repo_id import resolve_repo_id

VAULTS_BASE = Path.home() / "vaults"


def repo_id_to_slug(repo_id: str) -> str:
    return repo_id.replace("--", "-")


def get_vault_dir(repo_id: str) -> Path:
    return VAULTS_BASE / repo_id_to_slug(repo_id)


def resolve_vault(
    repo_id: str,
    vaults_base: Optional[Path] = None,
) -> Optional[Path]:
    base = vaults_base or VAULTS_BASE
    slug = repo_id_to_slug(repo_id)
    vault_dir = base / slug
    config_file = vault_dir / ".vault-config.json"
    if config_file.is_file():
        return vault_dir
    return None


def read_vault_config(vault_dir: Path) -> Optional[dict]:
    config_file = vault_dir / ".vault-config.json"
    if not config_file.is_file():
        return None
    try:
        return json.loads(config_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_vault_config(vault_dir: Path, config: dict) -> None:
    config_file = vault_dir / ".vault-config.json"
    config_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def set_active_vault(vault_path: Path) -> None:
    active_file = VAULTS_BASE / ".active-vault"
    VAULTS_BASE.mkdir(parents=True, exist_ok=True)
    active_file.write_text(str(vault_path) + "\n")


def list_vaults(vaults_base: Optional[Path] = None) -> list[dict]:
    base = vaults_base or VAULTS_BASE
    if not base.is_dir():
        return []

    results = []
    for item in sorted(base.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        config = read_vault_config(item)
        if config is not None:
            results.append(config)
    return results


def run_resolve_vault(args) -> int:
    try:
        repo_id = resolve_repo_id()
        vault_dir = resolve_vault(repo_id)
        if vault_dir is None:
            print(f"No vault found for {repo_id} (expected at {get_vault_dir(repo_id)})")
            return 1
        print(str(vault_dir))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_list_vaults(args) -> int:
    try:
        vaults = list_vaults()
        if not vaults:
            print("No vaults found in ~/vaults/")
            return 0
        for v in vaults:
            slug = v.get("repo_slug", "unknown")
            repo_id = v.get("repo_id", "unknown")
            print(f"  {slug}  ({repo_id})")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
