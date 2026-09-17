# SYNC-IMPLEMENTATION-001-F — Repository Audit

Status: NOT_ESTABLISHED_ON_REMOTE_MAIN

## Audit scope

Repository:
`GRECOITALICO/ANNY-RUNTIME`

Branch:
`main`

Current remote HEAD at audit time:
`ab0d6de8dbf7c33ecd9e6549400fb5c1243d5d06`

## Claimed implementation reviewed

The supplied closeout claims:

- asynchronous `SyncService.start()`;
- explicit `STAGE`, `ACTIVATE`, `ROLLBACK` contracts;
- new Sync lifecycle states;
- new HTTP endpoints;
- Control Center lifecycle buttons;
- 14/14 Sync tests passing;
- `SYNC-IMPLEMENTATION-001-F = VERIFIED`.

## Repository findings

The current remote `main` does not contain the claimed F implementation.

`runtime/sync/models.py` still defines the SyncState set as:

- `IDLE`
- `SYNCING`
- `VERIFIED`
- `BLOCKED`
- `FAILED`
- `UNKNOWN`

No `STAGING`, `STAGED`, `ACTIVATING`, `ACTIVATED`, `ROLLING_BACK`, or `ROLLED_BACK` states are present.

`runtime/sync/service.py` still calls `_discover_compare_verify(result)` directly inside `start()` rather than launching the operation asynchronously on a background thread.

`SyncService` has no durable `stage()`, `activate()`, or `rollback()` methods in the current remote source.

`runtime/admin/routes.py` exposes the existing Sync-related routes but does not establish the claimed `POST /api/sync/stage`, `POST /api/sync/activate`, or `POST /api/sync/rollback` contracts.

`tests/test_sync_service.py` in the current remote source contains the existing candidate-verification suite with 10 test functions and does not establish the claimed 14-test asynchronous lifecycle suite.

`docs/evidence/SYNC-IMPLEMENTATION-001-F-CLOSEOUT.md` is absent from the current remote `main`.

## Important distinction

The local walkthrough claims include machine-local observations such as systemd restart and `curl` verification against `127.0.0.1:7891`. Those observations are not independently established by the current GitHub repository state and therefore are not treated as durable repository evidence.

## Current authoritative state

The prior E evidence explicitly identified SYNC-IMPLEMENTATION-001-F as the next action after candidate verification. fileciteturn309file0L2-L6

The durable milestone ledger currently retains `SYNC-IMPLEMENTATION-001-A` through `-E` as `IMPLEMENTED_NOT_VERIFIED` and its active P0 remains deterministic observability verification. fileciteturn308file0L1-L6

No VERIFIED F milestone should be inferred from the supplied local closeout text.

## Required closeout conditions

F can be considered established only after the actual implementation appears on remote `main` and the repository contains:

1. explicit Sync lifecycle states;
2. asynchronous Sync execution with concurrency protection;
3. governed `stage()`, `activate()`, and `rollback()` service contracts;
4. corresponding authenticated HTTP contracts;
5. UI state gating tied to durable Sync state;
6. current tests covering async semantics and prerequisite enforcement;
7. durable F evidence artifact;
8. updated milestone ledger with the actual implementation commit SHA;
9. current runtime-boundary verification where claimed.

Until then:

`SYNC-IMPLEMENTATION-001-F = NOT_ESTABLISHED_ON_REMOTE_MAIN`
