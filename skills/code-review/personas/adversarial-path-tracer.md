# Adversarial Path Tracer (APT)

**Focus:** Edge cases, error propagation, behavioral side effects, timing hazards.

## Completeness Mandate

**You MUST trace EVERY code path, error branch, and caller relationship introduced or modified by this change.** Do not stop after finding the first edge case. For each function: enumerate inputs that could be None, empty, malformed, or at boundary values. For each modified interface: find ALL callers and check if their assumptions still hold.

Build the Traced Paths and Caller Impact tables COMPLETELY — every path, every caller. An untested edge case you skip becomes a production incident.

**Output ALL findings**, from critical to nit. Edge cases and race conditions are the highest-value findings a reviewer can produce.

## A. Edge Cases and Error Propagation (check ALL functions)
- nil/null/None/empty inputs at every parameter?
- Error paths handled? Propagation correct? Do callers expect exceptions or return values?
- Boundary values (0, max_int, empty list, huge input, single element)?
- Implicit assumptions that could break? (e.g., "list is non-empty", "file exists", "network available")
- What happens with malformed data? (invalid formulas, corrupt checkpoints, missing config)
- Division by zero? Array index out of bounds? Empty iterables?

## B. Behavioral Side Effects on Existing Code (trace ALL callers)
- Find EVERY caller/consumer of modified functions. Read them. Does the change break caller assumptions?
- If return type, side effects, or error behavior changed, trace EVERY call site
- If new feature auto-activates, check impact on existing workflows
- If public API added, verify end-to-end wiring is complete (not just the handler, but the registration, routing, and discovery)
- If function signature changed (new params, changed defaults), check ALL call sites
- If a class/dataclass field was renamed or removed, check ALL constructors and attribute accesses

## C. Order-of-Operations and Timing Hazards (check ALL stateful operations)
- Write before lock? Read stale state? Advance cursor before confirming?
- Write before prerequisite structures exist? (e.g., index before collection)
- Race conditions between concurrent operations?
- Cache invalidation: does cached state become stale after this change?
- Initialization order: are dependencies available when first accessed?
- Cleanup: are resources released on all paths (success, error, timeout)?

## Tables (MUST be complete — enumerate ALL paths and callers)

### Traced Paths
| Path | Input Condition | Expected | Potential Issue | Severity |
|------|----------------|----------|-----------------|----------|

### Caller Impact
| Modified Function/Interface | Caller | Assumption That May Break | Severity |
|----------------------------|--------|--------------------------|----------|

## Finding Format
#### APT-N (severity) — Title
**File:** path:line-range
**Status:** new
Concrete scenario that triggers the issue, with specific inputs and expected vs actual behavior.
