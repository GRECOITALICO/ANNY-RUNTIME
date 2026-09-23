# Update and Sync Lifecycle Status

Status: implementation-boundary record — not release, activation, or certification evidence.

## Effective lifecycle

```text
DISCOVER -> VERIFY -> REPORT
                   \-> STAGE (BLOCKED: STAGING_NOT_IMPLEMENTED)
                   \-> APPLY (BLOCKED: APPLY_REQUIRES_PHYSICAL_STAGE)
                   \-> ROLLBACK (BLOCKED: ROLLBACK_REQUIRES_PHYSICAL_APPLY)
```

`SyncService` has one persisted logical transaction record. `UpdateManager` is
a separate quarantined legacy/update surface; its public lifecycle methods
raise `UpdateNotImplementedError` and report `NOT_IMPLEMENTED`. Neither
component establishes a physical update lifecycle.

## Update check

`POST /admin/update-check` delegates to `SyncService.update_check()`. It is a
discovery-and-verification operation only and returns one of:

- `UPDATE_SOURCE_UNAVAILABLE`
- `UPDATE_METADATA_INVALID`
- `UPDATE_NOT_AVAILABLE`
- `UPDATE_AVAILABLE`
- `UPDATE_VERIFICATION_UNAVAILABLE`

`UPDATE_AVAILABLE` requires a `RUNTIME_RELEASE` candidate and strict release
identity verification. A different filename or version alone is only a
discovered candidate and does not establish a newer, stageable, or applicable
release.

The currently wired Runtime has no canonical external update authority or
verifier. Its update check therefore reports source unavailability; it does
not treat GitHub release metadata, local Git, package version, or a local
artifact as an update authority.

## Physical-operation boundary

No physical stage location, target transition, prior-state restore, locking
lease, apply receipt, or rollback receipt exists. The persisted operation
records contain correlation and candidate fields so a future authorized
implementation can be traced, but they do not claim that a physical operation
occurred.

In particular, no `APPLY_FAILED`, `ROLLBACK_FAILURE`, `ROLLED_BACK`, or
`VERIFIED_ACTIVE` result is emitted without a physical operation and its
verification evidence.
