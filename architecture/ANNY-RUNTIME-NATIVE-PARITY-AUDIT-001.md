# ANNY Runtime Native Engineering Parity — Audit 001

## Executive finding

ANNY-RUNTIME already contains a substantial engineering substrate. It is not yet a self-sufficient coding-agent replacement because several capabilities are only partial, read-only, stubbed, disconnected from the canonical Harness, or not yet proven by execution.

The audit target is functional engineering independence from Antigravity/Cursor and progressive retirement of external Codex execution.

## Audited existing areas

| Area | Existing source | Current truth | Main gap |
|---|---|---|---|
| ExecutionContext | `runtime/security/execution_context.py` | Implemented/governed | one adapter/current-generation source |
| Workspace | `runtime/workspace/manager.py`, `ephemeral.py` | Implemented/dual-model | unify governed workspace with execution workspace |
| Filesystem | `runtime/filesystem/service.py` | Basic governed CRUD | richer operation catalog + evidence |
| Shell | `runtime/shell/executor.py` | Hardened partial | structured command model/composites |
| Process | `runtime/process/manager.py` | Basic execution | durable lifecycle/evidence/drain |
| Git | `runtime/git/service.py` | Hardened partial | complete catalog + remote policy |
| Toolchain | `runtime/toolchain/runner.py` | Added | discovery/parser/artifacts/evidence |
| GitHub auth | `runtime/admin/github.py` | Implemented | engineering API surface |
| GitHub engineering | `runtime/github/engineering.py` | Implemented source-level | runtime binding + broader PR/review/release surface |
| Browser | `runtime/browser/*` | Implemented brokered | execution/health proof; broker is Runtime infrastructure, not an agent |
| MCP | `runtime/mcp/*` | Implemented partial | broaden through canonical capabilities only |
| Harness | `runtime/execution/harness_contract.py`, `harness_dispatcher.py` | Implemented partial | actual execution + receipt + ANNY consumption |
| Continuity/evidence | `runtime/continuity/*` | Implemented partial | single request→execution→receipt chain |
| Intelligence | `runtime/intelligence/*`, Qwen | Implemented partial | physical provenance/lifecycle proof |
| Diagnostics | `runtime/diagnostics/doctor.py` | Hardened | live execution proof |
| Update/SYNC | `runtime/updater/*`, `runtime/sync/*` | Fail-closed partial | authoritative update + physical lifecycle |
| Control Center | `runtime/admin/*` | Large projection layer | backend capability completion before more UI |
| Native IDE | none | Missing | must be built over Runtime APIs |

## Important corrections from historical reports

1. `runtime/browser` exists and includes a governed Browser Broker, authorization, navigation, observation, target discovery, click/type/fill/select/check and submission controls.
2. `runtime/updater/manager.py` exists but its former lifecycle was synthetic; it has now been changed to fail closed except for local checksum verification.
3. `runtime/diagnostics/doctor.py` formerly emitted unconditional PASS states; it has now been changed to report UNKNOWN/WARN/FAIL unless a real local observation supports PASS.
4. `runtime/admin/routes.py` formerly marked restart and update-check as SUCCESS without performing those operations; this has now been corrected.
5. GitHub organization discovery in Admin routing referenced a nonexistent client method and has been corrected to use the existing discovery service.
6. Shell execution had a first-token classification risk when later shell control operators were still passed to `bash -lc`; control syntax is now rejected by the deterministic path.
7. Filesystem containment used string-prefix comparison; it now uses `Path.relative_to`.

## Capability parity target

The useful harness substrate to internalize is:

- workspace
- files
- shell
- processes
- tests/lint/type-check/build
- Git
- GitHub
- browser/computer interaction where needed
- diagnostics/environment
- evidence/provenance
- authorization/context
- Harness/orchestration
- IDE
- complex engineering workflows
- models/workers
- optional delegation

Plugins, cosmetic integrations and provider-specific implementation details are intentionally excluded.

## Non-dependence rule

Antigravity and Cursor are not product dependencies.

Codex is temporary construction only.

Final path:

ANNY
→ Harness
→ ExecutionContext
→ Workspace
→ Runtime tools/executors
→ validation
→ receipt/evidence
→ ANNY consumption
→ checkpoint

Optional:

→ governed delegated worker

## Required independence gate

External-agent retirement is not declared by source-code existence. It requires successful Runtime execution of representative tasks across:

1. inspect
2. search/read
3. edit/patch
4. test/lint/type-check/build
5. Git
6. GitHub PR workflow
7. process/diagnostics
8. evidence/checkpoint
9. simple composite engineering
10. native IDE

Every representative capability must pass the ANNY adoption ladder:
L0 observe → L1 deterministic → L2 composite → L3 complex → L4 full workspace → L5 ANNY-first → L6 delegation → L7 native fallback.

## Current priority

P0: execution substrate
P0: repository engineering
P0: verification toolchain
P0: GitHub engineering
P0: environment operations
P0: evidence/governance
P0: Harness self-use

P1: Native IDE
P1: complex engineering
P1: intelligence/workers

Only after these boundaries are proven should broader convenience integrations be considered.

## Safety

activation=false
production=false
authority_expansion=false
destructive_mutation=false
historical_overwrite=false
azure_mutation=false
routing_authorization=false
deployment_authorized=false
merge_authorized=false
KIRA_P2=SEPARATE_AND_UNTOUCHED
T12=SEPARATE_BLOCKER
