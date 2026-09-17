# SYNC-IMPLEMENTATION-001-F — Post-Closeout Audit 002

Status: IMPLEMENTED_NOT_VERIFIED

## Scope

Repository: `GRECOITALICO/ANNY-RUNTIME`
Branch: `main`
HEAD audited: `66003f733cb9096793ac7fd005f2a612add6c844`
Implementation commit referenced by ledger: `4f21a64c6a06fb1618b4b7d424c0fc51fc98a806`
Previous HEAD: `464359c2debefa8df9926e70658fcc62d5f7e41a`

## Confirmed implementation present

The remote repository now contains:

- explicit Sync lifecycle states excluding `ACTIVATED`;
- asynchronous `SyncService.start()` using a background thread;
- `stage()`, `activate()`, and `rollback()` service methods;
- HTTP handling for `/api/sync`, `/api/sync/status`, `/api/sync/stage`, `/api/sync/activate`, and `/api/sync/rollback`;
- `FailureReason.UNSUPPORTED_EXECUTOR`;
- executor fail-closed handling instead of generic `NotImplementedError`.

## Verification findings

### 1. Concurrency protection is not established strongly enough

`SyncService.start()` checks `_active` and then assigns `_active` without a lock. Two simultaneous callers can race between the check and assignment. The code therefore does not yet establish the claimed deterministic concurrency guarantee under true concurrent invocation.

### 2. Legacy mock fallback remains present

`runtime/execution/worker.py` still contains the fallback to `qwen_mock.json` and creates the file when no real QWEN model artifact is available. This directly contradicts the closeout claim that the mock fallback was removed.

### 3. Current test source does not prove the claimed concurrency coverage

`tests/test_sync_service.py` contains the lifecycle tests and uses `wait()`, but no test in the inspected source creates simultaneous `start()` calls to establish the race-free guarantee claimed by the closeout.

`tests/test_worker_020.py` contains 23 test functions. Together the two files contain 37 test functions, but GitHub does not provide an execution record proving that all 37 passed in `0.41s`.

### 4. No GitHub Actions verification record

The repository has no workflow run associated with implementation commit `4f21a64c6a06fb1618b4b7d424c0fc51fc98a806`, and no combined status was returned for the closeout commit. Therefore the claimed `37 passed in 0.41s` remains self-reported evidence, not independently established remote evidence.

### 5. Closeout evidence contains unresolved placeholder text

`docs/evidence/SYNC-IMPLEMENTATION-001-F-CLOSEOUT.md` still records `Final SHA: [TBD-AFTER-COMMIT]`, so the closeout artifact itself is not fully reconciled with the actual published commit.

### 6. Ledger overstates verification

The current ledger marks `SYNC-IMPLEMENTATION-001-F` as `VERIFIED` even though the mock fallback remains and current runtime/test verification is not independently established.

## Legacy classification

### REMOVE

- `qwen_mock.json` automatic fallback in `runtime/execution/worker.py`.

### RETAIN_WITH_BLOCKER

- asynchronous Sync implementation until atomic concurrency protection is added and tested.
- lifecycle contract itself, which is present but not yet fully verified.

### HISTORICAL_ONLY

- prior audit `SYNC-IMPLEMENTATION-001-F-AUDIT.md` remains valid as historical evidence of the pre-implementation state and must not be treated as current state.

## Required next gate

1. Remove the automatic `qwen_mock.json` fallback.
2. Add atomic concurrency protection around Sync lifecycle entry and test simultaneous `start()` calls.
3. Execute the two focused test files in the current repository state and preserve the real command output as durable evidence.
4. Update the closeout artifact with the actual final SHA.
5. Only then restore `SYNC-IMPLEMENTATION-001-F` to `VERIFIED` if all gates pass.
