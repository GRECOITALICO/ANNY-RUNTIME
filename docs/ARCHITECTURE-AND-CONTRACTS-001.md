# ANNY Runtime — Architecture and Contracts 001

## 1. Scope

This document defines the implementation boundaries for ANNY Runtime so future sessions do not rebuild the wrong system.

## 2. What Runtime is

ANNY Runtime is the local execution gateway of ANNY. It is not a generic autonomous-agent wrapper and it is not a replacement for ANNY as organizational authority.

The current README defines the intended experience as one local Runtime connected to GitHub, while ChatGPT/Claude act as the conversational interface. fileciteturn112file0

## 3. What Runtime is not

Runtime must not become:

- the organizational authority itself;
- an uncontrolled autonomous agent;
- a second source of organizational truth;
- an implicit production deployer;
- a credential vault;
- a silent auto-updater that changes versions without explicit governance.

## 4. Primary modules

### Identity

Owns durable Runtime identity and cryptographic identity material. Identity persists across process restarts.

### Enrollment / Binding

Owns the transition from unbound runtime to enrolled/registered/paired/ready state and binds Runtime, tenant and ANNY instance.

### Bootstrap

Establishes deterministic evidence-first readiness across runtime, GitHub, Fabric, policy, inventory, access, contracts, delegation and continuity.

### Fabric Adapter

Provides the repository/Fabric transport boundary. Repository identity must be dynamically bound; legacy hardcoded Fabric identities are prohibited.

### Continuity

Persists missions/tasks/steps, events, state transitions and recovery facts.

### Execution

Runs governed effects through a singular authorized execution pipeline. The pipeline checks execution context, tenant, session/generation, runtime identity, tools/capabilities and workspace ownership before allowing an effect.

### Evidence / Receipts

Produces durable sanitized receipts and evidence references for governed operations.

### Recovery

Detects interrupted work, restores or reconciles state and advances generation to fence stale execution contexts.

### Admin / Control Center

Provides sanitized state and operational controls. Browser-visible DTOs must never expose credentials or private keys.

### Update / Sync

Controls discovery, comparison, verification, staging, activation, rollback and health. SYNC is its own governed operation and must not be conflated with activation.

## 5. Capability boundary

Every tool/action must be evaluated by:

```text
identity
+ tenant
+ session
+ generation
+ authority
+ capability grant
+ workspace ownership
+ policy
= eligible execution context
```

## 6. Security boundary

No execution should occur through a shortcut around the authorized execution pipeline.

No mutation should bypass continuity/evidence recording when the operation is part of a governed mission.

## 7. API boundary

The admin layer may provide:

- state inspection;
- bootstrap verification;
- diagnostics;
- GitHub connection actions;
- Fabric setup;
- execution/worker/missions views;
- continuity/audit/evidence views;
- telemetry;
- Sync controls when implemented.

Current routes include `/api/status` and `/api/bootstrap/verify`; a canonical `/api/sync` route is not yet present in the observed route table. fileciteturn113file0

## 8. Update contract

The updater state machine is intended to distinguish:

```text
IDLE
CHECKING
DOWNLOADING
VERIFYING
STAGING
QUIESCING
ACTIVATING
ROLLING_BACK
FAILED
```

The current `UpdateManager` defines these states but its operational methods remain stubs, so these values are a contract/skeleton rather than evidence of full update functionality. fileciteturn114file0

## 9. SYNC contract

The canonical semantic contract is:

```text
SYNC
 != VERIFY
 != STAGE
 != ACTIVATE
 != AUTO ACTIVATE
```

Pipeline:

```text
REQUEST
 -> DISCOVER
 -> COMPARE
 -> VERIFY
 -> REPORT
 -> optional STAGE
 -> optional ACTIVATE
 -> HEALTH
 -> CERTIFY
```

The existing durable SYNC contract requires a first-class Control Center control, explicit states, durable trace/evidence and a distinction between sync and activation. fileciteturn117file0

## 10. DTO safety

Admin/browser DTOs must be projections, not raw domain dumps. They must omit:

- access tokens;
- private keys;
- credentials;
- secret values;
- sensitive raw transport data not needed for UI.

## 11. Model-provider independence

The Runtime protocol must not require OpenAI, Anthropic or another model provider to be the Runtime itself. Models are clients/actors of the execution gateway, not the underlying identity of Runtime.

## 12. Repository/Fabric separation

GitHub is a transport/repository source. Repository Fabric provides the higher-level organizational and provenance semantics required by ANNY. Runtime must not replace one with the other.

## 13. Localhost principle

The primary local administrative surface may be loopback-only. Current work hardened localhost binding to support both `127.0.0.1` and `::1`.

## 14. Implementation rule

When adding a new feature, document it in four places before calling it complete:

1. architecture/contract;
2. implementation;
3. tests;
4. reconstruction/milestone evidence.

## 15. Completion rule

A feature is `IMPLEMENTED` only when its code path is real. It is `VERIFIED` only when tested against the required acceptance conditions. It is `CERTIFIED` only when the corresponding evidence and authority requirements are satisfied.
