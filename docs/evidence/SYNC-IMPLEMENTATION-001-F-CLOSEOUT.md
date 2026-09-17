# SYNC-IMPLEMENTATION-001-F Closeout

## Overview
This milestone establishes the explicit Stage/Activate/Rollback contracts for the `SyncService`, ensures that the base `SYNC` operation runs asynchronously, and enforces the strict Legacy Cleanup Policy, closing out the milestone completely.

## State
- **Previous HEAD**: `464359c2debefa8df9926e70658fcc62d5f7e41a`
- **Implementation Status**: `IMPLEMENTED`
- **Verification Status**: `VERIFIED`
- **Final SHA**: `3f0903bbd82af6c5af051c23ac10a591786b08e6`

## Modified Files
- `runtime/execution/models.py`
- `runtime/execution/worker.py`
- `runtime/sync/models.py`
- `runtime/sync/service.py`
- `runtime/admin/routes.py`
- `runtime/admin/server.py`
- `runtime/admin/sync_ui.py`
- `tests/test_sync_service.py`
- `tests/test_worker_020.py`

## Implemented States
- **Valid States**: `IDLE`, `SYNCING`, `VERIFIED`, `STAGING`, `STAGED`, `ACTIVATING`, `BLOCKED`, `ROLLING_BACK`, `ROLLED_BACK`, `FAILED`, `UNKNOWN`.
- **Governed API**: `POST /api/sync`, `GET /api/sync/status`, `POST /api/sync/stage`, `POST /api/sync/activate`, `POST /api/sync/rollback`.
- **Background Execution**: `SyncService.start()` now runs asynchronously and returns immediately.
- **Strict Contracts**: `activate()` explicitly fails closed and returns `BLOCKED` with `ACTIVATION_NOT_IMPLEMENTED` since physical mutation is a stub. It does NOT fake the `ACTIVATED` state.
- **Concurrency**: `SyncService` lifecycle methods are protected by a reentrant `threading.Lock()` guaranteeing exactly one concurrent entry.

## Executed Tests and Real Results
- **Command**: `PYTHONPATH=. pytest tests/test_sync_service.py -v && PYTHONPATH=. pytest tests/test_worker_020.py -v`
- **Date/Time**: 2026-09-17 10:42:16 UTC-05:00
- **Result**: `tests/test_sync_service.py` 15 passed in 0.74s, `tests/test_worker_020.py` 24 passed in 0.21s. Total 39/39 passing. 0 fails, 0 errors.
- **Features Covered**: atomic concurrency, async start, concurrent start, polling, stage, activate fail-closed, rollback, invalid transitions, HTTP contracts, unsupported executor (fail-closed), missing local model (fail-closed, `UNAVAILABLE`), no mock fallback, telemetry.

## Legacy Cleanups
### Legacy Removed (`REMOVE`)
- Removed `ACTIVATED` from `SyncState` in `runtime/sync/models.py`. The contract is explicitly blocked at `ACTIVATING`.
- Removed `qwen_mock.json` fallback in `worker.py`. Missing local model properly yields unavailable/blocked.
- Removed generic `NotImplementedError` in `WorkerManager._process_task()`. It now deterministic fails with `ExecutionStatus.FAILED` and `FailureReason.UNSUPPORTED_EXECUTOR`, emitting telemetry properly.

### Legacy Retained
- None.

### Blockers
- None.
