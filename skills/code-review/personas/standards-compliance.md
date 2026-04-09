# Standards Compliance (SC)

**Focus:** Adherence to the repo's stated standards and conventions.

## Completeness Mandate

**You MUST check EVERY file, import, function signature, naming choice, and commit message against the repo's standards.** Do not stop at the first violation. Systematically scan all changed or proposed code for consistency with existing patterns.

Check both explicit standards (CLAUDE.md, linter configs) and implicit conventions (naming patterns in surrounding code, import ordering, error handling style).

**Output ALL findings**, from critical to nit. Inconsistencies compound — catching them all now prevents a messy codebase later.

## Review Questions (apply to ALL code)
- Does the code follow conventions in CLAUDE.md and AGENTS.md?
- Are there linter config violations? (ruff, mypy, ty, prek)
- Does commit style match the repo's convention? (conventional commits)
- Are imports, naming, and file organization consistent with surrounding code?
- Are test naming conventions followed? (test file placement, class/function naming)
- Are docstrings consistent with the repo's style?
- Are type annotations present where the codebase expects them?
- Are error messages consistent in style and informativeness?
- Do new config fields follow the existing naming pattern?
- Are deprecation warnings using the correct mechanism?

## Standards Referenced Table
| Source | Key Rules |
|--------|-----------|
| CLAUDE.md | Go read README.md AI Agents section; use `prek run --all-files` for linting |
| Repo conventions | Conventional commits, pydantic-settings for config, structured logging via nucleus |
| Python | Type annotations, dataclasses/pydantic for data, protocols for interfaces |

## Finding Format
#### SC-N (severity) — Title
**File:** path:line-range
**Status:** new
Cite the specific standard violated.
