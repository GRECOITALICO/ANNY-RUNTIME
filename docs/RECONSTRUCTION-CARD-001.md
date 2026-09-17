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

## Mandatory first actions

```text
1. resolve repository HEAD
2. verify branch
3. inspect current bootstrap implementation
4. reconstruct Runtime/Fabric/Tenant identity
5. reconstruct current mission/task/next action
6. identify last VERIFIED/CERTIFIED milestone
7. verify its evidence
8. run required tests
9. report blockers
10. only then continue
```

## Current known anchor

Deterministic bootstrap milestone:

`a9771d11e3bf49fb1170a8a1140fc9887ac6e97a`

Live Control Center milestone:

`64f1336061c1d44c4bec53c68fce36546be07ca9`

SYNC contract milestone:

`f1043b322bf33b88587e2a68131e658e774e6688`

Documentation checkpoint:

`0c01327f3de1aaa146c0c227b60e138ef878c79f`

## Current P0 next action

Implement real governed SYNC end-to-end.

Do not confuse:

```text
SYNC
VERIFY
STAGE
ACTIVATE
AUTO UPDATE
```

They are distinct operations.

## Current known gap

`runtime/updater/manager.py` defines the updater state machine but its operational methods are still stubs. The admin route table currently exposes bootstrap verification but not a canonical `/api/sync` route.

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
BLOCKERS:
NEXT_ACTION:
RESUME_CONDITIONS:
```

If `LAST_VERIFIED_MILESTONE` or `NEXT_ACTION` cannot be proven, stop and reconcile.
