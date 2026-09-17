# ANNY Runtime — Deterministic Processing Observability 001

Status: P0 / REQUIRED DESIGN CONTRACT
Owner: ANNY Runtime

## Purpose

ANNY must make the execution split observable. Work entering the Runtime must be classifiable and traceable as:

- `DETERMINISTIC` — local governed capability execution without model inference;
- `LOCAL_MODEL` — inference performed by a locally hosted model;
- `FRONTIER_MODEL` — inference performed by a remote/frontier model.

The objective is to demonstrate, with durable evidence rather than narrative claims, how much Runtime work can be resolved by deterministic processing before model inference is required.

## Mandatory processing identity

Every task entering execution must carry or resolve:

- `task_id`
- `execution_id`
- `department_id`
- `project_id`
- `capability_id`
- `capability_family`
- `routing_class`
- `executor_type`
- `executor_id`
- `model_id` when applicable
- `policy_version`
- `workspace_id/path`
- input/result/evidence hashes when applicable
- status and duration

## Routing semantics

```text
TASK
  -> CAPABILITY LOOKUP
  -> POLICY EVALUATION
  -> EXECUTOR SELECTION
  -> ROUTING CLASS
       ├── DETERMINISTIC
       ├── LOCAL_MODEL
       └── FRONTIER_MODEL
  -> WORKER
  -> WORKSPACE
  -> RESULT
  -> EVIDENCE
  -> TELEMETRY / AUDIT
```

`DETERMINISTIC` is not synonymous with `LOCAL_MODEL`.

A local model is local compute, but still inference. Deterministic execution is a separate execution plane and must remain measurable as such.

## Department visibility

Department is an execution classification field, not a free-form display label only. The Runtime must preserve the source `department_id` through Task -> ExecutionContext -> Worker -> telemetry/audit.

The Control Center/telemetry views should support at minimum:

- total tasks by department;
- deterministic tasks by department;
- local-model tasks by department;
- frontier-model tasks by department;
- success/failure/timeout/limit counts by plane;
- capability-family distribution by department;
- average and p95 execution latency when sufficient observations exist;
- recent task/execution trace;
- evidence/result references.

## Deterministic-first measurement

The Runtime should not claim that a task was "solved deterministically" merely because it entered the deterministic plane. The evidence should show the actual executed capability, inputs, output/result, status and receipt/evidence.

The measurement vocabulary is:

- `ROUTED_DETERMINISTIC`
- `EXECUTED_DETERMINISTIC`
- `SUCCEEDED_DETERMINISTIC`
- `ROUTED_LOCAL_MODEL`
- `EXECUTED_LOCAL_MODEL`
- `ROUTED_FRONTIER_MODEL`

A future optimization ratio may be computed as:

`deterministic_successes / completed_tasks`

but this ratio is descriptive telemetry, not a claim of task quality by itself.

## Security

Telemetry must not contain secrets, tokens, private keys or raw credentials. Payloads must be scrubbed before persistence/display.

## Architecture patterns to adopt

The implementation should borrow technical patterns already proven in open-source systems:

1. hermetic/reproducible execution with isolated inputs and immutable/content-addressed results;
2. declarative DAGs with dependencies, retries, concurrency and local execution history;
3. a local Web UI that exposes run state, logs, artifacts and history.

ANNY must preserve its own capability, tenant, authority, evidence and fail-closed contracts instead of importing external project semantics or names into the product.

## Current state

The Runtime now persists routing classification and department metadata in execution contexts/workers and emits those fields through WorkerManager audit telemetry.

The deterministic substrate milestone remains `IMPLEMENTED_NOT_VERIFIED` until its focused tests are actually executed and evidence is reconciled.

## Next implementation stage

Build a read-only Processing Matrix view over the durable telemetry/audit stream, with filters for department, routing class, capability family, project and execution status.

The view must make visible, on one screen:

```text
DEPARTMENT
  -> TOTAL
  -> DETERMINISTIC
  -> LOCAL MODEL
  -> FRONTIER MODEL
  -> FAILURES
  -> TIMEOUTS
  -> LAST EXECUTIONS
```

No dashboard number may be inferred from model intent or narrative labels; it must come from execution telemetry/audit records.
