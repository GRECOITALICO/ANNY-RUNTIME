# ANNY Runtime — CONRRAD Infrastructure Visibility and Mandatory Bootstrap

**MANDATORY PRODUCT CONTRACT**

ANNY Runtime is an online execution surface of ANNY + CONRRAD, not an isolated local application.

## Startup order

    INSTALL ANNY
      ↓
    START LOCAL RUNTIME
      ↓
    RUNTIME IDENTITY
      ↓
    CONRRAD BOOTSTRAP PREFLIGHT  ← mandatory, before GitHub
      ↓
    VERIFY CONRRAD MANIFEST / TRUST
      ↓
    LOAD CONRRAD DEPENDENCY REGISTRY
      ↓
    CONNECT GITHUB
      ↓
    ANNY AUTH
      ↓
    EXTERNAL EXECUTION CONTEXT
      ↓
    ANNY CONTROL PLANE
      ↓
    REPOSITORY FABRIC
      ↓
    RUNTIME READY

A mandatory CONRRAD dependency that is missing, offline, unverified or unauthorized blocks bootstrap or the affected operation.

## Localhost: CONRRAD INFRASTRUCTURE

The Control Center must expose every CONRRAD service actually used by Runtime.

Required fields:

| Field | Required meaning |
|---|---|
| Service | Canonical CONRRAD service identifier/name |
| Class | Auth, Fabric, context, policy, evidence, identity, etc. |
| Endpoint | Authoritative endpoint |
| Node | node_id |
| Deployment | deployment_id |
| Source | source_commit |
| Artifact | artifact_digest |
| Contract | protocol/API version |
| Online | ONLINE_VERIFIED / ONLINE_UNVERIFIED / OFFLINE / BLOCKED / NOT_CONFIGURED / UNKNOWN |
| Trust | VERIFIED / UNVERIFIED / REJECTED / UNKNOWN |
| Certification | CERTIFIED_BY_LIVE_EVIDENCE / TEST_EVIDENCE_ONLY / NOT_CERTIFIED / UNKNOWN |
| Last check | Live verification timestamp |
| Evidence | Durable evidence_ref |
| Failure | Exact blocking reason |

## Certification

CERTIFIED_BY_LIVE_EVIDENCE is an evidence-derived state. HTTP reachability, GitHub file presence, Azure resource existence, fixtures, or local tests are not sufficient by themselves.

## Mandatory inventory

At minimum:

1. ANNY Auth.
2. External ExecutionContext issuer.
3. Repository Fabric.
4. Policy evaluator.
5. Durable evidence ledger.
6. Identity/admission.
7. Node/deployment identity.
8. Required observability/correlation.
9. Any other CONRRAD service invoked by Runtime.

No hidden CONRRAD dependency is acceptable.

## Fail closed

    CONRRAD DEPENDENCY FAILURE
      ↓
    BLOCK BOOTSTRAP / BLOCK AFFECTED OPERATION
      ↓
    SHOW SERVICE + STATUS + EVIDENCE + REASON
      ↓
    NO DIRECT-GITHUB BYPASS
      ↓
    NO FALSE CERTIFICATION

## End-to-end acceptance

fresh install → Runtime identity → CONRRAD preflight → visible infrastructure matrix → GitHub authorization → external ExecutionContext → canonical ANNY control plane → Repository Fabric → Runtime ready → durable evidence → restart → fresh-session reconstruction.

Offline operation is not supported.
