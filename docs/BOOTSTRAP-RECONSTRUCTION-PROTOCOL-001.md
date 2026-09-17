# ANNY Runtime — Bootstrap Reconstruction Protocol 001

## Objective

Establish the deterministic procedure by which a fresh session, fresh machine, or fresh model reconstructs the current ANNY Runtime state without relying on previous chat context.

## Preconditions

- repository: `GRECOITALICO/ANNY-RUNTIME`;
- default operational branch: `main` unless a durable mission explicitly names another branch;
- no authority inferred from local UI;
- no mutation before bootstrap passes its required gates.

## Phase 0 — Repository truth

1. Resolve repository identity.
2. Resolve branch and remote HEAD.
3. Record observed commit SHA and timestamp.
4. Confirm the workspace corresponds to the observed commit.

Required result:

```yaml
repository_truth: VERIFIED | BLOCKED
remote_head: <sha>
branch: <branch>
```

## Phase 1 — Read durable bootstrap sources

Read, in order when present:

1. `README.md`;
2. `docs/RECONSTRUCTION-MASTER-001.md`;
3. bootstrap implementation and reports;
4. current state / mission / next action artifacts;
5. continuity and evidence artifacts;
6. SYNC/update contracts;
7. test manifests and milestone ledger.

## Phase 2 — Runtime plane

Verify:

- Runtime identity;
- installation identity;
- runtime version/protocol version;
- process reachability;
- health;
- generation;
- workspace ownership.

A Runtime identity is persistent; it is not recreated merely because a new chat starts.

## Phase 3 — GitHub / organizational plane

Verify:

- GitHub connectivity;
- authenticated source identity;
- organization/repository binding;
- target branch;
- remote HEAD;
- access needed for read-only bootstrap.

Never silently fall back to an old hardcoded repository identity.

## Phase 4 — Fabric plane

Verify:

- Fabric reachability;
- node identity;
- node at remote HEAD;
- provenance;
- trust token state;
- tenant binding;
- admission;
- policy revision.

## Phase 5 — Deterministic bootstrap gates

The current design requires phases A-K covering runtime, GitHub, Fabric, policy, reconciliation, inventory, critical access, contracts, delegation and continuity. The current deterministic implementation defines 25 mandatory gates.

The implementation milestone that introduced this expanded form is `a9771d11e3bf49fb1170a8a1140fc9887ac6e97a`.

## Phase 6 — Cross-plane reconciliation

Reconcile:

```text
Runtime identity
    <-> Tenant
    <-> Fabric node
    <-> Repository HEAD
    <-> Canonical state
    <-> Mission/task
    <-> Continuity state
```

Any conflict must be surfaced as `BLOCKED`, `UNKNOWN`, or an explicit reconciliation state. Do not auto-resolve by guessing.

## Phase 7 — Inventory discovery

Discover live registries, not stale UI cache:

- capabilities;
- tools;
- models;
- workers;
- connectors;
- executors.

## Phase 8 — Critical access verification

Run only non-destructive checks required by the bootstrap contract, including the currently specified categories:

- filesystem inspect/list;
- repository read;
- fabric read.

A successful inventory does not prove usable access; the explicit access verification phase is required.

## Phase 9 — Contracts and authority

Discover:

- operational limits;
- capability grants;
- tenant scope;
- workspace scope;
- delegation context.

Authority may not be inferred from possession of a credential, key, or API token alone.

## Phase 10 — Continuity coherence

Verify that current work can be connected to durable continuity records:

```text
mission -> task -> step -> actor -> state -> evidence -> next action -> handoff
```

## Phase 11 — Reconstruction verdict

Return a sanitized report containing:

```yaml
RECONSTRUCTION_STATUS: VERIFIED | PARTIAL | BLOCKED
REMOTE_HEAD: <sha>
RUNTIME_IDENTITY: <id or UNKNOWN>
TENANT_ID: <id or UNKNOWN>
FABRIC_NODE: <id or UNKNOWN>
CURRENT_MISSION: <id or UNKNOWN>
CURRENT_TASK: <id or UNKNOWN>
LAST_VERIFIED_MILESTONE: <id or UNKNOWN>
NEXT_ACTION: <durable action or UNKNOWN>
BLOCKERS: []
EVIDENCE_REFS: []
```

## Phase 12 — Resume policy

A new session may act only after this report identifies a durable `NEXT_ACTION` and its prerequisites are satisfied.

### Resume rule

```text
verified bootstrap
    + verified last milestone
    + verified next action
    + no blocking authority/state contradiction
    = eligible to continue
```

Otherwise:

```text
STOP / INVESTIGATE / RECONCILE
```

## Hard-stop conditions

Stop before mutation when:

- repository HEAD cannot be verified;
- identity binding is ambiguous;
- tenant is unknown;
- Fabric admission is unknown;
- canonical state conflicts with repository state;
- last milestone cannot be tied to evidence;
- next action is absent;
- required authority is not established;
- an update would be interpreted as activation without explicit authorization.

## Output contract for ChatGPT / Claude

The model-facing bootstrap must expose enough information to reconstruct:

1. what ANNY is;
2. what Runtime instance is connected;
3. which repository and revision are authoritative;
4. what mission is active;
5. what work is complete;
6. what evidence proves it;
7. what remains;
8. what is blocked;
9. what exact next action is allowed.

No prose-only state is authoritative.
