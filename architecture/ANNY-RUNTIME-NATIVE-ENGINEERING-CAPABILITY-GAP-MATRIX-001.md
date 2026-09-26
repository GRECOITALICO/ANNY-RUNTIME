# ANNY Runtime — Native Engineering Parity Gap Matrix 001

## Scope

This matrix translates the useful engineering work normally performed in a coding-agent environment into ANNY Runtime-owned capabilities.

The comparison is capability-oriented. It is not a ranking of products.

## State vocabulary

- BUILT: source capability exists.
- PARTIAL: source exists but the end-to-end contract is incomplete.
- UNVERIFIED: source exists but physical Runtime execution has not been demonstrated.
- MISSING: no current native module.
- CERTIFIED: end-to-end evidence establishes the capability.

## Matrix

| Domain | ANNY Runtime state | What still closes the gap |
|---|---|---|
| Workspace | PARTIAL | one canonical governed workspace from request through result |
| File read/search/inspect | BUILT/PARTIAL | Runtime execution and evidence proof |
| File edit/patch/create/delete | PARTIAL | canonical mutation path + receipts + edge cases |
| Shell | PARTIAL | structured argv execution, streaming, cancellation and limits |
| Process | PARTIAL | lifecycle, drain, timeout/cancel and process identity evidence |
| Git | PARTIAL | full local catalog, remote policy, snapshot and mutation receipts |
| Test/lint/type/build | PARTIAL | discovery, parsers, artifacts and result/evidence correlation |
| GitHub engineering | PARTIAL | bind client to Runtime authority and prove mutations |
| Browser | BUILT/PARTIAL | live installation/health/execution evidence and engineering integration |
| Environment diagnostics | PARTIAL | dependency/executable/port/service/log operations as one governed plane |
| Secrets | PARTIAL | single authoritative context and no bypass routes |
| Harness | PARTIAL | physical execution, result consumption and checkpoint |
| Evidence | PARTIAL | one request -> execution -> result -> receipt -> checkpoint chain |
| Orchestration | PARTIAL | composite tasks and executor availability semantics |
| Local model | PARTIAL | artifact provenance, lifecycle and governed binding |
| Delegated worker | PARTIAL | authorization, receipts and native fallback |
| Native IDE | MISSING | build UI over Runtime capabilities only |
| Update | FAIL-CLOSED PARTIAL | authoritative discovery/download/stage/activate/rollback |
| Sync | FAIL-CLOSED PARTIAL | physical lifecycle verification |
| External-agent independence | NOT PROVEN | ANNY-first representative tasks across all domains |

## First executable milestones

### Level 1

ANNY Runtime executes a safe deterministic repository inspection in a governed workspace and returns evidence that ANNY can consume.

### Level 2

ANNY performs a bounded composite:

inspect -> edit/patch -> focused test -> result.

### Level 3

ANNY performs a bounded complex engineering task:

diagnose -> patch -> verify -> evidence.

### Level 4

ANNY operates the full workspace/tooling loop, including Git and authorized GitHub engineering.

### Level 5

ANNY-first certification is established for representative engineering tasks.

### Level 6

Optional governed delegation is enabled only after Level 5.

### Level 7

Native Runtime is the mandatory fallback when delegation is absent or fails.

## Reuse strategy

Open-source components may accelerate commodity layers. They do not replace the ANNY governance boundary.

A reused component must remain subordinate to:

ExecutionContext -> capability policy -> Runtime service -> validation -> evidence.

## Current safety boundary

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
