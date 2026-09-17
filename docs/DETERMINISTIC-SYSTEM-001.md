# ANNY Runtime — Deterministic System 001

Status: IMPLEMENTED_NOT_VERIFIED

## 1. Purpose

ANNY Runtime must treat deterministic execution as a first-class execution plane.

The purpose is not to assume that a large percentage of agentic work is deterministic. The purpose is to make that hypothesis measurable by routing every eligible task through governed Runtime capabilities and recording what actually happened.

The Runtime therefore separates three processing planes:

- `DETERMINISTIC` — governed local execution with no model inference;
- `LOCAL_MODEL` — inference executed by a locally available model;
- `FRONTIER_MODEL` — inference executed by a remote/frontier model.

A missing or contradictory routing provenance is `UNKNOWN` and must not be silently classified.

## 2. Core thesis

A significant class of work performed by agentic harnesses consists of operations whose result can be obtained by bounded computation against explicit inputs and policies rather than by generating or interpreting novel model output.

Examples include repository inspection, file listing, hashing, repository search, reading known content, diff generation, metadata extraction and schema/policy checks when those capabilities are explicitly declared deterministic.

This is an engineering hypothesis until measured on real Runtime traffic.

The Runtime exists to measure:

```text
work received
    -> capability identified
    -> policy evaluated
    -> execution plane selected
    -> actual executor run
    -> result/evidence produced
    -> telemetry recorded
```

The resulting evidence can answer, per department/project/repository/capability family, how much work was:

```text
ROUTED_DETERMINISTIC
EXECUTED_DETERMINISTIC
SUCCEEDED_DETERMINISTIC
ROUTED_LOCAL_MODEL
EXECUTED_LOCAL_MODEL
ROUTED_FRONTIER_MODEL
```

## 3. Deterministic processing contract

A capability can be classified as deterministic only when its behavior is governed by an explicit Runtime capability definition and its execution does not require model inference.

The capability definition records, at minimum:

- capability identity;
- capability family;
- execution mode/routing class;
- side-effect class;
- cache eligibility;
- hermeticity classification;
- filesystem/network policy;
- evidence requirement;
- enablement state.

Read-oriented deterministic capabilities must not gain write authority implicitly.

A disabled capability remains disabled even if an executor implementation exists.

## 4. Current deterministic capability boundary

The currently documented executable deterministic subset is:

- `filesystem.inspect`
- `filesystem.list`
- `filesystem.hash`
- `repository.inspect`
- `repository.search`
- `repository.read`
- `repository.diff`
- `artifact.metadata`

The registry also contains governed capability definitions for additional deterministic-oriented paths such as `schema.validate` and `fabric.read`; their presence in the registry must not be interpreted as proof that a full production execution path is already verified.

`fabric.register` is intentionally disabled because deterministic write effects require an explicit governed write executor and authority boundary.

Capability counts in design documents are taxonomy/design counts, not claims about currently implemented executable capabilities.

## 5. Deterministic execution pipeline

The intended Runtime path is:

```text
Task
  |
  v
Capability lookup
  |
  v
Policy evaluation
  |
  v
Executor selection
  |
  +-------------------+-------------------+
  |                   |                   |
  v                   v                   v
DETERMINISTIC     LOCAL_MODEL       FRONTIER_MODEL
  |                   |                   |
  v                   v                   v
Deterministic      Local inference    Remote inference
executor           executor           executor
  |                   |                   |
  +-------------------+-------------------+
                      |
                      v
                 Result/evidence
                      |
                      v
              Telemetry / audit
```

`DETERMINISTIC` is not equivalent to `LOCAL_MODEL`. Both may use local compute, but only the deterministic plane excludes inference by design.

## 6. Execution identity

Every processed task must preserve enough identity for reconstruction:

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
- `trace_id`
- `status`
- `duration_ms`
- `input_hash` where applicable
- `result_hash` where applicable
- evidence/result references where produced

No field may be invented by the dashboard. Missing provenance remains missing/unknown.

## 7. Department attribution

Department is execution provenance, not UI decoration.

The expected propagation path is:

```text
Task.department_id
    -> TaskExecutionContext.department_id
    -> Worker.department_id
    -> telemetry/audit department_id
    -> Processing Matrix
```

The Runtime must not infer a department from capability name, capability family, project name or model intent.

When source provenance is absent:

```text
department_id = UNKNOWN
```

This keeps department metrics auditable.

## 8. Workspace and isolation

The deterministic plane uses a Runtime-managed ephemeral workspace and bounded execution policies.

Current verified design constraints include:

- bounded deadline;
- bounded output size;
- bounded workspace size;
- network disabled by default for deterministic local capabilities;
- forbidden sensitive host paths;
- evidence and reproducibility records for deterministic execution;
- explicit filesystem policy per capability.

The current implementation must not be described as a complete hermetic sandbox. Stronger process isolation, resource isolation and broader host-boundary enforcement remain future work.

## 9. Evidence model

A deterministic execution is not considered proven merely because routing selected `DETERMINISTIC`.

Evidence should connect:

```text
input
 -> execution identity
 -> capability
 -> executor
 -> policy
 -> result
 -> evidence
 -> telemetry
```

The Runtime deterministic executor already produces result, observability, reproducibility and evidence records for its execution path. Current repository verification of that full chain remains pending until the focused suite and runtime boundary tests are executed against the current source tree.

## 10. Observability model

The canonical telemetry vocabulary is:

```text
ROUTED_DETERMINISTIC
EXECUTED_DETERMINISTIC
SUCCEEDED_DETERMINISTIC
ROUTED_LOCAL_MODEL
EXECUTED_LOCAL_MODEL
ROUTED_FRONTIER_MODEL
```

The durable Processing Matrix must be computed from actual execution telemetry/audit records.

Required aggregate dimensions:

- department;
- routing class;
- capability family;
- capability;
- project;
- repository;
- worker;
- status.

Required outcome dimensions:

- total executions;
- deterministic executions;
- local-model executions;
- frontier-model executions;
- unknown executions;
- success;
- failure;
- timeout;
- blocked;
- latest execution;
- latency when enough observations exist.

No metric should be presented as a ratio without a clearly defined denominator.

## 11. Processing Matrix

The intended Control Center view is:

| Department | Total | Deterministic | Local Model | Frontier Model | Success | Failed | Timeout | Blocked | Latest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| derived from telemetry | derived | derived | derived | derived | derived | derived | derived | derived | derived |

The view must support drill-down from:

```text
Department
 -> processing plane
 -> capability family
 -> capability
 -> execution
 -> trace
 -> evidence/result
```

Filters must be read-only and must not alter execution policy.

## 12. Model usage boundary

The deterministic plane is an optimization boundary for work that does not require inference.

The local-model plane is for tasks that require inference but can be satisfied by a locally available model.

The frontier-model plane is for tasks whose executor is a remote/frontier model.

The Runtime must never route to a model simply because deterministic capability coverage is inconvenient. Conversely, deterministic routing must not be forced when capability semantics require inference.

Routing must follow declared capability and policy.

## 13. Candidate deterministic capability families

The wider deterministic taxonomy can be organized into families for future implementation and measurement:

1. filesystem and paths;
2. metadata and inspection;
3. text and encoding transforms;
4. structured data parsing;
5. archives/compression;
6. hashing/integrity;
7. Git/repository operations;
8. diff/patch/reconciliation;
9. static code analysis;
10. build/compile/package operations;
11. tests and quality checks;
12. dependency inspection;
13. container/image metadata;
14. process/system inspection;
15. environment/config inspection;
16. logs/telemetry processing;
17. database inspection and bounded transforms;
18. document/PDF processing;
19. multimedia metadata/transforms;
20. browser/navigation operations that are explicitly scripted and bounded;
21. HTTP/API operations that are explicitly declared and policy-bound;
22. network diagnostics;
23. scheduled jobs;
24. workspace/artifact/cache management;
25. schemas and policy validation;
26. provenance/identity verification;
27. secret metadata without secret disclosure;
28. security analysis that is deterministic and bounded;
29. OS/service inspection;
30. evidence and reproducibility generation.

This family list is a design taxonomy. It does not state that all listed families or their individual capabilities are currently implemented.

## 14. Deterministic optimization roadmap

The next layers are:

### Layer A — measurement

- canonical routing provenance;
- execution-plane telemetry;
- department aggregation;
- Processing Matrix;
- execution drill-down.

### Layer B — reproducibility

- canonical execution fingerprint;
- explicit input identity;
- explicit output identity;
- reproducibility checks;
- replay contract.

### Layer C — content-addressed reuse

- deterministic result identity;
- cache eligibility policy;
- cache hit/miss evidence;
- invalidation rules;
- safe reuse only for hermetic/cacheable capabilities.

### Layer D — dependency execution

- explicit task dependencies;
- dependency graph/DAG;
- bounded concurrency;
- retry policy;
- partial-failure semantics;
- deterministic recovery.

### Layer E — stronger isolation

- process isolation;
- resource quotas;
- stronger host boundary enforcement;
- network policy enforcement;
- hermeticity verification.

No later layer is considered implemented merely because its design exists.

## 15. Fail-closed rules

The deterministic subsystem must fail closed when:

- capability is unknown;
- capability is disabled;
- policy is missing or contradictory;
- write effect lacks explicit authority;
- required evidence cannot be produced;
- required routing provenance is contradictory;
- execution exceeds deadline/size/resource limits;
- telemetry attempts to persist secrets;
- replay/cache identity cannot be proven.

## 16. Research-derived engineering patterns

ANNY may adopt general technical patterns such as:

- hermetic/reproducible execution;
- explicit inputs and dependencies;
- content-addressed artifacts;
- local execution history;
- declarative dependency graphs;
- bounded retries;
- concurrency controls;
- artifact/result retention;
- replay and cache verification.

These are engineering patterns, not imported product semantics. ANNY retains its own authority, tenancy, workspace, capability, evidence and fail-closed contracts.

## 17. Verification status

Current status:

```text
DETERMINISTIC-EXECUTION-SUBSTRATE-001 = VERIFIED
DETERMINISTIC-OBSERVABILITY-001       = VERIFIED
```

This document is therefore a durable implementation contract and reconstruction aid, not a certification.

Verification requires current focused test execution and evidence for:

- deterministic capability execution;
- routing classification;
- local-model classification;
- frontier-model classification where an actual executor exists;
- department propagation;
- aggregation correctness;
- telemetry scrubbing;
- HTTP/browser display of actual telemetry;
- deterministic evidence/result traceability.

## 18. Required future claims discipline

The Runtime may claim only what its evidence supports.

Allowed:

- “N deterministic executions were recorded.”
- “M executions were routed to the local-model plane.”
- “K executions were routed to the frontier-model plane.”
- “X% of completed executions in dataset Y succeeded deterministically,” when denominator and dataset are explicit.

Not allowed without supporting evidence:

- “most agentic work is deterministic”;
- “ANNY solves work deterministically”;
- “the Runtime eliminates model usage”;
- “all deterministic capabilities are implemented”;
- “the deterministic plane is fully hermetic.”

Those statements require measured evidence and a precisely defined population.
