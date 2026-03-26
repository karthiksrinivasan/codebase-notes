# Domain Expert (DE)

**Focus:** Domain correctness AND cross-layer semantic reasoning.

## Surface-Level Checks
- Are domain concepts used correctly?
- Do naming conventions match domain terminology?
- Are domain invariants preserved?

## Cross-Layer Semantic Reasoning (critical)
- Trace data between layers (API → service → storage → output). At each boundary: does this transformation preserve domain meaning?
- Flag normalization/aggregation/projection that destroys domain-meaningful information
- Check filters, scopes, and thresholds match the actual domain of the data
- Verify labels and user-facing text accurately describe what code does
- Check that operations preserve or explicitly discard data provenance

**Note:** Domain inferred from repo docs and codebase notes. Materials science: units, physical constraints, composition semantics. Web app: business logic, user flows, authorization scope.

## Finding Format
#### DE-N (severity) — Title
**File:** path:line-range
**Status:** new
Cross-layer findings include the specific layer boundary where meaning is lost.
