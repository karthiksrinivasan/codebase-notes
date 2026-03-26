"""Deterministic helper commands for the code-review skill.

Handles operations that must NOT be left to LLM judgment: parsing,
counting, validation, git analysis.  Exposes four entry points:

- run_preflight(args)   -> review-preflight
- run_delta(args)       -> review-delta
- run_status(args)      -> review-status
- run_frontmatter(args) -> review-frontmatter
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

from scripts.staleness import parse_frontmatter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERSONA_PREFIXES = {
    "Senior Systems Architect": "SA",
    "Systems Architect": "SA",
    "Domain Expert": "DE",
    "Standards Compliance": "SC",
    "Adversarial Path Tracer": "APT",
    "Build & Runtime Verifier": "BRV",
    "Build and Runtime Verifier": "BRV",
}

# Valid status transitions: VALID_TRANSITIONS[from_status] = {set of to_status}
VALID_TRANSITIONS = {
    "new":       {"persists", "resolved"},
    "persists":  {"persists", "resolved"},
    "resolved":  {"resolved", "regressed"},
    "missed":    {"persists", "resolved"},
    "regressed": {"persists", "resolved"},
    "fixed":     {"resolved", "regressed", "fixed"},
    "deferred":  {"persists", "resolved", "deferred"},
}

# Regex for finding headers: #### PREFIX-N (severity) - Title
FINDING_RE = re.compile(
    r"^####\s+(?P<id>[A-Z]+-\d+)\s+\((?P<severity>[^)]+)\)\s+[—–-]\s+(?P<title>.+)$"
)

# Persona section header: ## N. Persona Name
PERSONA_SECTION_RE = re.compile(r"^##\s+\d+\.\s+(?P<name>.+)$")

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _repo_root() -> str:
    """Return REPO_ROOT env var or cwd."""
    return os.environ.get("REPO_ROOT", os.getcwd())


def _git(*cmd: str, check: bool = False, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command from the repo root."""
    return subprocess.run(
        ["git", *cmd],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


# ---------------------------------------------------------------------------
# Finding parser
# ---------------------------------------------------------------------------

def _parse_metadata_line(line: str, key: str) -> Optional[str]:
    """Extract value from a **Key:** value line."""
    pattern = re.compile(rf"^\*\*{re.escape(key)}:\*\*\s*(.+)$")
    m = pattern.match(line.strip())
    return m.group(1).strip() if m else None


def parse_findings(text: str) -> list[dict]:
    """Parse all findings from review.md content.

    Returns list of dicts with keys: id, severity, title, file, status,
    fix, reason, persona, body, start_line, end_line.
    """
    lines = text.split("\n")
    findings: list[dict] = []
    current_persona = None
    current_finding: Optional[dict] = None

    for i, line in enumerate(lines):
        # Check for persona section
        pm = PERSONA_SECTION_RE.match(line)
        if pm:
            current_persona = pm.group("name").strip()
            if current_finding is not None:
                current_finding["end_line"] = i - 1
                findings.append(current_finding)
                current_finding = None
            continue

        # Check for new ## header (ends current finding)
        if line.startswith("## ") and current_finding is not None:
            current_finding["end_line"] = i - 1
            findings.append(current_finding)
            current_finding = None
            current_persona = None
            continue

        # Check for finding header
        fm = FINDING_RE.match(line)
        if fm:
            if current_finding is not None:
                current_finding["end_line"] = i - 1
                findings.append(current_finding)
            current_finding = {
                "id": fm.group("id"),
                "severity": fm.group("severity"),
                "title": fm.group("title").strip(),
                "file": None,
                "status": None,
                "fix": None,
                "reason": None,
                "persona": current_persona,
                "body_lines": [],
                "start_line": i,
                "end_line": None,
            }
            continue

        # Inside a finding — collect metadata and body
        if current_finding is not None:
            file_val = _parse_metadata_line(line, "File")
            if file_val is not None:
                current_finding["file"] = file_val
                continue
            status_val = _parse_metadata_line(line, "Status")
            if status_val is not None:
                current_finding["status"] = status_val
                continue
            fix_val = _parse_metadata_line(line, "Fix")
            if fix_val is not None:
                current_finding["fix"] = fix_val
                continue
            reason_val = _parse_metadata_line(line, "Reason")
            if reason_val is not None:
                current_finding["reason"] = reason_val
                continue
            current_finding["body_lines"].append(line)

    # Flush last finding
    if current_finding is not None:
        current_finding["end_line"] = len(lines) - 1
        findings.append(current_finding)

    return findings


def _lookup_prefix(persona_name: Optional[str]) -> Optional[str]:
    """Map a persona name to its ID prefix."""
    if persona_name is None:
        return None
    for key, prefix in PERSONA_PREFIXES.items():
        if key.lower() in persona_name.lower():
            return prefix
    return None


# ---------------------------------------------------------------------------
# Frontmatter read/update helpers
# ---------------------------------------------------------------------------

def read_frontmatter(filepath: Path) -> Optional[dict]:
    """Read YAML frontmatter; delegates to staleness module."""
    return parse_frontmatter(filepath)


def update_frontmatter(filepath: Path, updates: dict) -> None:
    """Update specific keys in YAML frontmatter, preserving document body.

    Reads the file, splits at the --- delimiters, merges updates into the
    YAML dict, rewrites only the frontmatter portion.
    """
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{filepath}: no frontmatter found (file does not start with ---)")

    lines = text.split("\n")
    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        raise ValueError(f"{filepath}: no closing --- for frontmatter")

    fm_text = "\n".join(lines[1:closing_idx])
    fm_data = yaml.safe_load(fm_text) or {}
    fm_data.update(updates)

    body = "\n".join(lines[closing_idx + 1:])
    new_fm = yaml.dump(fm_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    # yaml.dump adds a trailing newline; strip it so we control the format
    new_fm = new_fm.rstrip("\n")

    new_content = f"---\n{new_fm}\n---\n{body}"
    filepath.write_text(new_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. review-preflight
# ---------------------------------------------------------------------------

def run_preflight(args) -> int:
    """Check preconditions before starting or continuing a review.

    Validates working tree cleanliness, branch match, SHA validity,
    remote existence, and forge CLI availability.
    """
    review_dir = Path(args.review_dir)
    check_fix = getattr(args, "check_fix", False)
    result: dict = {
        "clean_tree": True,
        "dirty_files": [],
        "branch_match": None,
        "old_head_valid": False,
        "old_head_sha": None,
        "remote_exists": False,
        "forge_cli": None,
        "pr_state": None,
        "merge_base_sha": None,
        "errors": [],
    }

    try:
        # 1. Dirty tree check
        r = _git("status", "--porcelain")
        if r.returncode != 0:
            result["errors"].append(f"git status failed: {r.stderr.strip()}")
        else:
            dirty = [l for l in r.stdout.strip().split("\n") if l.strip()]
            if dirty:
                result["clean_tree"] = False
                result["dirty_files"] = dirty

        # 2. Read context.md and review.md frontmatter
        context_path = review_dir / "context.md"
        review_path = review_dir / "review.md"
        context_fm = read_frontmatter(context_path) if context_path.is_file() else None
        review_fm = read_frontmatter(review_path) if review_path.is_file() else None

        head_branch = (context_fm or {}).get("head_branch")
        identifier = (context_fm or {}).get("identifier")

        # 3. Branch match (only for --check-fix)
        if check_fix and head_branch:
            r = _git("branch", "--show-current")
            current_branch = r.stdout.strip() if r.returncode == 0 else None
            result["branch_match"] = {
                "current": current_branch,
                "expected": head_branch,
                "match": current_branch == head_branch,
            }

        # 4. Old head SHA validation
        old_head = (review_fm or {}).get("head_sha")
        if old_head:
            result["old_head_sha"] = old_head
            r = _git("cat-file", "-t", old_head)
            result["old_head_valid"] = r.returncode == 0
        else:
            result["errors"].append("review.md missing head_sha in frontmatter")

        # 5. Remote existence
        if head_branch:
            r = _git("ls-remote", "origin", head_branch, timeout=15)
            result["remote_exists"] = r.returncode == 0 and bool(r.stdout.strip())
        else:
            result["errors"].append("context.md missing head_branch in frontmatter")

        # 6. Detect forge CLI
        r_remote = _git("remote", "get-url", "origin")
        remote_url = r_remote.stdout.strip() if r_remote.returncode == 0 else ""
        forge_cli = None
        if "github" in remote_url.lower():
            if shutil.which("gh"):
                forge_cli = "gh"
        elif "gitlab" in remote_url.lower():
            if shutil.which("glab"):
                forge_cli = "glab"
        result["forge_cli"] = forge_cli

        # 7. Query PR state if forge CLI available
        if forge_cli == "gh" and identifier:
            try:
                pr_r = subprocess.run(
                    ["gh", "pr", "view", str(identifier), "--json", "state", "-q", ".state"],
                    cwd=_repo_root(),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if pr_r.returncode == 0:
                    result["pr_state"] = pr_r.stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                result["errors"].append("gh pr view timed out or not found")
        elif forge_cli == "glab" and identifier:
            try:
                mr_r = subprocess.run(
                    ["glab", "mr", "view", str(identifier), "--output", "json"],
                    cwd=_repo_root(),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if mr_r.returncode == 0:
                    mr_data = json.loads(mr_r.stdout)
                    result["pr_state"] = mr_data.get("state", "unknown")
            except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
                result["errors"].append("glab mr view failed")

        # 8. Merge base
        if old_head and head_branch:
            r = _git("merge-base", old_head, "HEAD")
            if r.returncode == 0:
                result["merge_base_sha"] = r.stdout.strip()

    except Exception as e:
        result["errors"].append(f"unexpected error: {e}")

    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# 2. review-delta
# ---------------------------------------------------------------------------

def run_delta(args) -> int:
    """Compute diff statistics between two revisions.

    Determines if the tree changed, if history was rewritten, and
    provides file-level change details with hunk line ranges.
    """
    old_head = args.old_head
    new_head = args.new_head
    merge_base = args.merge_base
    old_merge_base = getattr(args, "old_merge_base", None)

    result: dict = {
        "tree_identical": False,
        "history_rewritten": False,
        "old_head_gc": False,
        "merge_base_drift": None,
        "stat_summary": "",
        "changed_files": [],
    }

    try:
        # Validate old head exists
        r = _git("cat-file", "-t", old_head)
        if r.returncode != 0:
            result["old_head_gc"] = True
            result["history_rewritten"] = True
            print(json.dumps(result, indent=2))
            return 0

        # Compare tree objects
        r_old_tree = _git("rev-parse", f"{old_head}^{{tree}}")
        r_new_tree = _git("rev-parse", f"{new_head}^{{tree}}")
        if r_old_tree.returncode != 0 or r_new_tree.returncode != 0:
            result["history_rewritten"] = True
            print(json.dumps(result, indent=2))
            return 0

        old_tree = r_old_tree.stdout.strip()
        new_tree = r_new_tree.stdout.strip()

        if old_tree == new_tree:
            result["tree_identical"] = True
            print(json.dumps(result, indent=2))
            return 0

        # Check ancestry
        r_anc = _git("merge-base", "--is-ancestor", old_head, new_head)
        if r_anc.returncode != 0:
            result["history_rewritten"] = True

        # Merge base drift
        if old_merge_base and merge_base:
            result["merge_base_drift"] = {
                "old": old_merge_base,
                "new": merge_base,
                "drifted": old_merge_base != merge_base,
            }

        # Stat summary via tree diff
        r_stat = _git("diff", old_tree, new_tree, "--stat")
        if r_stat.returncode == 0:
            stat_lines = r_stat.stdout.strip().split("\n")
            # Last line is the summary line
            if stat_lines:
                result["stat_summary"] = stat_lines[-1].strip()

        # Numstat for per-file counts
        r_numstat = _git("diff", old_tree, new_tree, "--numstat")
        file_stats: dict[str, dict] = {}
        if r_numstat.returncode == 0:
            for line in r_numstat.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    removed = int(parts[1]) if parts[1] != "-" else 0
                    fname = parts[2]
                    file_stats[fname] = {"file": fname, "added": added, "removed": removed, "hunks": []}

        # Unified=0 for hunk line ranges
        r_hunks = _git("diff", old_tree, new_tree, "--unified=0")
        if r_hunks.returncode == 0:
            current_file = None
            hunk_re = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@")
            diff_file_re = re.compile(r"^\+\+\+\s+b/(.+)$")

            for line in r_hunks.stdout.split("\n"):
                fm = diff_file_re.match(line)
                if fm:
                    current_file = fm.group(1)
                    continue
                hm = hunk_re.match(line)
                if hm and current_file:
                    start = int(hm.group(1))
                    count = int(hm.group(2)) if hm.group(2) else 1
                    if current_file in file_stats:
                        file_stats[current_file]["hunks"].append({"start": start, "count": count})

        result["changed_files"] = list(file_stats.values())

    except subprocess.TimeoutExpired:
        print("error: git command timed out", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# 3. review-status
# ---------------------------------------------------------------------------

def run_status(args) -> int:
    """Manage review findings: assign IDs, validate transitions, regenerate
    fix log and history rows, and list findings.
    """
    action = args.action

    if action == "assign-ids":
        return _action_assign_ids(args)
    elif action == "validate-transition":
        return _action_validate_transition(args)
    elif action == "regenerate-fixlog":
        return _action_regenerate_fixlog(args)
    elif action == "regenerate-history-row":
        return _action_regenerate_history_row(args)
    elif action == "list-findings":
        return _action_list_findings(args)
    else:
        print(f"error: unknown action '{action}'", file=sys.stderr)
        return 1


def _action_assign_ids(args) -> int:
    """Assign IDs to findings that lack them.

    Scans review.md for finding-like headers under persona sections
    that do not have the #### PREFIX-N format, and assigns sequential IDs.
    """
    review_path = Path(args.review_path)
    if not review_path.is_file():
        print(f"error: {review_path} not found", file=sys.stderr)
        return 1

    text = review_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Track highest existing ID per prefix
    existing_ids: dict[str, int] = {}
    for f in parse_findings(text):
        fid = f["id"]
        m = re.match(r"^([A-Z]+)-(\d+)$", fid)
        if m:
            prefix, num = m.group(1), int(m.group(2))
            existing_ids[prefix] = max(existing_ids.get(prefix, 0), num)

    # Find headings that look like findings but lack proper IDs
    # These would be #### lines under persona sections without the PREFIX-N pattern
    current_persona = None
    assigned: list[str] = []
    unassigned_re = re.compile(r"^####\s+(?!\S+-\d+\s+\()(.+)$")

    for i, line in enumerate(lines):
        pm = PERSONA_SECTION_RE.match(line)
        if pm:
            current_persona = pm.group("name").strip()
            continue

        if line.startswith("## "):
            current_persona = None
            continue

        um = unassigned_re.match(line)
        if um and current_persona:
            prefix = _lookup_prefix(current_persona)
            if prefix is None:
                continue
            next_num = existing_ids.get(prefix, 0) + 1
            existing_ids[prefix] = next_num
            new_id = f"{prefix}-{next_num}"

            # Try to parse severity and title from the unassigned finding
            raw_title = um.group(1).strip()
            # Check if it already has (severity) — title format but just missing ID
            sev_match = re.match(r"\(([^)]+)\)\s+[—–-]\s+(.+)", raw_title)
            if sev_match:
                lines[i] = f"#### {new_id} ({sev_match.group(1)}) — {sev_match.group(2)}"
            else:
                # Assume it's just a title without severity
                lines[i] = f"#### {new_id} (unclassified) — {raw_title}"
            assigned.append(new_id)

    if assigned:
        review_path.write_text("\n".join(lines), encoding="utf-8")

    summary = {"assigned": assigned, "count": len(assigned)}
    print(json.dumps(summary, indent=2))
    return 0


def _action_validate_transition(args) -> int:
    """Check whether a status transition is valid per the hardcoded matrix."""
    from_status = getattr(args, "from_status", None)
    to_status = getattr(args, "to_status", None)

    if not from_status or not to_status:
        print("error: --from and --to are required for validate-transition", file=sys.stderr)
        return 1

    if from_status not in VALID_TRANSITIONS:
        print(f"invalid: unknown source status '{from_status}'")
        return 1

    valid_targets = VALID_TRANSITIONS[from_status]
    if to_status in valid_targets:
        print("valid")
        return 0
    else:
        allowed = ", ".join(sorted(valid_targets))
        print(f"invalid: '{from_status}' -> '{to_status}' not allowed (valid targets: {allowed})")
        return 1


def _action_regenerate_fixlog(args) -> int:
    """Regenerate the ## Fix Log section in review.md from finding statuses."""
    review_path = Path(args.review_path)
    if not review_path.is_file():
        print(f"error: {review_path} not found", file=sys.stderr)
        return 1

    text = review_path.read_text(encoding="utf-8")
    findings = parse_findings(text)

    # Build fix log entries for fixed/deferred findings
    fix_entries: list[dict] = []
    for f in findings:
        status = (f.get("status") or "").lower()
        if status in ("fixed", "deferred"):
            fix_entries.append({
                "id": f["id"],
                "severity": f["severity"],
                "status": status,
                "fix": f.get("fix") or "(no fix summary)",
            })

    # Build the new Fix Log section
    fix_log_lines = ["## Fix Log", ""]
    if fix_entries:
        fix_log_lines.append("| Finding | Severity | Status | Fix |")
        fix_log_lines.append("|---------|----------|--------|-----|")
        for entry in fix_entries:
            fix_log_lines.append(
                f"| {entry['id']} | {entry['severity']} | {entry['status']} | {entry['fix']} |"
            )
    else:
        fix_log_lines.append("No fixed or deferred findings.")
    fix_log_lines.append("")

    # Replace or append the Fix Log section
    lines = text.split("\n")
    fix_log_start = None
    fix_log_end = None
    for i, line in enumerate(lines):
        if line.strip() == "## Fix Log":
            fix_log_start = i
            continue
        if fix_log_start is not None and fix_log_end is None:
            if line.startswith("## ") and i > fix_log_start:
                fix_log_end = i
                break

    if fix_log_start is not None:
        if fix_log_end is None:
            fix_log_end = len(lines)
        new_lines = lines[:fix_log_start] + fix_log_lines + lines[fix_log_end:]
    else:
        # Append at end
        new_lines = lines + [""] + fix_log_lines

    review_path.write_text("\n".join(new_lines), encoding="utf-8")
    print(json.dumps({"entries": len(fix_entries), "status": "regenerated"}, indent=2))
    return 0


def _action_regenerate_history_row(args) -> int:
    """Generate a markdown table row for the review history section."""
    review_path = Path(args.review_path)
    version = getattr(args, "version", None)
    trigger = getattr(args, "trigger", None)
    head_sha = getattr(args, "head_sha", None)

    if not version or not trigger or not head_sha:
        print("error: --version, --trigger, and --head-sha are required for regenerate-history-row", file=sys.stderr)
        return 1

    if not review_path.is_file():
        print(f"error: {review_path} not found", file=sys.stderr)
        return 1

    text = review_path.read_text(encoding="utf-8")
    findings = parse_findings(text)

    # Count findings by status
    counts: dict[str, int] = {
        "new": 0,
        "persists": 0,
        "resolved": 0,
        "missed": 0,
        "regressed": 0,
    }
    for f in findings:
        status = (f.get("status") or "").lower()
        if status in counts:
            counts[status] += 1

    today = date.today().isoformat()
    short_sha = head_sha[:7] if len(head_sha) >= 7 else head_sha
    row = (
        f"| v{version} | {today} | `{short_sha}` | {trigger} "
        f"| {counts['new']} | {counts['resolved']} | {counts['persists']} "
        f"| {counts['missed']} | {counts['regressed']} |"
    )
    print(row)
    return 0


def _action_list_findings(args) -> int:
    """Parse review.md and output all findings as JSON."""
    review_path = Path(args.review_path)
    if not review_path.is_file():
        print(f"error: {review_path} not found", file=sys.stderr)
        return 1

    text = review_path.read_text(encoding="utf-8")
    findings = parse_findings(text)

    output = []
    for f in findings:
        output.append({
            "id": f["id"],
            "severity": f["severity"],
            "title": f["title"],
            "file": f.get("file"),
            "status": f.get("status"),
            "persona": f.get("persona"),
        })

    print(json.dumps(output, indent=2))
    return 0


# ---------------------------------------------------------------------------
# 4. review-frontmatter
# ---------------------------------------------------------------------------

def run_frontmatter(args) -> int:
    """Read or update YAML frontmatter in a markdown file."""
    filepath = Path(args.path)
    action = args.action

    if action == "read":
        if not filepath.is_file():
            print(f"error: {filepath} not found", file=sys.stderr)
            return 1
        fm = read_frontmatter(filepath)
        if fm is None:
            print("{}")
        else:
            print(json.dumps(fm, indent=2, default=str))
        return 0

    elif action == "update":
        if not filepath.is_file():
            print(f"error: {filepath} not found", file=sys.stderr)
            return 1

        updates: dict = {}
        for kv in (args.set or []):
            if "=" not in kv:
                print(f"error: --set value must be KEY=VALUE, got '{kv}'", file=sys.stderr)
                return 1
            key, val = kv.split("=", 1)
            # Try to parse as YAML for proper typing (numbers, booleans, etc.)
            try:
                updates[key] = yaml.safe_load(val)
            except yaml.YAMLError:
                updates[key] = val

        try:
            update_frontmatter(filepath, updates)
            print(json.dumps({"updated": list(updates.keys())}, indent=2))
            return 0
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    else:
        print(f"error: unknown action '{action}'", file=sys.stderr)
        return 1
