# POST-CLOSEOUT AUDIT: DETERMINISTIC-OBSERVABILITY-001

Audit date: 2026-09-17
Audited ref: `main`
Audited HEAD: `b5a0b12f8ca962719316f6bec4e666a3c030efb7`
Previous implementation milestone: `6173a87b4ca21d1865649bf3bd82ff58588aa547`

## Determination

`DETERMINISTIC-OBSERVABILITY-001 = IMPLEMENTED_NOT_VERIFIED`

The implementation and requested test artifact are present on `main`, but the durable verification chain is not sufficient for `VERIFIED` under the ANNY milestone rules and the active legacy-cleanup policy.

## Confirmed on main

- `runtime/telemetry/aggregator.py` contains a chronological sort before execution-state folding.
- `tests/test_deterministic_observability_001.py` exists with 7 test functions.
- `docs/evidence/DETERMINISTIC-OBSERVABILITY-001-CLOSEOUT.md` exists.
- `docs/MILESTONE-LEDGER-001.yaml` records the milestone as `VERIFIED`.
- `SYNC-IMPLEMENTATION-001-F` remains `VERIFIED` and is not reopened.
- `next_p0` has moved to `DETERMINISTIC-EXECUTION-SUBSTRATE-001-VERIFY` in the current ledger.

## Blockers

### 1. Current test execution is not independently established

The closeout lists seven tests as `PASSED`, but it does not contain the exact command, date/time, duration, or complete current execution result required by the milestone process.

No CI status is attached to commit `b5a0b12f8ca962719316f6bec4e666a3c030efb7` through the available GitHub status endpoint.

Therefore the durable repository proves that test results were asserted in the closeout, but does not independently establish execution during this audit.

### 2. Department provenance test is narrower than the claim

`test_department_provenance_flow` creates a `TelemetryEnvelope` directly and asserts that the aggregator sees the supplied `department_id`.

It does not exercise the claimed full chain:

`Task -> ExecutionContext -> Worker -> Telemetry`

Therefore the closeout wording "from task creation down to telemetry ingestion" is stronger than the test currently proves.

### 3. HTTP boundary test is not an HTTP runtime test

`test_processing_matrix_http_boundary` directly instantiates `AdminRouter`, constructs a mock parsed query object, and invokes `handle_processing_matrix()` / `handle_processing_events()` directly.

This verifies handler behavior, not a live HTTP request through the actual server boundary.

Therefore the closeout must not classify this as runtime/E2E HTTP verification.

### 4. Control Center verification is not durable

The closeout states that the Control Center UI was verified, but the new test file contains no browser/control-center rendering test and no durable runtime/browser transcript or artifact establishing that verification.

The route definitions exist, but route existence is not equivalent to UI runtime verification.

### 5. Temporal ordering implementation is only string-sorted

`TelemetryAggregator.get_matrix()` sorts by `event.timestamp` as a raw string.

The repository also imports an ISO timestamp parser, but the new sorting key does not parse timestamps into timezone-aware datetime values before ordering.

This needs an explicit regression test covering equivalent instants represented with different UTC offsets, e.g. `10:00Z` versus `11:00+01:00`.

Lexical ordering is not a sufficient deterministic time-order contract for arbitrary valid ISO-8601 offsets.

### 6. Ledger reconciliation is incomplete

The milestone entry remains:

`commit_sha: 6173a87b4ca21d1865649bf3bd82ff58588aa547`

while the verification/closeout commit is:

`b5a0b12f8ca962719316f6bec4e666a3c030efb7`

The milestone entry has no milestone-local `next_action`.

The repository rule explicitly requires every new milestone to record `commit_sha` and `next_action`.

### 7. Current documentation anchor is stale

`current_documentation_anchor.commit_sha` still points to:

`df2b247877f0aefd74c4940fb20b1c1fd6cac7b2`

and its note still describes the old reopened F audit, despite F subsequently being verified and the repository having advanced through the observability milestone.

This is contradictory durable state.

### 8. Referenced pre-existing failure triage artifact is absent

The walkthrough claims broader test failures were isolated using `preexisting_failures_triage.md` and Rule 22.

No `preexisting_failures_triage.md` was found at repository root or by repository code search.

That claim therefore lacks the referenced durable support.

## Legacy cleanup determination

`LEGACY REVIEW = NOT_CLEARED_FOR_CLOSEOUT`

The current routes and telemetry implementations were inspected, but the closeout evidence does not provide a sufficiently durable, path-by-path removal/retention record satisfying `LEGACY-CLEANUP-POLICY-001`.

The policy requires inspected surfaces, deleted/deprecated paths, remaining exceptions and removal gates, current test results, and the actual commit SHA containing the cleanup.

The closeout instead states that old paths were scrubbed in prior commits without enumerating the reviewed surfaces and exact dispositions.

## Required remediation

1. Add real current test execution evidence with exact command/date/time/result.
2. Add an actual Task -> ExecutionContext -> Worker -> Telemetry provenance regression.
3. Add a true runtime HTTP boundary verification or explicitly downgrade the evidence to handler-level verification.
4. Provide durable Control Center runtime evidence or downgrade that claim.
5. Change timestamp ordering to parsed timezone-aware instants or add sufficient parsing-aware reduction logic, with offset regression tests.
6. Reconcile milestone `commit_sha`, `next_action`, and `current_documentation_anchor`.
7. Add the missing durable triage artifact or remove the claim that relies on it.
8. Produce a path-by-path legacy review with `REMOVE`, `RETAIN_WITH_BLOCKER`, or `HISTORICAL_ONLY` dispositions.

## Gate

Until the remediation above is completed and current evidence is recorded:

`DETERMINISTIC-OBSERVABILITY-001 = IMPLEMENTED_NOT_VERIFIED`

`DETERMINISTIC-EXECUTION-SUBSTRATE-001-VERIFY` must not be treated as the trusted next resume point yet; observability verification remains the active gate.
