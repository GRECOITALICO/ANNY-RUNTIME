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
10. `docs/DETERMINISTIC-SYSTEM-001.md`
11. `docs/DETERMINISTIC-EXECUTION-STRATEGY-001.md`
12. `docs/DETERMINISTIC-PROCESSING-OBSERVABILITY-001.md`
13. relevant evidence records under `docs/evidence/`

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
9. inspect deterministic execution substrate state
10. inspect current processing-plane telemetry state
11. run required tests when execution is available
12. report blockers
13. only then continue
```

## Historical anchors

Deterministic bootstrap milestone:

`a9771d11e3bf49fb1170a8a1140fc9887ac6e97a`

Live Control Center milestone:

`64f1336061c1d44c4bec53c68fce36546be07ca9`

SYNC contract milestone:

`f1043b322bf33b88587e2a68131e658e774e6688`

## Current deterministic documentation anchors

System-level deterministic contract:

`docs/DETERMINISTIC-SYSTEM-001.md`

Deterministic execution strategy:

`docs/DETERMINISTIC-EXECUTION-STRATEGY-001.md`

Processing-plane and department observability:

`docs/DETERMINISTIC-PROCESSING-OBSERVABILITY-001.md`

The consolidated deterministic documentation defines the deterministic execution thesis, capability boundary, three execution planes, department provenance, workspace/security boundaries, evidence requirements, telemetry vocabulary, Processing Matrix, capability-family taxonomy, future cache/replay/DAG/sandbox layers, and claims discipline.

## Current documentation anchors

README deterministic system section:

`327090b4f18366733c75159b119bc5b7373bbdfd`

Deterministic system documentation milestone:

`434a7a031b5387999ff7ddc2c1b25b8b238a1d21`

Latest deterministic observability/documentation support:

`96f2ff658deb7566b7f328894353282c77798c4e`

## Current deterministic execution anchor

Governed local deterministic execution substrate:

`bb26f74a3b4588af3ba4fd4e2deaed721415e50e`

Supporting implementation commits include:

- `a0ac78e49069ee922f399b91050432189750b76f`
- `855d38f8661e33d6be42a3e153414a7e3ad8afa9`
- `55d9c6230f6a3862972c4058a427c10fd278bf46`
- `7d059d09597f15f581f1153b55af5a9968599ceb`
- `7934e135c148cb13544cbdaabfa84bd3e0ddc61c`
- `e572e0c26004bdee4e473f8561da0bf55cd6ab25`
- `9edef80cfcf8c3c203a107ffbd22a28852f6e595`

## Deterministic system state

Current status:

```text
DETERMINISTIC-EXECUTION-SUBSTRATE-001 = IMPLEMENTED_NOT_VERIFIED
DETERMINISTIC-OBSERVABILITY-001       = IMPLEMENTED_NOT_VERIFIED
DETERMINISTIC-SYSTEM-001              = IMPLEMENTED_NOT_VERIFIED
```

The system supports an explicitly governed deterministic execution subset and carries routing/department classification through execution data structures. Verification remains pending until current focused tests and runtime-boundary evidence are executed and reconciled.

Do not interpret design taxonomy counts as implemented capability counts.
Do not interpret registry presence as verified executable coverage.
Do not interpret routing as successful execution.
Do not interpret documentation as certification.

## Deterministic execution planes

```text
TASK
  -> CAPABILITY
  -> POLICY
  -> EXECUTOR
  -> ROUTING CLASS
       DETERMINISTIC
       LOCAL_MODEL
       FRONTIER_MODEL
       UNKNOWN
  -> EXECUTION
  -> RESULT/EVIDENCE
  -> TELEMETRY
```

`DETERMINISTIC` means governed execution without model inference.

`LOCAL_MODEL` means inference performed by a local model.

`FRONTIER_MODEL` means inference performed by a remote/frontier model.

`UNKNOWN` means the provenance is missing or contradictory.

## Current documented deterministic executable subset

- `filesystem.inspect`
- `filesystem.list`
- `filesystem.hash`
- `repository.inspect`
- `repository.search`
- `repository.read`
- `repository.diff`
- `artifact.metadata`

Additional registry definitions may exist without constituting verified runtime coverage.

## Deterministic observability

Every processing record should preserve, where applicable:

```text
task_id
execution_id
department_id
project_id
repository_id
capability_id
capability_family
routing_class
executor_type
executor_id
model_id/model_version
policy_version
workspace_id
trace_id
status
duration_ms
input_hash
result_hash
evidence/result references
```

Department must propagate from source task through execution context and worker into telemetry/audit. Missing department stays `UNKNOWN` and is never inferred from capability family or naming.

The target Processing Matrix is:

```text
DEPARTMENT
  -> TOTAL
  -> DETERMINISTIC
  -> LOCAL MODEL
  -> FRONTIER MODEL
  -> UNKNOWN
  -> SUCCESS
  -> FAILURE
  -> TIMEOUT
  -> BLOCKED
  -> LAST EXECUTIONS
```

All values must originate from actual telemetry/audit records.

## Deterministic-first measurement

The Runtime is being built to measure how much real execution can be completed without inference.

This is a measurable engineering hypothesis, not a pre-existing fact.

Canonical vocabulary:

- `ROUTED_DETERMINISTIC`
- `EXECUTED_DETERMINISTIC`
- `SUCCEEDED_DETERMINISTIC`
- `ROUTED_LOCAL_MODEL`
- `EXECUTED_LOCAL_MODEL`
- `ROUTED_FRONTIER_MODEL`

A deterministic success requires an actual execution result/evidence record; routing alone is insufficient.

## Current Sync implementation anchors

Governed Sync core:

`4bd544756ea04c89f3a2dc2889bb2e63e632be8a`

Canonical API integration:

`8ba195044e2593cf144576bdb71b364dc81b7e7b`

Control Center Sync surface:

`6242aa8995b6cf6862376b37d1286d3a5e9750f6`

Configured GitHub release discovery:

`fead26357e279daea1c6256a8675d6101afd005a`

Candidate integrity verification:

The durable reconstruction supplied for SYNC-E identifies:

- `5efd8c04d5c70867df0e9291c60d52f7f334279c` — implementation
- `b87a36d56032314ca474cbd1f31e1d96ffddded1` — focused candidate integrity tests
- `dbdd8e84e409b730fbcd4ca1933db6daccdf6489` — evidence document
- `88b5a55908c454233fe4aea4e5257d6bc479ed6c` — milestone ledger update
- `e4c576d80a1482fccd5ed47177ef39e3457d2d40` — reconstruction card update reported for that checkpoint

Focused SYNC-E suite reported:

`10 passed in 0.12s`

Current verification boundary for E remains:

```text
IMPLEMENTED_NOT_VERIFIED
```

because end-to-end HTTP/browser verification remains pending and the broader repository suite lacks the required `mcp` environment dependency.

## Current P0 next action

`DETERMINISTIC-EXECUTION-SUBSTRATE-001-VERIFY`

Execute and verify deterministic processing plus routing/department observability tests before expanding the deterministic execution substrate further.

Required outputs:

- current focused test results;
- deterministic routing evidence;
- local-model routing evidence;
- frontier-model routing evidence where available;
- department aggregation evidence;
- no-secret telemetry evidence;
- Processing Matrix HTTP/browser evidence.

After deterministic verification, return to:

`SYNC-IMPLEMENTATION-001-F`

## Current known gaps

- End-to-end HTTP/browser verification for Sync and the Processing Matrix is not established.
- Current focused deterministic test execution has not yet been established from this reconstruction pass.
- `runtime/updater/manager.py` operational methods remain stubs where applicable.
- The deterministic workspace must not be described as a complete hermetic sandbox; process/resource isolation remains incomplete.
- Content-addressed cache, replay/idempotency and DAG scheduling are design/future layers until implemented and verified.
- Frontier execution must not be represented as actual activity unless a real frontier executor event exists.
- No percentage claim about deterministic workload is valid until a real telemetry population and denominator are defined.

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
DETERMINISTIC_SUBSTRATE:
PROCESSING_MATRIX:
BLOCKERS:
NEXT_ACTION:
RESUME_CONDITIONS:
```

If `LAST_VERIFIED_MILESTONE` or `NEXT_ACTION` cannot be proven, stop and reconcile.
