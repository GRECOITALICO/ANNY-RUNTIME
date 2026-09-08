# ANNY Customer Zero Bootstrap Specification

## Overview

The ANNY Customer Zero Bootstrap process enables a freshly installed `ANNY-RUNTIME` node to initialize its identity, authenticate with GitHub, discover accessible organizations and repositories, resolve `GRECOITALICO/ANNY-OPERATIONAL` as its canonical state, and expose complete operational status through the Control Plane.

## Bootstrap Sequence

1. **Identity Initialization**: Ed25519 keypair generation and local credential persistence.
2. **GitHub Authorization**: Device Flow (RFC 8628) token acquisition.
3. **Organization Discovery**: Read-only GitHub API discovery of authenticated principal, accessible organizations, and repositories.
4. **Operational State Resolution**: Resolving `GRECOITALICO/ANNY-OPERATIONAL` and executing the 14-stage read order per `BOOTSTRAP.md`.
5. **Continuity Reconciliation**: Reconciling canonical state against observed GitHub and local runtime state to classify continuity (`CONSISTENT`, `DEGRADED`, `CONFLICTED`, `UNKNOWN`, `BLOCKED`).
6. **Control Plane Exposure**: Serving operational dashboard and `/api/v1/continuity/bootstrap` REST endpoint.
7. **Execution Boundary**: Stopping at `ANNY_READY_FOR_WORK` without automatic worker spawning or LLM execution.

## Architectural Boundaries

- **Repository Fabric**: Status strictly reported as `NOT_CONFIGURED`.
- **Mutations**: Bootstrap is strictly read-only. No GitHub repositories or branches are created or modified.
- **Dynamic Mission Resolution**: Current mission is read dynamically from `state/CURRENT_MISSION.yaml` (e.g. `MISSION-058`).
