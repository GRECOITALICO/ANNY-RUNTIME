# ANNY Runtime — Deterministic Execution Strategy 001

Status: IMPLEMENTED_NOT_VERIFIED

This document defines the implementation strategy for the deterministic execution substrate. The consolidated system-level contract is maintained in:

`docs/DETERMINISTIC-SYSTEM-001.md`

That document is the primary reconstruction/reference document for the complete deterministic topic, including execution planes, capability boundaries, telemetry, department attribution, evidence, workspace constraints, future cache/DAG layers, fail-closed rules and claims discipline.

## Purpose

Define the local deterministic execution substrate so ANNY can process repeatable, bounded, evidence-producing tasks without requiring model inference for every operation.

## Current implementation boundary

The Runtime currently exposes deterministic capability metadata through `CapabilityRegistry` and executes a bounded subset through `DeterministicExecutor`.

Current executable local capabilities after this milestone:

- `filesystem.inspect`
- `filesystem.list`
- `filesystem.hash`
- `repository.inspect`
- `repository.search`
- `repository.read`
- `repository.diff`
- `artifact.metadata`

The registry also contains governed definitions such as `schema.validate` and `fabric.read`; registry presence is not equivalent to verified executable coverage.

`fabric.register` remains disabled because deterministic write effects require a separate governed write executor.

## Design principles

1. Same declared input + same policy + same tool/runtime version should produce a reproducible execution identity whenever the capability is marked hermetic.
2. Deterministic read capabilities must not require model inference.
3. Network access is disabled by default for the deterministic local plane.
4. Workspace execution is bounded by deadline, output size and workspace size.
5. Every deterministic execution produces result, observability, reproducibility and evidence records on its implemented path.
6. Write-effect capabilities are not implicitly upgraded into read-only deterministic capabilities.
7. Capability identity must be separated from executor implementation.
8. Deterministic coverage is a measurable execution property, not a narrative claim about all agentic work.

## Workspace contract

The deterministic execution path uses a Runtime-managed ephemeral workspace with bounded execution policy. Stronger hermetic process/resource isolation remains future work and must not be claimed as complete before verification.

## External technical research

The implementation direction uses general engineering patterns studied in open-source systems: reproducibility, explicit inputs, isolation, content identity, local execution history, dependency graphs, retries, concurrency and reusable artifacts.

These patterns are engineering references only. External product names and product-specific semantics are not part of the ANNY Runtime architecture or capability taxonomy.

## Next technical layer

The next deterministic-substrate layers are:

1. canonical execution fingerprint;
2. content-addressed input/output identity;
3. deterministic result cache;
4. replay/idempotency contract;
5. dependency graph/DAG model;
6. bounded retry policy;
7. stronger sandbox boundary;
8. capability family inventory;
9. focused execution tests;
10. durable cache/replay evidence.

Before expanding these layers, current deterministic and observability evidence must be executed and reconciled.

## Verification boundary

This document records implementation direction and current source evidence. It does not claim current repository-wide test execution, end-to-end verification or certification.

The authoritative current state is maintained in the milestone ledger and the consolidated deterministic system document.
