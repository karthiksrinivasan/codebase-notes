# Adversarial Path Tracer (APT)

**Focus:** Edge cases, error propagation, behavioral side effects, timing hazards.

## A. Edge Cases and Error Propagation
- nil/null/None/empty inputs?
- Error paths handled? Propagation correct?
- Boundary values (0, max_int, empty list, huge input)?
- Implicit assumptions that could break?

## B. Behavioral Side Effects on Existing Code
- Find every caller/consumer of modified functions. Read them. Does the change break caller assumptions?
- If return type, side effects, or error behavior changed, trace every call site
- If new feature auto-activates, check impact on existing workflows
- If public API added, verify end-to-end wiring complete

## C. Order-of-Operations and Timing Hazards
- Write before lock? Read stale state? Advance cursor before confirming? Write before prerequisite structures exist? Race conditions?

## Tables
### Traced Paths
| Path | Input Condition | Expected | Potential | Issue? |
|------|----------------|----------|-----------|--------|

### Caller Impact
| Modified Function | Caller | Assumption That May Break | Severity |
|------------------|--------|--------------------------|----------|

## Finding Format
#### APT-N (severity) — Title
**File:** path:line-range
**Status:** new
Concrete scenario that triggers the issue.
