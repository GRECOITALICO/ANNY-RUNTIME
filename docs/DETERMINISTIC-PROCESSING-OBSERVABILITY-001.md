# ANNY Runtime — Deterministic Processing Observability 001

Status: P0 / REQUIRED DESIGN CONTRACT

Primary consolidated deterministic reference:

`docs/DETERMINISTIC-SYSTEM-001.md`

## Purpose

ANNY must make the execution split observable. Work entering the Runtime must be classifiable and traceable as:

- `DETERMINISTIC` — local governed capability execution without model inference;
- `LOCAL_MODEL` — inference performed by a locally hosted model;
- `FRONTIER_MODEL` — inference performed by a remote/frontier model;
- `UNKNOWN` — provenance is missing or contradictory.

The objective is to demonstrate, with durable evidence rather than narrative claims, how much Runtime work can be resolved by deterministic processing before model inference is required.

## Mandatory processing identity

Every task entering execution must carry or resolve:

- `task_id`
- `execution_id`
- `department_id`
- `project_id`
- `repository_id`
- `capability_id`
- `capability_family`
- `routing_class`
- `executor_type`
- `executor_id`
- `model_id` when applicable
- `model_version` when applicable
- `policy_version`
- `workspace_id`
- trace identity when available
- input/result/evidence hashes when applicable
- status and duration

Missing values remain missing/unknown. The dashboard must not invent provenance.

## Routing semantics

```text
TASK
  -> CAPABILITY LOOKUP
  -> POLICY EVALUATION
  -> EXECUTOR SELECTION
  -> ROUTING CLASS
       ├── DETERMINISTIC
       ├── LOCAL_MODEL
       ├── FRONTIER_MODEL
       └── UNKNOWN
  -> WORKER
  -> WORKSPACE
  -> RESULT
  -> EVIDENCE
  -> TELEMETRY / AUDIT
```

`DETERMINISTIC` is not synonymous with `LOCAL_MODEL`.

A local model is local compute, but still inference. Deterministic execution is a separate execution plane and must remain measurable as such.

## Department visibility

Department is an execution provenance field, not a free-form display label only. The Runtime must preserve the source `department_id` through:

`Task -> ExecutionContext -> Worker -> telemetry/audit`.

The Processing Matrix should support at minimum:

- total executions by department;
- deterministic executions by department;
- local-model executions by department;
- frontier-model executions by department;
- unknown executions by department;
- success/failure/timeout/blocked counts by plane;
- capability-family distribution by department;
- latency when sufficient observations exist;
- recent task/execution trace;
- evidence/result references.

## Deterministic-first measurement

The Runtime should not claim that a task was "solved deterministically" merely because it entered the deterministic plane. Evidence should show the actual executed capability, inputs, output/result, status and receipt/evidence.

The measurement vocabulary is:

- `ROUTED_DETERMINISTIC`
- `EXECUTED_DETERMINISTIC`
- `SUCCEEDED_DETERMINISTIC`
- `ROUTED_LOCAL_MODEL`
- `EXECUTED_LOCAL_MODEL`
- `ROUTED_FRONTIER_MODEL`

Any optimization ratio must define its denominator and population explicitly.

## Processing Matrix contract

The Control Center must expose a read-only matrix whose numbers are derived solely from execution telemetry/audit records.

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

Filters should support:

- department;
- routing class;
- capability family;
- capability;
- project;
- repository;
- worker;
- status;
- execution/trace identity.

Drill-down should connect:

`department -> plane -> capability -> execution -> trace -> evidence/result`.

## Evidence and security

Telemetry must not contain secrets, tokens, private keys or raw credentials. Payloads must be scrubbed before persistence/display.

A deterministic routing decision without an actual execution record must not be counted as a deterministic success.

## Current state

The Runtime carries department/routing/capability-family metadata through its execution data model and worker path, and the canonical telemetry model is being aligned to preserve the same classification.

The deterministic execution substrate and this observability milestone remain `IMPLEMENTED_NOT_VERIFIED` until the current focused tests and runtime boundary evidence are executed and reconciled.

## Future execution layers

After measurement is verified, the deterministic system may add:

- canonical execution fingerprints;
- content-addressed input/output identity;
- result cache with eligibility policy;
- replay/idempotency;
- dependency graphs/DAGs;
- bounded retries;
- stronger process/resource isolation;
- cache/replay evidence.

These are future implementation layers, not current completion claims.
