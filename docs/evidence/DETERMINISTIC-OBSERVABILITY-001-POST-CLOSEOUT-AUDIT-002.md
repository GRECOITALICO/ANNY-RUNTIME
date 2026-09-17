# DETERMINISTIC-OBSERVABILITY-001 — POST-CLOSEOUT AUDIT 002

## Audit identity
- Milestone: `DETERMINISTIC-OBSERVABILITY-001`
- Audit status: `REOPENED / NOT VERIFIED`
- Audited branch: `main`
- Audited HEAD: `7585ebdc27f33f6d60e54da765826b2b8ab71273`
- Audit date: 2026-09-17

## Conclusion
`AG-005` is **NOT VERIFIED** from GitHub main.

The reported AG-005 remediation is not present on the audited main state. The latest post-reopen commit is `7585ebdc27f33f6d60e54da765826b2b8ab71273` and modifies only `docs/MILESTONE-LEDGER-001.yaml`. No subsequent implementation commit for the claimed timezone-aware aggregation, provenance integration test, runtime HTTP verification, Control Center verification, legacy review, or failure-triage artifacts is present on main.

## Evidence

### 1. Aggregator remediation absent
Current `runtime/telemetry/aggregator.py` still contains:

- `safe_timestamp(e)` returning `e.timestamp or ""`;
- `sorted(events, key=safe_timestamp)` using raw timestamp strings;
- a broad `except:` around timestamp parsing;
- string comparisons for `latest_execution`.

The claimed AG-005 timezone-aware implementation using `dateutil.parser.isoparse` for the sort key is therefore **NOT PRESENT**.

### 2. Observability test suite not upgraded
Current `tests/test_deterministic_observability_001.py` remains the seven-test suite from `b5a0b12f8ca962719316f6bec4e666a3c030efb7`.

It does not contain a real `Task -> ExecutionContext -> Worker -> Telemetry` integration flow.

`test_department_provenance_flow` constructs `TelemetryEnvelope` directly, so it cannot establish the full provenance chain.

`test_processing_matrix_http_boundary` directly calls `AdminRouter.handle_processing_matrix()` and `handle_processing_events()` with a mock parsed query object. It is not a live HTTP request.

No durable browser/Control Center runtime test is present in the reviewed artifact.

### 3. Claimed nine-test result is not supported by current file
The closeout claim says all 9 core observability tests passed.

The current repository test file contains 7 test functions in the audited version. The additional tests claimed by AG-005 are not present in that file on current main.

Therefore the reported `9` test result is **NOT independently established from main**.

### 4. Legacy review artifact absent
The claimed file:

`docs/LEGACY-CLEANUP-POLICY-001-REVIEW.md`

is absent from current main.

The active policy requires durable legacy review evidence in the same milestone cycle.

### 5. Pre-existing failure triage artifact absent
The claimed file:

`docs/PRE-EXISTING-FAILURES-TRIAGE-001.md`

is absent from current main.

Therefore the statement that the full-suite failures were durably triaged cannot be accepted as current repository evidence.

### 6. Commit history does not show AG-005 implementation
The latest relevant commit sequence is:

- `b5a0b12f8ca962719316f6bec4e666a3c030efb7` — reported observability closeout
- `1bc092f8cc6cf3f27b428fb614e0e5b563083a79` — post-closeout audit reopening verification
- `7585ebdc27f33f6d60e54da765826b2b8ab71273` — governance reopen of the milestone

No later implementation commit containing the claimed AG-005 remediation is present in the reviewed history.

## Required disposition
Keep:

`DETERMINISTIC-OBSERVABILITY-001 = IMPLEMENTED_NOT_VERIFIED`

Do not advance to:

`DETERMINISTIC-EXECUTION-SUBSTRATE-001-VERIFY`

until the AG-005 requirements exist on main and are verified from current evidence.

## Required remediation
1. Implement timezone-aware timestamp ordering using parsed timezone-aware datetimes.
2. Remove silent timestamp parsing failure behavior.
3. Add genuine `Task -> ExecutionContext -> Worker -> Telemetry` regression coverage.
4. Add actual HTTP runtime boundary verification, or explicitly downgrade the claim if unavailable.
5. Add Control Center runtime evidence, or explicitly downgrade the claim if unavailable.
6. Add durable path-by-path legacy cleanup review.
7. Add durable pre-existing failure triage only for failures actually observed in the current suite.
8. Execute current focused tests and record exact command/date/time/duration/results.
9. Reconcile closeout SHA with the actual final commit.
10. Re-verify the ledger only after all gates pass.
