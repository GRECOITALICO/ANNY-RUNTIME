# CONRRAD Runtime — Topology Boundary Record (2026-09-21)

## Purpose
This document reconciles the repository name ANNY-RUNTIME with the current CONRRAD ontology. It does not authorize repository movement or code changes.

## Canonical interpretation

CONRRAD is the distributed infrastructure cluster. Runtime is one infrastructure node of that cluster.

```text
CONRRAD
  +-- RUNTIME node
       +-- execution
       +-- orchestration
       +-- process
       +-- session
       +-- workspace
       +-- sandbox
       +-- platform
       +-- capability adapter
       +-- compute/resource adapters
       +-- intelligence/Laboratory substrate
       +-- Fabric/GitHub clients
```

## Product consumers
ANNY and Citizen are products of CONRRAD and may consume Runtime infrastructure. They are not Runtime submodules by ontology.

## Authority boundary
Runtime may enforce technical execution policy and runtime identity. It is not:
- ANNY organizational authority;
- a replacement for ANNY-OPERATIONAL;
- a second organizational source of truth;
- a product identity registry.

## Repository boundary
GRECOITALICO/ANNY-RUNTIME is the current source-control custody surface. Repository identity must not be used as the permanent node identity.

The future canonical model is:

```text
repository -> component(s) -> CONRRAD.RUNTIME -> artifact -> deployment instance
```

## Existing implementation evidence
The current repository contains substantial Runtime infrastructure under runtime/, including execution, capability, compute, intelligence, fabric, GitHub, process, workspace and sandbox paths.

runtime/execution already demonstrates the governed chain:

```text
capability -> policy/eligibility -> implementation selection -> execution -> evidence/telemetry
```

runtime/intelligence contains Laboratory substrate primitives such as benchmark datasets, runner/store, grading, evidence building and telemetry. This is substrate evidence, not proof that the Laboratory node is fully integrated.

## Documentation reconciliation rule
Until the custody matrix is approved, existing ANNY-oriented wording remains historical/compatibility documentation where necessary. New documentation must use CONRRAD Runtime as the infrastructure owner and preserve the ANNY organizational authority boundary.

## Certification vocabulary
IMPLEMENTED != VERIFIED != CERTIFIED.
A repository path may implement a node component without proving full node certification.

## Next gate
G6 completes when README and architecture contract wording are reconciled with this record and the change is merged under normal repository authority.
