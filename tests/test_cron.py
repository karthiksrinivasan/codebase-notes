"""Tests for cron.py — lock file management, plist generation, auto-update orchestration."""

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestLockFile:
    """Test lock file acquire/release and stale lock detection."""

    def test_acquire_lock_creates_file(self, tmp_path):
        """Acquiring a lock should create .cron.lock with current PID."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        assert acquire_lock(lock_path) is True
        assert lock_path.exists()
        assert lock_path.read_text().strip() == str(os.getpid())
        release_lock(lock_path)

    def test_acquire_lock_fails_if_process_alive(self, tmp_path):
        """Should fail to acquire if lock exists and owning process is alive."""
        from scripts.cron import acquire_lock

        lock_path = tmp_path / ".cron.lock"
        # Write our own PID — we are alive
        lock_path.write_text(str(os.getpid()))

        assert acquire_lock(lock_path) is False

    def test_acquire_lock_removes_stale_lock(self, tmp_path):
        """Should remove lock and acquire if owning process is dead."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        # Write a PID that almost certainly doesn't exist
        lock_path.write_text("9999999")

        # Mock os.kill to raise OSError (process not found)
        with patch("os.kill", side_effect=OSError("No such process")):
            assert acquire_lock(lock_path) is True
            assert lock_path.read_text().strip() == str(os.getpid())

        release_lock(lock_path)

    def test_release_lock_removes_file(self, tmp_path):
        """Releasing the lock should delete the lock file."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        acquire_lock(lock_path)
        assert lock_path.exists()
        release_lock(lock_path)
        assert not lock_path.exists()

    def test_release_lock_noop_if_missing(self, tmp_path):
        """Releasing a non-existent lock should not error."""
        from scripts.cron import release_lock

        lock_path = tmp_path / ".cron.lock"
        release_lock(lock_path)  # Should not raise

    def test_acquire_lock_replaces_lock_with_non_numeric_content(self, tmp_path):
        """If lock file has garbage content, treat as stale and acquire."""
        from scripts.cron import acquire_lock, release_lock

        lock_path = tmp_path / ".cron.lock"
        lock_path.write_text("not-a-pid\n")

        assert acquire_lock(lock_path) is True
        release_lock(lock_path)


class TestPlistGeneration:
    """Test launchd plist XML generation for macOS."""

    def test_generate_plist_default_interval(self):
        """Plist should default to 6h (21600s) interval."""
        from scripts.cron import generate_plist_content

        content = generate_plist_content(interval_hours=6)
        assert "com.codebase-notes.auto-update" in content
        assert "<integer>21600</integer>" in content

    def test_generate_plist_custom_interval(self):
        """Plist should accept custom interval in hours."""
        from scripts.cron import generate_plist_content

        content = generate_plist_content(interval_hours=12)
        assert "<integer>43200</integer>" in content

    def test_generate_plist_contains_correct_command(self):
        """Plist should run: cd scripts dir && uv run python -m scripts auto-update --all-repos."""
        from scripts.cron import generate_plist_content, SCRIPTS_DIR

        content = generate_plist_content(interval_hours=6)
        assert "uv" in content
        assert "auto-update" in content
        assert "--all-repos" in content
        assert str(SCRIPTS_DIR) in content

    def test_generate_plist_has_log_paths(self):
        """Plist should set stdout/stderr log paths."""
        from scripts.cron import generate_plist_content, LOG_FILE

        content = generate_plist_content(interval_hours=6)
        assert str(LOG_FILE) in content or "cron.log" in content

    def test_generate_plist_is_valid_xml(self):
        """Plist content should be parseable XML."""
        import xml.etree.ElementTree as ET
        from scripts.cron import generate_plist_content

        content = generate_plist_content(interval_hours=6)
        # Should not raise
        ET.fromstring(content)

    def test_install_cron_creates_plist_file(self, tmp_path):
        """install_cron should write the plist file to the given path."""
        from scripts.cron import install_cron

        plist_path = tmp_path / "com.codebase-notes.auto-update.plist"
        with patch("scripts.cron.PLIST_PATH", plist_path), \
             patch("subprocess.run") as mock_run, \
             patch("platform.system", return_value="Darwin"):
            install_cron(interval_hours=6)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "com.codebase-notes.auto-update" in content

    def test_uninstall_cron_removes_plist(self, tmp_path):
        """uninstall_cron should unload and delete the plist file."""
        from scripts.cron import uninstall_cron

        plist_path = tmp_path / "com.codebase-notes.auto-update.plist"
        plist_path.write_text("<plist></plist>")

        with patch("scripts.cron.PLIST_PATH", plist_path), \
             patch("subprocess.run") as mock_run, \
             patch("platform.system", return_value="Darwin"):
            uninstall_cron()

        assert not plist_path.exists()


class TestCrontabFallback:
    """Test crontab generation for Linux systems."""

    def test_generate_crontab_entry_default(self):
        """Should generate valid crontab entry with 6h interval."""
        from scripts.cron import generate_crontab_entry

        entry = generate_crontab_entry(interval_hours=6)
        assert entry.startswith("0 */6 * * *")
        assert "auto-update --all-repos" in entry

    def test_generate_crontab_entry_custom(self):
        """Should handle custom interval."""
        from scripts.cron import generate_crontab_entry

        entry = generate_crontab_entry(interval_hours=2)
        assert "*/2" in entry

    def test_install_cron_linux_adds_entry(self):
        """On Linux, install_cron should add a tagged crontab entry."""
        from scripts.cron import install_cron, CRONTAB_MARKER

        with patch("platform.system", return_value="Linux"), \
             patch("subprocess.run") as mock_run:
            # First call: crontab -l returns empty
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="no crontab"),  # crontab -l
                MagicMock(returncode=0),  # crontab -
            ]
            result = install_cron(interval_hours=6)

        assert "crontab" in result.lower()
        # Verify crontab - was called with the marker
        written_input = mock_run.call_args_list[1].kwargs.get("input", "")
        assert CRONTAB_MARKER in written_input

    def test_uninstall_cron_linux_removes_entry(self):
        """On Linux, uninstall_cron should remove the tagged crontab line."""
        from scripts.cron import uninstall_cron, CRONTAB_MARKER

        existing = f"0 * * * * some-other-job\n0 */6 * * * cd /path && uv run ... {CRONTAB_MARKER}\n"

        with patch("platform.system", return_value="Linux"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=existing),  # crontab -l
                MagicMock(returncode=0),  # crontab -
            ]
            uninstall_cron()

        written_input = mock_run.call_args_list[1].kwargs.get("input", "")
        assert CRONTAB_MARKER not in written_input
        assert "some-other-job" in written_input


class TestAutoUpdate:
    """Test auto-update orchestration: staleness check, claude spawning, timeouts."""

    def test_build_update_prompt_includes_stale_notes(self):
        """The prompt sent to claude should list stale notes and changed files."""
        from scripts.cron import build_update_prompt

        stale_entries = [
            {
                "note": "02-models/index.md",
                "changed_files": ["src/models/user.py", "src/models/auth.py"],
                "files_changed": 2,
            }
        ]
        prompt = build_update_prompt(stale_entries, "my-org--my-repo")
        assert "02-models/index.md" in prompt
        assert "src/models/user.py" in prompt
        assert "src/models/auth.py" in prompt

    def test_build_update_prompt_limits_to_max_repos(self):
        """Prompt builder should respect the list it's given (caller limits)."""
        from scripts.cron import build_update_prompt

        stale_entries = [
            {"note": f"note-{i}/index.md", "changed_files": [f"file{i}.py"], "files_changed": i + 1}
            for i in range(3)
        ]
        prompt = build_update_prompt(stale_entries, "org--repo")
        for entry in stale_entries:
            assert entry["note"] in prompt

    def test_spawn_claude_for_repo_calls_subprocess(self, tmp_path):
        """Should invoke claude CLI with correct flags and working directory."""
        from scripts.cron import spawn_claude_for_repo

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
            result = spawn_claude_for_repo(
                prompt="Update the notes",
                working_dir=tmp_path,
                timeout=60,
            )

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "claude" in cmd[0]
        assert "-p" in cmd
        assert "--allowedTools" in cmd
        assert str(tmp_path) == call_args[1].get("cwd") or call_args.kwargs.get("cwd") == str(tmp_path)

    def test_spawn_claude_for_repo_handles_timeout(self, tmp_path):
        """Should return timeout status when claude exceeds time limit."""
        from scripts.cron import spawn_claude_for_repo

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=10)):
            result = spawn_claude_for_repo(
                prompt="Update",
                working_dir=tmp_path,
                timeout=10,
            )

        assert result["status"] == "timeout"

    def test_spawn_claude_for_repo_handles_error(self, tmp_path):
        """Should return error status when claude fails."""
        from scripts.cron import spawn_claude_for_repo

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error occurred")
            result = spawn_claude_for_repo(
                prompt="Update",
                working_dir=tmp_path,
                timeout=60,
            )

        assert result["status"] == "error"

    def test_auto_update_acquires_and_releases_lock(self, tmp_path):
        """auto_update_all_repos should acquire lock at start, release at end."""
        from scripts.cron import auto_update_all_repos

        lock_path = tmp_path / ".cron.lock"
        log_path = tmp_path / "cron.log"

        with patch("scripts.cron.LOCK_FILE", lock_path), \
             patch("scripts.cron.LOG_FILE", log_path), \
             patch("scripts.cron.REPO_NOTES_BASE", tmp_path), \
             patch("scripts.cron.get_all_stale_repos", return_value=[]):
            auto_update_all_repos()

        assert not lock_path.exists()  # Lock released

    def test_auto_update_skips_if_locked(self, tmp_path):
        """auto_update_all_repos should skip if lock is held by live process."""
        from scripts.cron import auto_update_all_repos

        lock_path = tmp_path / ".cron.lock"
        lock_path.write_text(str(os.getpid()))  # Our PID — alive
        log_path = tmp_path / "cron.log"

        with patch("scripts.cron.LOCK_FILE", lock_path), \
             patch("scripts.cron.LOG_FILE", log_path), \
             patch("scripts.cron.REPO_NOTES_BASE", tmp_path), \
             patch("scripts.cron.get_all_stale_repos") as mock_stale:
            auto_update_all_repos()

        mock_stale.assert_not_called()  # Should have bailed before checking staleness

    def test_auto_update_limits_to_max_repos(self, tmp_path):
        """Should process at most MAX_REPOS_PER_RUN repos, sorted by severity."""
        from scripts.cron import select_top_stale_repos, MAX_REPOS_PER_RUN

        repos = [
            {"repo_id": f"org--repo{i}", "total_changed_files": i * 3, "stale_notes": [], "clone_path": f"/tmp/r{i}"}
            for i in range(10)
        ]
        selected = select_top_stale_repos(repos, max_repos=MAX_REPOS_PER_RUN)
        assert len(selected) == MAX_REPOS_PER_RUN
        # Should be sorted by severity descending
        for j in range(len(selected) - 1):
            assert selected[j]["total_changed_files"] >= selected[j + 1]["total_changed_files"]

    def test_auto_update_logs_outcomes(self, tmp_path):
        """Each repo update outcome should be logged."""
        from scripts.cron import log_message

        log_path = tmp_path / "cron.log"
        log_message("org--repo1: success", log_path)
        log_message("org--repo2: timeout", log_path)

        content = log_path.read_text()
        assert "org--repo1: success" in content
        assert "org--repo2: timeout" in content
        # Each line should have a timestamp
        lines = content.strip().split("\n")
        for line in lines:
            assert line.startswith("[")


class TestCronCLI:
    """Test the CLI entry points for cron and auto-update commands."""

    def test_parse_interval_default(self):
        """Default interval should be 6 hours."""
        from scripts.cron import parse_interval

        assert parse_interval("6h") == 6
        assert parse_interval(None) == 6

    def test_parse_interval_custom(self):
        """Should parse Nh format."""
        from scripts.cron import parse_interval

        assert parse_interval("12h") == 12
        assert parse_interval("1h") == 1
        assert parse_interval("24h") == 24

    def test_parse_interval_invalid(self):
        """Should raise ValueError for bad format."""
        from scripts.cron import parse_interval

        with pytest.raises(ValueError):
            parse_interval("abc")
        with pytest.raises(ValueError):
            parse_interval("6m")  # Only hours supported

    def test_handle_cron_install(self, tmp_path):
        """handle_cron with --install should call install_cron."""
        from scripts.cron import handle_cron

        plist_path = tmp_path / "test.plist"
        with patch("scripts.cron.install_cron", return_value="Installed") as mock_install:
            handle_cron(install=True, uninstall=False, interval="6h")

        mock_install.assert_called_once_with(interval_hours=6)

    def test_handle_cron_uninstall(self):
        """handle_cron with --uninstall should call uninstall_cron."""
        from scripts.cron import handle_cron

        with patch("scripts.cron.uninstall_cron", return_value="Removed") as mock_uninstall:
            handle_cron(install=False, uninstall=True, interval=None)

        mock_uninstall.assert_called_once()
