# ANNY Runtime — Reconstruction Card 001

This is the compact entrypoint for a fresh ChatGPT/Claude session after token exhaustion or context loss.

## BOOTSTRAP

```text
Repository: GRECOITALICO/ANNY-RUNTIME
Branch: main
Role: ANNY Runtime reconstruction
Mode: evidence-first / fail-closed / no assumed state
```

## First reads

1. `README.md`
2. `docs/RECONSTRUCTION-MASTER-001.md`
3. `docs/BOOTSTRAP-RECONSTRUCTION-PROTOCOL-001.md`
4. `docs/STATE-CONTINUITY-AND-EVIDENCE-001.md`
5. `docs/ARCHITECTURE-AND-CONTRACTS-001.md`
6. `docs/SYNC-CONTROL-CONTRACT-001.md`
7. `docs/MILESTONE-LEDGER-001.yaml`
8. `docs/RECOVERY-PLAYBOOK-001.md`
9. `docs/BUILD-TEST-AND-RELEASE-001.md`
10. `docs/evidence/SYNC-IMPLEMENTATION-001-A-EVIDENCE.md`
11. `docs/evidence/SYNC-IMPLEMENTATION-001-B-EVIDENCE.md`
12. `docs/evidence/SYNC-IMPLEMENTATION-001-D-EVIDENCE.md`

## Mandatory first actions

```text
1. resolve repository HEAD
2. verify branch
3. inspect current bootstrap implementation
4. reconstruct Runtime/Fabric/Tenant identity
5. reconstruct current mission/task/next action
6. identify last VERIFIED/CERTIFIED milestone
7. verify its evidence
8. inspect current Sync implementation state
9. run required tests when execution is available
10. report blockers
11. only then continue
```

## Historical anchors

Deterministic bootstrap milestone:

`a9771d11e3bf49fb1170a8a1140fc9887ac6e97a`

Live Control Center milestone:

`64f1336061c1d44c4bec53c68fce36546be07ca9`

SYNC contract milestone:

`f1043b322bf33b88587e2a68131e658e774e6688`

## Current Sync implementation anchors

Governed Sync core:

`4bd544756ea04c89f3a2dc2889bb2e63e632be8a`

Canonical API integration:

`8ba195044e2593cf144576bdb71b364dc81b7e7b`

Control Center Sync surface:

`6242aa8995b6cf6862376b37d1286d3a5e9750f6`

Configured GitHub release discovery:

`fead26357e279daea1c6256a8675d6101afd005a`

Latest milestone ledger update:

`940a2eb710faea93d9baa8bcd8fe925f9bead34c`

## Current P0 next action

`SYNC-IMPLEMENTATION-001-E`

Implement candidate verification before any Stage or Activate capability.

Required boundary:

```text
DISCOVER
   -> CANDIDATE IDENTITY
   -> CHECKSUM / SIGNATURE / PROVENANCE VERIFY
   -> EVIDENCE
   -> VERIFIED
   -> only then allow future STAGE
```

Do not confuse:

```text
SYNC
VERIFY
STAGE
ACTIVATE
AUTO UPDATE
```

They are distinct operations.

## Current known gaps

- `runtime/updater/manager.py` operational methods remain stubs.
- Candidate verification is not yet implemented.
- End-to-end HTTP/browser verification is not established.
- No current CI run is being claimed for the new Sync milestones.
- `ANNY_UPDATE_SOURCE_REPO` is optional; when absent, Sync must remain fail-closed.

## Resume answer format

A fresh session should end bootstrap with:

```yaml
RECONSTRUCTION_STATUS:
REMOTE_HEAD:
RUNTIME_IDENTITY:
TENANT_ID:
FABRIC_NODE:
CURRENT_MISSION:
CURRENT_TASK:
LAST_VERIFIED_MILESTONE:
EVIDENCE_REFS:
SYNC_STATE:
SYNC_SOURCE:
SYNC_CANDIDATE:
BLOCKERS:
NEXT_ACTION:
RESUME_CONDITIONS:
```

If `LAST_VERIFIED_MILESTONE` or `NEXT_ACTION` cannot be proven, stop and reconcile.
