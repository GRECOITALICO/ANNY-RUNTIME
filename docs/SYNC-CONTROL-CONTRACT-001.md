# ANNY Runtime — SYNC Control Contract 001

Status: P0 / REQUIRED / IMPLEMENTATION CONTRACT
Owner: ANNY Runtime
Authority: ANNY / DTO

## Purpose

`SYNC` is a first-class Control Center operation. It is not a cosmetic refresh, not an alias for `VERIFY NOW`, and not an implicit activation mechanism.

The purpose of `SYNC NOW` is to reconcile the local Runtime against its configured authoritative sources, perform governed discovery/comparison/verification, publish the resulting state, and leave a durable trace/evidence record.

## Non-negotiable semantics

- `SYNC != VERIFY` even though the verification engine may be one stage inside the sync pipeline.
- `SYNC != STAGE`.
- `SYNC != ACTIVATE`.
- `SYNC != AUTO ACTIVATE`.
- A successful sync never implies that a new Runtime version was activated.
- A failed or incomplete sync must be represented as `FAILED`, `BLOCKED`, or `UNKNOWN`; never silently mapped to success.
- Missing authority/source evidence must remain `UNKNOWN` or `BLOCKED`.

## Canonical pipeline

```text
REQUEST SYNC
    -> DISCOVER
    -> COMPARE
    -> VERIFY
    -> REPORT
    -> [STAGE]
    -> [ACTIVATE]
    -> HEALTH
    -> CERTIFY
```

The base `SYNC NOW` operation stops after `REPORT` unless a separately authorized stage/activation action is explicitly requested. Automatic update policy may invoke the same sync contract, but sync alone must not activate anything.

## Control Center requirements

The primary Control Center header must expose a visible `SYNC` control. It must not be hidden under Settings, an overflow menu, or an updater-only page.

Required visible state values:

- `IDLE`
- `SYNCING`
- `VERIFIED`
- `BLOCKED`
- `FAILED`
- `UNKNOWN`

Required visible telemetry:

- last sync timestamp;
- current sync state;
- authoritative source identity;
- local Runtime identity/version;
- candidate/latest verified version when available;
- sync progress/current stage;
- resulting trace identifier;
- resulting evidence identifier when available;
- explicit distinction between sync, staging and activation.

Required actions exposed by the Control Center as capability/authority permits:

- `SYNC NOW`
- `VIEW SYNC TRACE`
- `VIEW EVIDENCE`
- `VIEW CANDIDATE`
- `STAGE`
- `ACTIVATE`
- `ROLLBACK`

## API contract

The implementation should expose:

- `POST /api/sync` — initiate one governed sync transaction;
- `GET /api/sync/status` — return sanitized current sync state and latest durable result.

The existing `/admin/update-check` endpoint must not be treated as the canonical Sync API merely because it exists.

### POST /api/sync

The response must acknowledge that the transaction was requested and return a correlation identifier or trace identifier. It must not report `ACTIVE` unless an explicitly separate activation operation actually occurred.

Expected initial response states:

```json
{
  "status": "started",
  "sync_state": "SYNCING",
  "sync_id": "...",
  "trace_id": "..."
}
```

### GET /api/sync/status

The response must be sanitized and safe for browser consumption. It must include at minimum:

```json
{
  "sync_state": "IDLE",
  "last_sync_at": null,
  "source": "UNKNOWN",
  "local_version": "...",
  "candidate_version": null,
  "stage": "NONE",
  "trace_id": null,
  "evidence_id": null,
  "activation_performed": false
}
```

## Durable evidence

Every requested sync must leave a durable record containing at minimum:

- `sync_id`;
- `trace_id`;
- request timestamp;
- source/authority identity;
- local Runtime identity/version;
- discovered source revision/version;
- comparison result;
- verification result;
- final sync state;
- stage/activation flags;
- error classification when failed;
- links/IDs for trace and evidence artifacts.

No secret, token, private key, or credential may be written into the sync record.

## Auto Update integration

Auto Update is allowed to schedule or invoke `SYNC` according to policy. The GUI must show the latest and next scheduled sync when Auto Update is enabled.

The following equivalence is forbidden:

```text
AUTO UPDATE = AUTO ACTIVATE
```

The required separation is:

```text
SYNC -> discovery/reconciliation/verification/report
STAGE -> prepare a candidate
ACTIVATE -> change the active runtime version
CERTIFY -> establish post-activation health/evidence
```

## Acceptance criteria

1. `SYNC` is visibly present in the first-level Control Center interface.
2. `SYNC NOW` invokes a real governed backend operation, not a browser refresh or no-op.
3. The operation reconciles against configured authoritative sources.
4. The operation leaves durable trace/evidence data.
5. `SYNC` never silently activates a runtime update.
6. The UI distinguishes `SYNCING`, `VERIFIED`, `BLOCKED`, `FAILED`, and `UNKNOWN`.
7. Missing source/authority evidence is not inferred.
8. The existing updater stubs are not presented as functional update capability.
9. Automated tests cover successful sync, blocked sync, failed sync, idempotent repeated sync, and sync-without-activation.
10. Release evidence explicitly states whether Sync is `IMPLEMENTED`, `TESTED`, `LIVE`, and `EVIDENCED`.

## Current implementation gap

As of the current `main` branch, the Runtime contains an `UpdateManager`, but its check/download/verify/stage/activate/rollback methods are stubbed. The admin `/admin/update-check` handler records an audit event and redirects. The current Control Center exposes `VERIFY NOW`, which invokes bootstrap verification. Therefore the required first-class governed `SYNC` path is not yet established by these components.
