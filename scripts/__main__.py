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

    # verify-diagrams
    verify_parser = subparsers.add_parser("verify-diagrams", help="Check notes for missing diagrams")
    verify_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # resolve-vault
    subparsers.add_parser("resolve-vault", help="Print the vault path for the current repo")

    # list-vaults
    subparsers.add_parser("list-vaults", help="List all Obsidian vaults")

    # migrate-to-vault
    mtv_parser = subparsers.add_parser("migrate-to-vault", help="Migrate repo_notes to Obsidian vault")
    mtv_parser.add_argument("--repo-id", help="Specific repo ID to migrate")
    mtv_parser.add_argument("--all", action="store_true", help="Migrate all repos")
    mtv_parser.add_argument("--dry-run", action="store_true", help="Preview only")

    # review-forge
    forge_parser = subparsers.add_parser("review-forge", help="Detect git forge from remote URL")
    forge_parser.add_argument("--remote", default="origin", help="Git remote name (default: origin)")

    # review-preflight
    preflight_parser = subparsers.add_parser("review-preflight", help="Check preconditions for a code review")
    preflight_parser.add_argument("--review-dir", required=True, help="Path to the review directory")
    preflight_parser.add_argument("--check-fix", action="store_true", help="Run fix-specific checks")

    # review-delta
    delta_parser = subparsers.add_parser("review-delta", help="Compute diff statistics between revisions")
    delta_parser.add_argument("--old-head", required=True, help="Old HEAD SHA")
    delta_parser.add_argument("--new-head", required=True, help="New HEAD SHA")
    delta_parser.add_argument("--merge-base", required=True, help="Current merge base SHA")
    delta_parser.add_argument("--old-merge-base", help="Previous merge base SHA (for drift detection)")

    # review-status
    status_parser = subparsers.add_parser("review-status", help="Manage review finding statuses")
    status_parser.add_argument("--review-path", required=True, help="Path to review.md")
    status_parser.add_argument("--action", required=True,
                               choices=["assign-ids", "validate-transition",
                                        "regenerate-fixlog", "regenerate-history-row",
                                        "list-findings"],
                               help="Action to perform")
    status_parser.add_argument("--from", dest="from_status", help="Source status (for validate-transition)")
    status_parser.add_argument("--to", dest="to_status", help="Target status (for validate-transition)")
    status_parser.add_argument("--version", type=int, help="Version number (for regenerate-history-row)")
    status_parser.add_argument("--trigger", help="Trigger text (for regenerate-history-row)")
    status_parser.add_argument("--head-sha", help="HEAD SHA (for regenerate-history-row)")

    # review-frontmatter
    fm_parser = subparsers.add_parser("review-frontmatter", help="Read or update markdown frontmatter")
    fm_parser.add_argument("--path", required=True, help="Path to .md file")
    fm_parser.add_argument("--action", required=True, choices=["read", "update"], help="Action to perform")
    fm_parser.add_argument("--set", action="append", help="KEY=VALUE pair (repeatable, for update)")

    # review-stack
    stack_parser = subparsers.add_parser("review-stack", help="Discover stacked branch chain from base")
    stack_parser.add_argument("--base", required=True, help="Base branch of the stack")

    # review-assess
    assess_parser = subparsers.add_parser("review-assess", help="Assess findings against deferred registry")
    assess_parser.add_argument("--review-path", required=True, help="Path to review.md")
    assess_parser.add_argument("--registry-path", help="Path to deferred-registry.json (default: sibling of review.md)")

    # review-deferred
    deferred_parser = subparsers.add_parser("review-deferred", help="Manage deferred finding registry")
    deferred_parser.add_argument("--registry-path", required=True, help="Path to deferred-registry.json")
    deferred_parser.add_argument("--action", required=True,
                                  choices=["add-deferred", "add-fix", "read", "auto-populate"],
                                  help="Action to perform")
    deferred_parser.add_argument("--entry", help="JSON entry (for add-deferred, add-fix)")
    deferred_parser.add_argument("--review-path", help="Path to review.md (for auto-populate)")
    deferred_parser.add_argument("--cycle", type=int, help="Cycle number (for auto-populate)")

    # review-loop-state
    loop_state_parser = subparsers.add_parser("review-loop-state", help="Manage loop state file")
    loop_state_parser.add_argument("--review-dir", required=True, help="Code reviews directory path")
    loop_state_parser.add_argument("--action", required=True, choices=["read", "write", "update-branch"],
                                   help="Action to perform")
    loop_state_parser.add_argument("--branches", help="JSON branch list (for write action)")
    loop_state_parser.add_argument("--loop-args", help="JSON loop arguments (for write action)")
    loop_state_parser.add_argument("--branch", help="Branch name (for update-branch action)")
    loop_state_parser.add_argument("--status", help="Branch status (for update-branch action)")
    loop_state_parser.add_argument("--cycles", type=int, help="Cycle count (for update-branch action)")

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
        "commits": "scripts.commits",
        "auto-update": "scripts.cron",
        "cron": "scripts.cron",
        "migrate": "scripts.migrate",
        "stats": "scripts.stats",
        "verify-diagrams": "scripts.verify_diagrams",
        "resolve-vault": "scripts.vault",
        "list-vaults": "scripts.vault",
        "migrate-to-vault": "scripts.migrate",
        "review-forge": "scripts.code_review",
        "review-assess": "scripts.code_review",
        "review-deferred": "scripts.code_review",
        "review-stack": "scripts.code_review",
        "review-loop-state": "scripts.code_review",
        "review-preflight": "scripts.code_review",
        "review-delta": "scripts.code_review",
        "review-status": "scripts.code_review",
        "review-frontmatter": "scripts.code_review",
    }

    module_name = dispatch.get(args.command)
    if module_name is None:
        print(f"{args.command}: unknown command", file=sys.stderr)
        return 1

    try:
        import importlib
        mod = importlib.import_module(module_name)
        # Modules with multiple entry points
        if args.command == "cron":
            return mod.run_cron(args)
        elif args.command == "auto-update":
            return mod.run_auto_update(args)
        elif args.command == "review-assess":
            return mod.run_assess(args)
        elif args.command == "review-deferred":
            return mod.run_deferred(args)
        elif args.command == "review-forge":
            return mod.run_forge(args)
        elif args.command == "review-stack":
            return mod.run_stack(args)
        elif args.command == "review-loop-state":
            return mod.run_loop_state(args)
        elif args.command == "review-preflight":
            return mod.run_preflight(args)
        elif args.command == "review-delta":
            return mod.run_delta(args)
        elif args.command == "review-status":
            return mod.run_status(args)
        elif args.command == "review-frontmatter":
            return mod.run_frontmatter(args)
        elif args.command == "resolve-vault":
            return mod.run_resolve_vault(args)
        elif args.command == "list-vaults":
            return mod.run_list_vaults(args)
        elif args.command == "migrate-to-vault":
            return mod.run_migrate_to_vault(args)
        else:
            return mod.run(args)
    except ImportError:
        print(f"{args.command}: not yet implemented", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
