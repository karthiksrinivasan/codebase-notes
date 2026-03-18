"""CLI dispatcher for codebase-notes scripts."""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="scripts",
        description="CLI tools for codebase-notes skill",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # repo-id
    subparsers.add_parser("repo-id", help="Print the repo ID for the current git repo")

    # scaffold
    subparsers.add_parser("scaffold", help="Create notes directory structure for current repo")

    # stale
    stale_parser = subparsers.add_parser("stale", help="Check all notes for staleness")
    stale_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")
    stale_parser.add_argument("--all-repos", action="store_true", help="Check all repos")
    stale_parser.add_argument("--no-cache", action="store_true", help="Skip staleness cache")
    stale_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # nav
    nav_parser = subparsers.add_parser("nav", help="Rebuild all navigation links")
    nav_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")

    # render
    render_parser = subparsers.add_parser("render", help="Render .excalidraw to .png")
    render_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")

    # commits
    commits_parser = subparsers.add_parser("commits", help="Generate commit history notes")
    commits_parser.add_argument("--author", required=True, help="Author name or email")
    commits_parser.add_argument("--since", default="4w", help="Time range (default: 4w)")
    commits_parser.add_argument("--path", default="", help="Path filter")
    commits_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")

    # auto-update
    auto_parser = subparsers.add_parser("auto-update", help="Run staleness check + Claude update")
    auto_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")
    auto_parser.add_argument("--all-repos", action="store_true", help="Update all repos")

    # cron
    cron_parser = subparsers.add_parser("cron", help="Manage cron auto-updates")
    cron_group = cron_parser.add_mutually_exclusive_group(required=True)
    cron_group.add_argument("--install", action="store_true", help="Install cron entry")
    cron_group.add_argument("--uninstall", action="store_true", help="Remove cron entry")
    cron_parser.add_argument("--interval", default="6h", help="Cron interval (default: 6h)")

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Migrate v1 notes to v2")
    migrate_parser.add_argument("--from", dest="from_path", required=True, help="Source notes path")
    migrate_parser.add_argument("--repo-id", help="Repo ID (auto-detected if omitted)")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Display notes statistics")
    stats_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # Dispatch to subcommand modules.
    # Each module must expose a run(args) -> int entry point.
    # Modules are imported lazily so missing ones fail gracefully.
    dispatch = {
        "repo-id": "scripts.repo_id",
        "scaffold": "scripts.scaffold",
        "stale": "scripts.staleness",
        "nav": "scripts.nav_links",
        "render": "scripts.render",
        "commits": "scripts.commits",
        "auto-update": "scripts.cron",
        "cron": "scripts.cron",
        "migrate": "scripts.migrate",
        "stats": "scripts.stats",
    }

    module_name = dispatch.get(args.command)
    if module_name is None:
        print(f"{args.command}: unknown command", file=sys.stderr)
        return 1

    try:
        import importlib
        mod = importlib.import_module(module_name)
        # cron module has two entry points
        if args.command == "cron":
            return mod.run_cron(args)
        elif args.command == "auto-update":
            return mod.run_auto_update(args)
        else:
            return mod.run(args)
    except ImportError:
        print(f"{args.command}: not yet implemented", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
