# ANNY Customer Zero Bootstrap Specification

## Overview

The ANNY Customer Zero Bootstrap process enables a freshly installed `ANNY-RUNTIME` node to initialize its identity, authenticate with GitHub, discover accessible organizations and repositories, dynamically resolve its operational repository, and expose complete operational status through the Control Plane.

> **Note:** The operational repository is discovered dynamically via explicit markers (repository topic `anny-operational` or presence of `BOOTSTRAP.md`). It is NOT hardcoded to any specific owner or repository name. In the Customer Zero example deployment, the operational repository happens to be `GRECOITALICO/ANNY-OPERATIONAL`, but this is specific to that deployment and is not a universal architectural assumption.

## Bootstrap Sequence

1. **Identity Initialization**: Ed25519 keypair generation and local credential persistence.
2. **GitHub Authorization**: GitHub Access Token onboarding (paste-based). Device Flow (RFC 8628) retained as optional future method.
3. **Organization Discovery**: Read-only GitHub API discovery of authenticated principal, accessible organizations, and repositories.
4. **Operational Repository Resolution**: Dynamically discovering the operational repository by inspecting all accessible repositories for an explicit operational-repository marker (`anny-operational` topic or `BOOTSTRAP.md` presence). Exactly one candidate must be found; zero yields `BLOCKED/UNKNOWN`, multiple yields `AMBIGUOUS/BLOCKED`.
5. **14-Stage Bootstrap Read**: Executing the 14-stage read order per `BOOTSTRAP.md` contract against the resolved operational repository.
6. **Continuity Reconciliation**: Reconciling canonical state against observed GitHub and local runtime state to classify continuity (`CONSISTENT`, `DEGRADED`, `CONFLICTED`, `UNKNOWN`, `BLOCKED`).
7. **Control Plane Exposure**: Serving operational dashboard and `/api/v1/continuity/bootstrap` REST endpoint.
8. **Execution Boundary**: Stopping at `ANNY_READY_FOR_WORK` without automatic worker spawning or LLM execution.

## Architectural Boundaries

- **Repository Fabric**: Status strictly reported as `NOT_CONFIGURED`.
- **Mutations**: Bootstrap is strictly read-only. No GitHub repositories or branches are created or modified.
- **Dynamic Mission Resolution**: Current mission is read dynamically from `state/CURRENT_MISSION.yaml`.
- **No Automatic Execution**: No mission is automatically executed. The bootstrap stops at `ANNY_READY_FOR_WORK`.

## Customer Zero Example

In the Customer Zero deployment:
- **Operational Repository**: `GRECOITALICO/ANNY-OPERATIONAL` (discovered dynamically, not hardcoded)
- **Owner**: `GRECOITALICO` (specific to this deployment)

**Customer Zero example ≠ universal architecture.** Other deployments will resolve their own operational repository through the same dynamic discovery mechanism.

## Operational Repository Discovery Rules

1. Authenticate principal via GitHub API
2. List all accessible repositories (user + organization)
3. For each repository, check for operational-repository marker:
   - Repository topic `anny-operational`, OR
   - Presence of `BOOTSTRAP.md` in repository root
4. If exactly one candidate: resolve as operational repository
5. If zero candidates: `BLOCKED/UNKNOWN`
6. If multiple candidates: `AMBIGUOUS/BLOCKED`

The discovery is deterministic: given the same set of accessible repositories, the same candidate (or error) will always be produced.
