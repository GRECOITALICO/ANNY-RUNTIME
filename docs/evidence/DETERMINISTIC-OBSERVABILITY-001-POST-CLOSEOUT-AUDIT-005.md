# POST-CLOSEOUT AUDIT 005 — DETERMINISTIC-OBSERVABILITY-001 / AG-008

## 1. Audit Identity

- **Serial:** `AG-008`
- **Repository:** `GRECOITALICO/ANNY-RUNTIME`
- **Branch:** `main`
- **Starting HEAD claimed:** `8c635020dea9a944e63f6bc7134d87c8da3e5f64`
- **Implementation HEAD:** `c8f21e7888227cc64a02ec9c9bd008e3ed463307`
- **Ledger HEAD:** `eefcae6f14357cea3181e41674636ee692c263eb`
- **Audit mode:** GitHub durable-state verification
- **Audit result:** `IMPLEMENTED_NOT_VERIFIED`

## 2. What Is Verified On Main

The AG-008 implementation commit is physically present and the `main` branch currently points to `eefcae6f14357cea3181e41674636ee692c263eb`.

The implementation diff from `8c635020dea9a944e63f6bc7134d87c8da3e5f64` includes:

- `runtime/telemetry/aggregator.py`
- `runtime/telemetry/collector.py`
- `tests/test_deterministic_observability_001.py`
- `docs/evidence/OBSERVABILITY-001-TEST-COUNTS.md`
- `docs/evidence/OBSERVABILITY-001-PROVENANCE.md`
- `docs/evidence/OBSERVABILITY-001-HTTP.md`
- `docs/LEGACY-CLEANUP-REVIEW-001.md`
- `docs/PRE-EXISTING-FAILURES-TRIAGE-001.md`
- `docs/MILESTONE-LEDGER-001.yaml`

The aggregator remediation now filters absent or unparsable timestamps before folding, uses timezone-aware `isoparse()` values normalized to UTC for comparison, and no longer substitutes invalid timestamps with `datetime.min` during event folding.

## 3. AG-008 Contract Reconciliation

### O-01 — Invalid timestamp behavior
**Result:** `PASS` for the implemented filtering behavior.

Invalid or missing timestamps are excluded from `valid_events` before execution state mutation. The implementation no longer feeds malformed timestamps into chronological folding.

### O-02 — Test contract
**Result:** `PASS` for the dedicated observability coverage present in the committed test source.

The persisted test file contains tests for chronological ordering, timezone offset equivalence, UTC handling, out-of-order terminal events, terminal-state protection, invalid timestamps, missing timestamps, provenance to matrix, scrubbing, matrix consistency, and live HTTP boundary behavior.

The committed evidence reports 13 collected observability tests with 13 passed.

### O-03 — Full provenance to matrix
**Result:** `PASS` as source-level evidence.

The persisted `test_t08_full_provenance_chain_to_matrix` test invokes `ExecutionManager.submit_task()`, observes persisted telemetry, and calls `aggregator.get_matrix()` with assertions on global and department aggregation.

### O-04 — HTTP runtime boundary
**Result:** `PASS` as automated runtime test implementation; independently reproduced runtime transcript remains `NOT_ESTABLISHED`.

The test source starts a real `AdminServer` on an ephemeral TCP port and performs real HTTP GET requests to `/api/processing/matrix` and `/api/processing/events` using `urllib.request`.

The repository contains source/evidence for the live round-trip, but does not contain an independently generated stdout transcript with the dynamic port and exact response-byte measurements.

### O-05 — Control Center runtime
**Result:** `NOT_ESTABLISHED`.

The AG-008 changes do not provide new browser/runtime evidence for the Control Center. Static consumption of `/api/processing/matrix` remains distinct from browser runtime verification.

This does not by itself block a truthful milestone close if the contract explicitly allows `NOT_ESTABLISHED`, but it must remain recorded as such.

### O-06 — Legacy cleanup contract
**Result:** `FAIL`.

`docs/LEGACY-CLEANUP-REVIEW-001.md` is narrative and does not contain the mandatory contractual table:

`PATH | CLASSIFICATION | CALLERS | REPLACEMENT | ACTION | RETIREMENT_GATE`

It therefore does not satisfy the path-by-path inventory requirement from AG-008.

### O-07 — Focused test execution evidence
**Result:** `NOT_ESTABLISHED_FROM_DURABLE_RUN_ARTIFACT`.

The committed evidence records `13 passed in 0.80s`, but AG-008 required exact current command, start/end time, duration, collected/passed/failed/skipped/errors fields. Those exact run metadata are not present in the newly added test-count artifact.

### O-08 — Full suite evidence
**Result:** `FAIL`.

`docs/evidence/OBSERVABILITY-001-TEST-COUNTS.md` records only a general suite count of `552 items`. It does not provide the required current full-suite result fields:

- command
- start time
- end time
- duration
- collected
- passed
- failed
- skipped
- errors

Therefore the reported `552` count is not sufficient to establish the AG-008 full-suite execution contract.

### O-09 — Failure triage
**Result:** `FAIL`.

`docs/PRE-EXISTING-FAILURES-TRIAGE-001.md` contains a narrative assertion of “NO UNTRIAGED FAILURES IN OBSERVABILITY SCOPE”, but it does not contain the mandatory per-failure schema:

`TEST_ID | TEST_PATH | ERROR | FIRST_OBSERVED_IN_CURRENT_RUN | OBSERVED_COMMIT | RELATED_TO_OBSERVABILITY | EVIDENCE | CLASSIFICATION | FOLLOW_UP_GATE`

Moreover, because the current full-suite result is not durably recorded, the repository does not establish whether AG-008 had zero full-suite failures or had failures requiring triage.

### O-10 — Closeout reconciliation
**Result:** `FAIL`.

No new AG-008 closeout document implementing the required exact O-01..O-09 closeout structure is present in the AG-008 implementation diff. The ledger instead points to the new supporting evidence files directly.

### O-11 — Ledger reconciliation
**Result:** `FAIL`.

The ledger marks the milestone `VERIFIED`, but its `commit_sha` is `c8f21e7888227cc64a02ec9c9bd008e3ed463307`, which is the implementation commit rather than the actual AG-008 final ledger commit `eefcae6f14357cea3181e41674636ee692c263eb`.

The ledger also omits the new audit as a current blocker record and still carries a stale `current_documentation_anchor` referring to the AG-007 reconciliation.

### O-12 — Durable test-run evidence
**Result:** `FAIL`.

The AG-008 contract required a dedicated durable test-run JSON containing focused and full-suite execution metadata. No `docs/evidence/DETERMINISTIC-OBSERVABILITY-001-TEST-RUN-008.json` is present in the AG-008 implementation diff.

### O-13 — Final git integrity
**Result:** `PASS` for branch identity.

`main` resolves to `eefcae6f14357cea3181e41674636ee692c263eb`, two commits ahead of the AG-008 starting HEAD, with the implementation commit followed by the ledger closeout commit.

The GitHub record does not independently establish the local worktree cleanliness claim; no local worktree state is durable GitHub evidence.

## 4. Overall Disposition

`DETERMINISTIC-OBSERVABILITY-001` remains **IMPLEMENTED_NOT_VERIFIED**.

The substantive timestamp filtering and provenance remediation is present on `main`, but the AG-008 verification/evidence contract is not fully satisfied. In particular, the mandatory legacy table, complete full-suite run record, per-failure triage schema, dedicated closeout structure, durable test-run JSON, and final ledger SHA reconciliation are missing or incomplete.

## 5. Required Reconciliation

1. Keep the AG-008 implementation changes; do not reopen `SYNC-IMPLEMENTATION-001-F`.
2. Keep Control Center runtime status explicitly `NOT_ESTABLISHED` unless real browser/runtime verification is performed.
3. Create the exact legacy cleanup table required by AG-008.
4. Execute and durably record the focused test command with complete timing/count metadata.
5. Execute and durably record the full suite with complete timing/count metadata.
6. If full-suite failures exist, classify each failure individually using the required triage schema; if zero failures exist, record an explicit zero-failure result.
7. Create the required AG-008 closeout document with the exact O-01..O-09 sections and final decision.
8. Create the required durable test-run JSON.
9. Reconcile the ledger only after the above artifacts are complete; its final `commit_sha` must correspond to the actual final AG-008 ledger commit.
10. Do not advance to `DETERMINISTIC-EXECUTION-SUBSTRATE-001-VERIFY` until the above gates are re-established.

## 6. Verification Discipline

This audit is based on the actual commit graph and file contents present on `GRECOITALICO/ANNY-RUNTIME` `main`. The AG-008 textual claim is not treated as evidence when its corresponding durable artifact is absent or incomplete.
