---
identifier: {identifier}
created: {date}
last_updated: {date}
status: reviewed
current_version: 1
head_sha: {head_sha}
merge_base_sha: {merge_base_sha}
last_fix_sha: null
---
# Review: {title}

## Review History

| Version | Date | Head SHA | Trigger | New | Resolved | Persists | Missed | Regressed |
|---------|------|----------|---------|-----|----------|----------|--------|-----------|
| v1 | {date} | `{head_sha}` | new | {new_count} | — | — | — | — |

---

{persona_sections}

## Fix Log

_No fixes applied yet. Use `/codebase-notes:code-review fix "{identifier}"` to address findings._

## Summary

| Persona | Verdict | Critical | Suggestions |
|---------|---------|----------|-------------|
{summary_rows}

## Recommended Actions

{recommended_actions}
