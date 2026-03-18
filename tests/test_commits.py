"""Tests for scripts.commits — git log extraction and markdown generation."""

import os
import textwrap
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.commits import (
    parse_git_log_output,
    Commit,
    group_commits_by_author,
    group_by_path_prefix,
)


# Sample git log output matching --format="%H|%an|%ae|%ad|%s"
SAMPLE_GIT_LOG = textwrap.dedent("""\
    abc1234abc1234abc1234abc1234abc1234abc1234|Alice Smith|alice@company.com|Mon Mar 10 14:30:00 2026 -0700|Refactor auth middleware to JWT
    def5678def5678def5678def5678def5678def5678|Alice Smith|alice@company.com|Wed Mar 5 09:15:00 2026 -0700|Add rate limiting to /users endpoint
    111aaaa111aaaa111aaaa111aaaa111aaaa111aaaa|Bob Jones|bob@company.com|Tue Mar 11 10:00:00 2026 -0700|Fix database connection pooling
    222bbbb222bbbb222bbbb222bbbb222bbbb222bbbb|Alice Smith|alice@company.com|Mon Mar 3 16:45:00 2026 -0700|Update API documentation
    333cccc333cccc333cccc333cccc333cccc333cccc|Bob Jones|bob@company.com|Fri Feb 28 11:20:00 2026 -0700|Add user profile endpoints
""").strip()


class TestParseGitLog:
    """Test parsing raw git log output into Commit objects."""

    def test_parses_all_commits(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        assert len(commits) == 5

    def test_commit_fields(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        c = commits[0]
        assert isinstance(c, Commit)
        assert c.hash == "abc1234abc1234abc1234abc1234abc1234abc1234"
        assert c.author == "Alice Smith"
        assert c.email == "alice@company.com"
        assert "Refactor auth middleware" in c.subject

    def test_handles_empty_input(self):
        commits = parse_git_log_output("")
        assert commits == []

    def test_handles_malformed_lines(self):
        """Lines that don't have exactly 5 pipe-separated fields are skipped."""
        bad_input = "not|enough|fields\ngood_hash|Author|email@x.com|Mon Mar 10 14:30:00 2026 -0700|Subject"
        commits = parse_git_log_output(bad_input)
        assert len(commits) == 1

    def test_date_parsed(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        c = commits[0]
        assert isinstance(c.date, str)
        assert "2026" in c.date


class TestGroupByAuthor:
    """Test grouping commits by author name."""

    def test_groups_correctly(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        grouped = group_commits_by_author(commits)
        assert "Alice Smith" in grouped
        assert "Bob Jones" in grouped
        assert len(grouped["Alice Smith"]) == 3
        assert len(grouped["Bob Jones"]) == 2

    def test_empty_list(self):
        grouped = group_commits_by_author([])
        assert grouped == {}


class TestGroupByPathPrefix:
    """Test grouping commits by path prefix."""

    def test_default_depth_2(self):
        # Simulated file paths from git log
        paths = [
            "src/api/routes.py",
            "src/api/middleware.py",
            "src/models/user.py",
            "docs/readme.md",
        ]
        grouped = group_by_path_prefix(paths, depth=2)
        assert "src/api" in grouped
        assert "src/models" in grouped
        assert "docs" in grouped  # only 1 level deep, so just "docs"

    def test_depth_1(self):
        paths = ["src/api/routes.py", "src/models/user.py", "docs/readme.md"]
        grouped = group_by_path_prefix(paths, depth=1)
        assert "src" in grouped
        assert "docs" in grouped
        assert len(grouped) == 2

    def test_root_level_files(self):
        paths = ["README.md", "setup.py"]
        grouped = group_by_path_prefix(paths, depth=2)
        # Root-level files group under "." or "root"
        assert len(grouped) == 1


from scripts.commits import (
    generate_commit_markdown,
    path_to_slug,
    parse_frontmatter,
    merge_commits_into_existing,
)


class TestPathToSlug:
    """Test path-to-filename slug conversion."""

    def test_simple_path(self):
        assert path_to_slug("src/api") == "src-api"

    def test_deep_path(self):
        assert path_to_slug("src/api/v2") == "src-api-v2"

    def test_root_path(self):
        assert path_to_slug(".") == "root"

    def test_strips_slashes(self):
        assert path_to_slug("src/api/") == "src-api"


class TestGenerateCommitMarkdown:
    """Test markdown output generation."""

    def test_produces_valid_frontmatter(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        alice_commits = [c for c in commits if c.author == "Alice Smith"]
        md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=alice_commits,
            date_range="2026-02-18 to 2026-03-18",
        )
        # Should start with YAML frontmatter
        assert md.startswith("---\n")
        # Parse frontmatter
        fm = parse_frontmatter(md)
        assert fm["author"] == "Alice Smith"
        assert fm["author_email"] == "alice@company.com"
        assert fm["path_filter"] == "src/api/"
        assert "2026-02-18" in fm["date_range"]
        assert "last_updated" in fm

    def test_contains_commit_table(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        alice_commits = [c for c in commits if c.author == "Alice Smith"]
        md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=alice_commits,
            date_range="2026-02-18 to 2026-03-18",
        )
        assert "| Date | Message |" in md  # table header
        assert "Refactor auth middleware" in md
        assert "Add rate limiting" in md

    def test_contains_summary_placeholder(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter=".",
            commits=commits[:1],
            date_range="2026-03-18 to 2026-03-18",
        )
        assert "## Summary" in md

    def test_heading_format(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        md = generate_commit_markdown(
            author="Bob Jones",
            email="bob@company.com",
            path_filter="src/models/",
            commits=commits[-1:],
            date_range="2026-02-28 to 2026-02-28",
        )
        assert "# Bob Jones" in md


class TestMergeCommits:
    """Test deduplication when merging into existing markdown."""

    def test_merge_deduplicates_by_hash(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        existing_md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=commits[:2],
            date_range="2026-03-05 to 2026-03-10",
        )
        # Now merge with overlapping + new commits
        all_alice = [c for c in commits if c.author == "Alice Smith"]
        merged_md = merge_commits_into_existing(
            existing_md=existing_md,
            new_commits=all_alice,
            date_range="2026-03-03 to 2026-03-10",
        )
        # Should have all 3 unique Alice commits, not 2 + 3 = 5
        # Check the short hash (8 chars) appears exactly once
        hash_count = merged_md.count("`abc1234a`")
        assert hash_count == 1  # not duplicated

    def test_merge_preserves_summary_section(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        existing_md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=commits[:1],
            date_range="2026-03-10 to 2026-03-10",
        )
        # Simulate Claude having filled in the summary
        existing_md = existing_md.replace(
            "## Summary\n\n[Claude-generated narrative summary — to be filled by Claude]\n",
            "## Summary\n\nAlice refactored the auth middleware to use JWT tokens.\n",
        )
        merged_md = merge_commits_into_existing(
            existing_md=existing_md,
            new_commits=commits[:2],
            date_range="2026-03-05 to 2026-03-10",
        )
        assert "Alice refactored the auth middleware" in merged_md

    def test_merge_updates_frontmatter_dates(self):
        commits = parse_git_log_output(SAMPLE_GIT_LOG)
        existing_md = generate_commit_markdown(
            author="Alice Smith",
            email="alice@company.com",
            path_filter="src/api/",
            commits=commits[:1],
            date_range="2026-03-10 to 2026-03-10",
        )
        merged_md = merge_commits_into_existing(
            existing_md=existing_md,
            new_commits=commits[:2],
            date_range="2026-03-05 to 2026-03-10",
        )
        fm = parse_frontmatter(merged_md)
        assert "2026-03-05" in fm["date_range"]


from scripts.commits import (
    run_git_log,
    run_commits_command,
    get_changed_files_for_commit,
)


SAMPLE_GIT_LOG_WITH_FILES = SAMPLE_GIT_LOG  # reuse same fixture


class TestRunGitLog:
    """Test the subprocess wrapper for git log."""

    @patch("scripts.commits.subprocess.run")
    def test_calls_git_with_correct_args(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        commits = run_git_log(since="4w", path="src/api/", cwd="/fake/repo")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "git" in cmd[0]
        assert "log" in cmd
        assert '--format=%H|%an|%ae|%ad|%s' in cmd
        assert "--since=4w" in cmd
        assert "src/api/" in cmd
        assert len(commits) == 5

    @patch("scripts.commits.subprocess.run")
    def test_default_since_4w(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        run_git_log(since=None, path=None, cwd="/fake/repo")
        cmd = mock_run.call_args[0][0]
        assert "--since=4w" in cmd

    @patch("scripts.commits.subprocess.run")
    def test_handles_git_error_gracefully(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: not a git repository", returncode=128
        )
        commits = run_git_log(since="4w", path=None, cwd="/fake/repo")
        assert commits == []


class TestRunCommitsCommand:
    """Integration test for the full commits command with mocked git."""

    @patch("scripts.commits.subprocess.run")
    @patch("scripts.commits.resolve_repo_id", return_value="test--repo")
    def test_creates_output_files(self, mock_repo_id, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        # Patch get_notes_dir to use tmp_path
        commits_dir = tmp_path / "commits"
        with patch("scripts.commits.get_notes_dir", return_value=tmp_path):
            run_commits_command(
                author=None,  # all authors
                since="4w",
                path="src/",
                repo_id=None,
                cwd="/fake/repo",
                depth=2,
            )

        # Should create author directories
        assert (commits_dir / "Alice Smith").is_dir() or (commits_dir / "alice-smith").is_dir()

    @patch("scripts.commits.subprocess.run")
    @patch("scripts.commits.resolve_repo_id", return_value="test--repo")
    def test_output_file_has_valid_frontmatter(self, mock_repo_id, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        commits_dir = tmp_path / "commits"
        with patch("scripts.commits.get_notes_dir", return_value=tmp_path):
            run_commits_command(
                author="Alice Smith",
                since="4w",
                path=None,
                repo_id=None,
                cwd="/fake/repo",
                depth=2,
            )

        # Find any generated .md file
        md_files = list(commits_dir.rglob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text()
        fm = parse_frontmatter(content)
        assert fm["author"] == "Alice Smith"
        assert "## Commits" in content

    @patch("scripts.commits.subprocess.run")
    @patch("scripts.commits.resolve_repo_id", return_value="test--repo")
    def test_merge_mode_deduplicates(self, mock_repo_id, mock_run, tmp_path):
        """Running commits command twice should not duplicate entries."""
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_GIT_LOG, stderr="", returncode=0
        )
        with patch("scripts.commits.get_notes_dir", return_value=tmp_path):
            run_commits_command(
                author="Alice Smith", since="4w", path=None,
                repo_id=None, cwd="/fake/repo", depth=2,
            )
            # Run again — should merge, not duplicate
            run_commits_command(
                author="Alice Smith", since="4w", path=None,
                repo_id=None, cwd="/fake/repo", depth=2,
            )

        md_files = list((tmp_path / "commits").rglob("*.md"))
        for md_file in md_files:
            content = md_file.read_text()
            # Count occurrences of Alice's first commit hash (short)
            count = content.count("`abc1234a`")
            assert count <= 1, f"Duplicate hash found in {md_file}"
