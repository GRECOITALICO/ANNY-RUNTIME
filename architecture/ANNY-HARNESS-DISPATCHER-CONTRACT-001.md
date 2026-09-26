# ANNY Harness Dispatcher Contract 001

## Status and boundary

**DEFINED CONTRACT + EXECUTABLE GOVERNED DISPATCHER.** This document and
`runtime/execution/harness_contract.py` define a request validator only. They
do not dispatch a Runtime task, start a worker, issue a durable receipt, prove
ANNY first use, verify live Runtime/CONRRAD, or certify a capability.

The contract is provider-neutral. It introduces neither a second capability
registry nor an authority path: Runtime `CapabilityRegistry` remains the
implementation registry, `ExecutionContext` remains the security context, and
`ExecutionManager`/`WorkerManager` remain the future execution authority.

## Adoption position

`repository.inspect` remains at the proven **Level 1 — safe deterministic
local test** boundary. This contract is the precondition for a later governed
Harness attempt; it does not advance to Level 2, Runtime-executed, ANNY-first
use, evidence, certification, or delegation. Native fallback is unproven and
delegation is not ready.

## Request binding

`HarnessDispatchRequest` binds semantics to existing Runtime fields rather
than duplicating them:

| Required semantic | Current binding |
| --- | --- |
| request ID / replay identity | `request_id`, `idempotency_key` |
| capability / caller | `Task.capability_id`, `Task.requested_by` |
| project, input, constraints, deadline, workspace/evidence policy | existing `Task` fields |
| caller actor and level | `actor_id`, `actor_level`, compared with `ExecutionContext.actor_id` |
| execution context identity | `execution_context_id` = `ExecutionContext.execution_id` |
| workspace identity | `workspace_id` = `ExecutionContext.workspace_id` |
| source snapshot | `source_snapshot_id` (required; Runtime Task has no equivalent field) |
| authorization | `authorization_scope` plus `ExecutionContext.capabilities` |
| timeout | `timeout_seconds`, in addition to the existing Task deadline |
| receipt/evidence promise | `ReceiptContractSlot` |

The minimum request is accepted only for future handoff. It does not create a
`TaskExecutionContext`; `ExecutionManager.submit_task` remains responsible for
that later transition.

## Fail-closed dispatch decision

The only outcomes are `ACCEPTED`, `REJECTED`, `BLOCKED`, and `UNSUPPORTED`.
No decision may silently select another executor.

| Condition | Decision | Reason |
| --- | --- | --- |
| unknown capability | REJECTED | `UNKNOWN_CAPABILITY` |
| missing authorization | REJECTED | `MISSING_AUTHORIZATION` |
| missing execution context | REJECTED | `MISSING_EXECUTION_CONTEXT` |
| actor/project/context capability mismatch | REJECTED | `CONTEXT_CAPABILITY_MISMATCH` |
| workspace mismatch | REJECTED | `WORKSPACE_BINDING_FAILURE` |
| empty/invalid input or timeout | REJECTED | `INVALID_INPUT` |
| replay | REJECTED | `REPLAY_CONFLICT` |
| stale/missing source snapshot | BLOCKED | `STALE_SOURCE_SNAPSHOT` |
| executor unavailable | BLOCKED | `EXECUTOR_UNAVAILABLE` |
| required evidence lacks receipt/hash contract slot | BLOCKED | `EVIDENCE_POLICY_UNSATISFIED` |

Unsupported behavior must use `UNSUPPORTED` with `UNSUPPORTED_CAPABILITY`; it
must never be converted to a fallback route.

## Future execution handoff

After validation, the executable dispatcher may submit the bound Task to the existing `ExecutionManager`; `WorkerManager` remains responsible for worker selection and execution:

- `TaskExecutionContext.execution_id`;
- `WorkerDefinition.worker_id` and `executor_id`;
- capability, workspace, source snapshot, routing class, and authorization
  decision.

The contract does not prescribe a new worker-ID format. `WorkerManager` owns
the existing `wrk-<uuid-prefix>` generation.

## Result and receipt boundary

`HarnessResultEnvelope` represents the future result shape: execution status,
capability result, validation status, evidence reference/hash, failure class,
timestamps, and execution identifiers. It maps existing
`TaskExecutionContext` fields and does not reinterpret a local test as an
execution receipt.

The required future chain is:

`ANNY selects → Harness validates → context binds → Runtime dispatches → result validates → receipt emits → durable evidence stores → ANNY consumes → checkpoint`.

Batch 023 defines this chain only. A future implementation must make receipt
persistence failure terminal/non-success and cannot mark a result successful
until required evidence is durably stored.

## Failure containment

Invalid request, authorization failure, context/workspace mismatch, stale
source, unavailable executor, timeout, validation failure, receipt persistence
failure, worker mismatch, and replay conflict are terminal non-success states.
There is no partial acceptance and no direct Harness shortcut to shell,
filesystem, process, or external coding-agent APIs.

## Next implementation preconditions

Before claiming Runtime-executed or ANNY-first-use status, the dispatcher must be
actually exercised in an execution-capable Runtime environment and its receipt/evidence
must be consumed and checkpointed through the canonical control-plane path. A local
unit-test pass alone is insufficient.
