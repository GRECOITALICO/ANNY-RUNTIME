# ANNY Runtime

The ANNY Runtime is the physical local execution environment for the ANNY autonomous system.

## The Experience

```text
install ANNY Runtime once
↓
connect GitHub
↓
Runtime starts with OS
↓
open ChatGPT or Claude
↓
connect same GitHub
↓
"inicia bootstrap como ANNY"
↓
"inicia bootstrap como KIRA"
↓
ANNY uses local Runtime for execution
```

## Architecture

This is NOT another autonomous agent wrapper (like OpenHands or Aider). This is a foundational capability execution gateway:

```text
ANNY (Cloud DTO)
    ↓
ANNY Runtime Protocol (v0.1)
    ↓
ANNY Runtime (Local)
    ↓
ANNY-owned execution paths
    ↓
OS (Linux / WSL2)
```

It is permanently resident on your machine (via systemd), strictly scoped by Tenant/Workspace, and completely independent of any specific AI model provider.

## Deterministic execution is a first-class Runtime plane

ANNY Runtime does not assume that most agentic work is deterministic. It makes that proposition measurable.

Every eligible task is intended to resolve through one of three execution planes:

```text
                    TASK
                      ↓
             CAPABILITY + POLICY
                      ↓
                 EXECUTOR
                      ↓
       ┌──────────────┼──────────────┐
       ↓              ↓              ↓
DETERMINISTIC    LOCAL_MODEL    FRONTIER_MODEL
       ↓              ↓              ↓
 governed local   local model    remote model
 execution        inference      inference
       └──────────────┼──────────────┘
                      ↓
              RESULT / EVIDENCE
                      ↓
               TELEMETRY / AUDIT
```

`DETERMINISTIC` means governed execution without model inference.

`LOCAL_MODEL` means inference executed by a locally available model.

`FRONTIER_MODEL` means inference executed by a remote/frontier model.

Missing or contradictory provenance remains `UNKNOWN`; Runtime and Control Center must not silently invent a classification.

### Why the deterministic plane exists

Many operations commonly surrounding model-driven work are bounded transformations or inspections whose result can be derived from explicit inputs and policies. Examples in the current documented Runtime boundary include repository inspection, filesystem inspection/listing, hashing, repository search/read/diff and artifact metadata extraction.

The important distinction is between **routing** and **successful deterministic execution**. ANNY records what actually executed and what evidence was produced rather than treating capability intent as proof.

### Current documented deterministic executable subset

- `filesystem.inspect`
- `filesystem.list`
- `filesystem.hash`
- `repository.inspect`
- `repository.search`
- `repository.read`
- `repository.diff`
- `artifact.metadata`

The registry can contain additional governed definitions that are not yet proof of verified executable coverage. Write-effect capabilities do not gain deterministic authority implicitly.

### Deterministic observability

The Runtime is designed to make processing visible by department, project, repository and capability family. The target Processing Matrix is derived from execution telemetry/audit records rather than model narrative:

```text
DEPARTMENT
  → TOTAL
  → DETERMINISTIC
  → LOCAL MODEL
  → FRONTIER MODEL
  → UNKNOWN
  → SUCCESS
  → FAILURE
  → TIMEOUT
  → BLOCKED
  → LAST EXECUTIONS
```

A deterministic execution is traceable through task, execution, capability, executor, policy, workspace, result/evidence and telemetry identifiers.

The complete durable design is documented in:

- `docs/DETERMINISTIC-SYSTEM-001.md`
- `docs/DETERMINISTIC-EXECUTION-STRATEGY-001.md`
- `docs/DETERMINISTIC-PROCESSING-OBSERVABILITY-001.md`

### Current verification boundary

```text
DETERMINISTIC-EXECUTION-SUBSTRATE-001 = VERIFIED
DETERMINISTIC-OBSERVABILITY-001       = VERIFIED
DETERMINISTIC-SYSTEM-001              = VERIFIED
```

Current documentation is an implementation/reconstruction contract, fully verified against runtime boundary evidence. Claims about the percentage of agentic work that is deterministic require an explicit telemetry population, denominator and current execution evidence.

### Future deterministic layers

The deterministic roadmap includes, in sequence:

1. measurement and Processing Matrix;
2. canonical execution fingerprints and reproducibility;
3. content-addressed deterministic results and cache eligibility;
4. replay/idempotency;
5. dependency graphs and bounded concurrency/retries;
6. stronger process/resource/network isolation;
7. durable cache-hit/replay evidence.

These layers are not considered implemented merely because they are documented.
