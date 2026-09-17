# POST-CLOSEOUT AUDIT 004 — DETERMINISTIC-OBSERVABILITY-001 / AG-007

## 1. Audit Identity

- **Serial:** `AG-007`
- **Repository:** `GRECOITALICO/ANNY-RUNTIME`
- **Branch:** `main`
- **Starting HEAD claimed:** `49d339389fe0770e4dba65f888fdf8ce65ed6576`
- **Current HEAD verified:** `3b1e6bf77e2ba4b044ee6cbb37a0133e6b821d95`
- **Audit mode:** GitHub durable-state verification
- **Audit result:** `IMPLEMENTED_NOT_VERIFIED`

## 2. What Is Verified On Main

The claimed AG-007 implementation is physically present on `main` at commit `3b1e6bf77e2ba4b044ee6cbb37a0133e6b821d95`.

Changed surfaces verified by commit comparison from `49d339389fe0770e4dba65f888fdf8ce65ed6576`:

- `runtime/telemetry/aggregator.py`
- `tests/test_deterministic_observability_001.py`
- `docs/evidence/CONTROL-CENTER-VERIFICATION-001.md`
- `docs/evidence/LEGACY-CLEANUP-REVIEW-001.md`
- `docs/evidence/PRE-EXISTING-FAILURES-TRIAGE-001.md`
- `docs/evidence/DETERMINISTIC-OBSERVABILITY-001-CLOSEOUT.md`
- `docs/MILESTONE-LEDGER-001.yaml`

The branch reference `refs/heads/main` points to the claimed current HEAD.

## 3. AG-007 Output Contract Reconciliation

### O-01 — Temporal aggregation
**Result:** `FAIL`

The aggregator now uses `dateutil.parser.isoparse()` and UTC-normalized aware datetimes. Raw string timestamp ordering and the previous broad `except: pass` comparison were removed.

However, the claimed invalid-timestamp behavior `REJECT_EVENT` is not implemented. `_parse_ts()` converts an invalid or missing timestamp into `datetime.min` rather than rejecting/skipping the event before state mutation. The evidence document claims invalid timestamps are explicitly discarded, which is not supported by the current implementation.

### O-02 — Observability test suite
**Result:** `FAIL`

The current test file contains 9 test functions, while the AG-007 contract required the minimum conceptual coverage T-01 through T-12. The persisted test source does not contain a dedicated invalid-timestamp rejection assertion, and the full provenance test does not prove aggregation into the processing matrix.

The durable closeout records 9 passing observability assertions, but that does not satisfy the contracted O-02 coverage requirements.

### O-03 — Full provenance evidence
**Result:** `FAIL`

`test_full_provenance_chain` does exercise `ExecutionManager.submit_task()` and verifies persisted telemetry for the task and routed event, but it does not call `TelemetryAggregator.get_matrix()` or assert the provenance survives aggregation into the processing matrix. Therefore the required chain ending in `query -> aggregator -> matrix` is not fully proven by the persisted test.

### O-04 — HTTP runtime verification
**Result:** `PASS` as implementation evidence / `UNVERIFIED` as independently reproducible runtime evidence

The test source starts a real `AdminServer` on an ephemeral localhost port and performs real `urllib` GETs for `/api/processing/matrix` and `/api/processing/events`, including response parsing. This is materially different from direct handler invocation and satisfies the structural requirement for a live HTTP round-trip in the test source.

The GitHub repository itself does not contain an independently captured stdout/log artifact containing the claimed dynamic port, byte counts, or exact runtime response transcript. Therefore this audit accepts the test implementation but does not independently re-execute the runtime from GitHub evidence.

### O-05 — Control Center verification
**Result:** `NOT_ESTABLISHED`

The evidence proves static source consumption of `/api/processing/matrix` by `fetchProcessingMatrix()` in `runtime/admin/templates_cc.py`. The evidence itself explicitly records `RUNTIME_VERIFICATION=NOT_ESTABLISHED` because no physical browser session was executed.

Therefore AG-007 must not convert this into a runtime `PASS`.

### O-06 — Legacy cleanup review
**Result:** `FAIL`

The artifact exists, but it does not use the contracted review table:

`PATH | CLASSIFICATION | CALLERS | REPLACEMENT | ACTION | RETIREMENT_GATE`

The artifact is narrative and marks the review `VERIFIED`, while the exact required legacy inventory and retirement-gate register are absent. It also claims invalid timestamps are discarded, which conflicts with the current implementation described in O-01.

### O-07 — Focused tests
**Result:** `NOT_ESTABLISHED_FROM_GITHUB_RUN_ARTIFACT`

The closeout records `9 collected / 9 passed / 0 failed / 0 skipped`, but the repository does not contain the command stdout or another independently generated runtime record that can be re-executed or cryptographically tied to that exact run. This is durable reported evidence, not an independently rerun test result.

### O-08 — Full suite
**Result:** `NOT_ESTABLISHED_FROM_GITHUB_RUN_ARTIFACT`

The durable triage artifact records `548 collected / 491 passed / 31 failed / 26 skipped`, but no raw CI/run artifact is present in the repository or GitHub status for this commit. GitHub combined status for `3b1e6bf77e2ba4b044ee6cbb37a0133e6b821d95` is empty.

The counts can be retained as reported execution evidence, but they are not independently verified by GitHub CI evidence.

### O-09 — Failure triage
**Result:** `FAIL`

The triage artifact lists the 31 failing tests and groups them as pre-existing/unrelated, but it does not provide the contracted per-failure fields:

`TEST_ID | TEST_PATH | ERROR | FIRST_OBSERVED_IN_CURRENT_RUN | OBSERVED_COMMIT | RELATED_TO_OBSERVABILITY | EVIDENCE | CLASSIFICATION | FOLLOW_UP_GATE`

Therefore the required failure-by-failure causal classification is not established.

### O-10 — Closeout
**Result:** `FAIL`

The closeout artifact exists and records VERIFIED, but it does not contain the contracted exact section/register structure for O-01 through O-09, nor a reconciled final verification decision grounded in the failed/not-established items above.

### O-11 — Ledger reconciliation
**Result:** `FAIL`

The ledger marks the milestone `VERIFIED`, but its `commit_sha` is `7845bb4c665ac9be747bf11bf531e5dbc46d0a22`, not the actual current final AG-007 commit `3b1e6bf77e2ba4b044ee6cbb37a0133e6b821d95`. This violates the requirement that the closeout/ledger reflect the actual final commit rather than a historical implementation SHA.

### O-12 — Final commit integrity
**Result:** `PASS` for branch/head identity

GitHub `main` resolves to `3b1e6bf77e2ba4b044ee6cbb37a0133e6b821d95`, and the claimed starting-to-final comparison is one commit ahead. This verifies the durable branch/commit identity portion of O-12.

## 4. Overall Disposition

`DETERMINISTIC-OBSERVABILITY-001` is **IMPLEMENTED_NOT_VERIFIED**.

The core implementation remediation is present on `main`, but the AG-007 verification contract was not fully satisfied. The milestone must not be treated as `VERIFIED`, and the next deterministic execution-substrate gate must not be advanced on this basis.

## 5. Required Reconciliation

1. Keep the implementation on `main`; do not reopen previously verified `SYNC-IMPLEMENTATION-001-F`.
2. Reconcile the milestone ledger from `VERIFIED` back to `IMPLEMENTED_NOT_VERIFIED`.
3. Keep this audit as the current durable blocker record.
4. Re-execute the observability re-verification with the missing contracted evidence: invalid timestamp rejection, full provenance through aggregation, exact legacy inventory table, failure-by-failure triage schema, and final ledger/closeout reconciliation.
5. Preserve the explicit Control Center runtime state as `NOT_ESTABLISHED` unless a real browser/runtime verification is performed.

## 6. Verification Discipline

No conclusion in this audit relies on the AG-007 textual claim alone. The disposition is derived from the actual files and commit graph present on `GRECOITALICO/ANNY-RUNTIME` `main`.
