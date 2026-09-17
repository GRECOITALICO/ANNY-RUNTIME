# ANNY Runtime — SYNC-IMPLEMENTATION-001-A

Status: IMPLEMENTED_NOT_VERIFIED

## Scope

First governed SYNC core, deliberately fail-closed and separate from Stage/Activate.

## Evidence

- `runtime/sync/__init__.py`
- `runtime/sync/models.py`
- `runtime/sync/service.py`
- `tests/test_sync_service.py`

## Commit anchors

- package: `a88371083e79129ecdf5e4c7c64febd55fbdc340`
- models: `c5d8e8babcaba0f9a552deb7239a7eccf7daf8e2`
- service: `4bd544756ea04c89f3a2dc2889bb2e63e632be8a`
- tests: `afe108713998f4a4967d4d092584d1360a19d559`

## Implemented semantics

1. Every Sync receives a durable `sync_id` and `trace_id`.
2. Records are persisted to `sync/sync_records.jsonl`.
3. Missing authoritative discovery is `BLOCKED`.
4. Missing authority evidence is `BLOCKED`.
5. Candidate without a verifier is `UNKNOWN`.
6. Failed verification is `BLOCKED`.
7. No-change with verified authority is `VERIFIED`.
8. Sync-only execution never activates a runtime.

## Test intent

The added tests cover:

- fail-closed behavior when no authority exists;
- verified no-change behavior;
- candidate discovery without a verifier;
- verified candidate without activation.

A local smoke check also confirmed durable fail-closed record creation. This is not a substitute for the repository's complete test suite or CI.

## NOT YET VERIFIED

The following remain open:

- `POST /api/sync` integration in `AdminRouter`;
- `GET /api/sync/status` integration;
- first-level Control Center SYNC control;
- live browser polling of Sync state;
- authoritative production update source discovery;
- candidate artifact verification implementation;
- stage/activation/rollback integration;
- complete repository test-suite result.

## Next action

`SYNC-IMPLEMENTATION-001-B`: wire the governed Sync core into the Runtime Admin API and primary Control Center, preserving `SYNC != STAGE != ACTIVATE`.
