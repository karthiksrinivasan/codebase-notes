"""Tests for CLI dispatcher."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


def _run_scripts(*args):
    """Run the scripts CLI via uv from the project root."""
    return subprocess.run(
        ["uv", "run", "python", "-m", "scripts", *args],
        capture_output=True, text=True,
        cwd=PROJECT_ROOT,
    )


def test_help_shows_all_commands():
    result = _run_scripts("--help")
    assert result.returncode == 0
    for cmd in ["repo-id", "scaffold", "stale", "nav", "render", "commits", "auto-update", "cron", "migrate", "stats",
                "review-forge", "review-stack", "review-loop-state"]:
        assert cmd in result.stdout, f"Missing subcommand: {cmd}"


def test_no_command_prints_help():
    result = _run_scripts()
    assert result.returncode == 1
