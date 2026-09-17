# SYNC-IMPLEMENTATION-001-B — Evidence

Date: 2026-09-17
Repository: `GRECOITALICO/ANNY-RUNTIME`
Branch: `main`
Status: `IMPLEMENTED_NOT_VERIFIED`

## Implemented

The canonical authenticated admin server now recognizes:

- `POST /api/sync`
- `GET /api/sync/status`

Both paths execute after the existing authentication and POST-body/CSRF middleware. The Sync operation is therefore not exposed as an unauthenticated side channel.

The server holds one durable `SyncService` instance and persists Sync records under the Runtime data directory.

## Safety semantics

`SyncService`:

- creates a `sync_id` and `trace_id`;
- persists an initial `SYNCING` record;
- discovers, compares and verifies through explicit providers;
- returns `BLOCKED` when no authoritative discovery provider exists;
- returns `UNKNOWN` when a candidate exists but no verifier is configured;
- never calls an activation function;
- records `activation_performed=false` for Sync-only operation;
- persists the final result as append-only JSONL.

## Test coverage added

`tests/test_sync_service.py` covers:

1. missing authority -> `BLOCKED`;
2. authorized no-change -> `VERIFIED`;
3. candidate without verifier -> `UNKNOWN`;
4. verified candidate without activation.

## Verification limitation

No GitHub Actions run was available for the API integration commit at verification time. The local execution environment also could not resolve GitHub, so this report deliberately does **not** claim current green CI or full runtime integration verification.

A separate local smoke check of the fail-closed record semantics passed, but that check was a minimal reconstruction check and is not equivalent to running the repository test suite.

## Remaining work

- wire visible first-level SYNC controls into the Control Center;
- connect authoritative source discovery;
- connect candidate verification/provenance;
- make Sync asynchronous for responsive UI progress where required;
- add full HTTP integration tests against authenticated middleware;
- only then consider `IMPLEMENTED` -> `VERIFIED`.
