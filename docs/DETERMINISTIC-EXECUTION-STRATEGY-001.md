# ANNY Runtime — Deterministic Execution Strategy 001

Status: IMPLEMENTED_NOT_VERIFIED

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

`fabric.register` remains disabled because deterministic write effects require a separate governed write executor.

## Design principles

1. Same declared input + same policy + same tool/runtime version should produce a reproducible execution identity whenever the capability is marked hermetic.
2. Deterministic read capabilities must not require model inference.
3. Network access is disabled by default for the deterministic local plane.
4. Workspace execution is bounded by deadline, output size and workspace size.
5. Every execution produces result, observability, reproducibility and evidence records.
6. Write-effect capabilities are not implicitly upgraded into read-only deterministic capabilities.
7. Capability identity must be separated from executor implementation.

## Workspace contract

Each execution receives an ephemeral workspace with:

- `input/`
- `work/`
- `output/`
- `logs/`
- `evidence/`
- `result/`
- `metadata/`
- `cache/`

This provides a stable substrate for future content-addressed artifacts, retries, replay and recovery.

## External technical research

The following open-source projects were studied only as engineering references; their product names are intentionally not part of the ANNY Runtime design or public capability taxonomy.

### Research pattern A — hermetic/reproducible execution

A mature functional build system demonstrates that reproducibility improves when dependencies are explicit, the build is isolated from the host, outputs are content-addressed, and sandboxing removes hidden network/filesystem inputs. Its documentation describes isolated build processes and hash-addressed dependency trees. [Nix documentation](https://wiki.nixos.org/wiki/Nix_Package_Manager) and [Nix derivations](https://wiki.nixos.org/wiki/Derivations).

ANNY adoption:

- explicit task inputs
- explicit policy/runtime/tool versions
- isolated workspace
- content identity
- cache eligibility only for hermetic capabilities
- durable evidence

### Research pattern B — hermetic actions and action caching

A mature build system defines hermetic actions as actions isolated from host changes and recommends strict sandboxing plus cache verification to detect hidden environment dependencies. [Hermeticity documentation](https://bazel.googlesource.com/bazel/%2B/refs/heads/release-10.0.0-pre.20260520.2rc1/docs/basics/hermeticity.mdx).

ANNY adoption:

- action/task identity
- input and output hashes
- strict distinction between hermetic and non-hermetic capabilities
- future content-addressed cache
- reproducibility tests

### Research pattern C — local-first DAG execution

A local-first workflow engine demonstrates declarative DAGs, retries, concurrency controls, execution history, reusable sub-DAGs and reuse of prior step results when commands and files have not changed. [Dagu project](https://github.com/dagucloud/dagu).

ANNY adoption:

- future deterministic task graph
- explicit dependencies
- bounded retries
- local scheduling
- durable execution history
- reuse of valid prior deterministic results

## What ANNY should NOT copy

- no external product-specific architecture
- no external project names in Runtime capability IDs
- no replacement of ANNY governance with generic workflow semantics
- no uncontrolled remote execution
- no implicit network access
- no automatic activation
- no deterministic write capability without explicit authority/policy

## Next technical layer

The next deterministic-substrate milestone should introduce:

1. canonical execution fingerprint
2. content-addressed input/output identity
3. deterministic result cache
4. replay/idempotency contract
5. dependency graph/DAG model
6. bounded retry policy
7. stronger sandbox boundary
8. capability family inventory
9. focused execution tests
10. durable evidence for cache hits/misses and replay

## Verification boundary

This document records implementation direction and current source evidence. It does not claim current repository-wide test execution, end-to-end verification or certification.
