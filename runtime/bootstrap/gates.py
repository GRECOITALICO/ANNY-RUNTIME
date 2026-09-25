"""
Bootstrap Readiness Gates.

Defines ALL mandatory gates required for ANNY_READY to be true.

RUNTIME_* gates are EXPLICIT — RuntimeIdentity.load() is NOT
proof of reachability or admission. These gates are separate.
"""
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class ReadinessGate(Enum):
    # Plane 1 - Local Runtime Identity
    RUNTIME_IDENTITY = auto()

    # CONRRAD external authority boundary. These gates must run before GitHub.
    CONRRAD_BOOTSTRAP_PREFLIGHT = auto()
    CONRRAD_MANIFEST_AND_TRUST_VERIFIED = auto()
    CONRRAD_DEPENDENCY_REGISTRY_LOADED = auto()

    # Plane 2 - GitHub Connectivity & Auth
    GITHUB_CONNECTED = auto()
    GITHUB_ORG_BOUND = auto()

    # Plane 3 - Repository Fabric
    FABRIC_REACHABLE = auto()
    FABRIC_IDENTITY_VERIFIED = auto()
    FABRIC_TRUST_VERIFIED = auto()
    FABRIC_TENANT_BOUND = auto()
    FABRIC_STATE_READABLE = auto()
    FABRIC_PROVENANCE_VALID = auto()
    FABRIC_NODE_AT_REMOTE_HEAD = auto()   # Explicit: fabric/node.json at remote HEAD

    # ANNY-RUNTIME Reachability Gates — MANDATORY
    # These are DISTINCT from identity. Passing identity != passing these.
    RUNTIME_REACHABLE = auto()            # Runtime process is up and responds
    RUNTIME_HEALTH_VERIFIED = auto()      # Health endpoint returns 200 OK
    RUNTIME_BINDING_VERIFIED = auto()     # Runtime reports correct fabric_org/repo
    RUNTIME_ADMITTED = auto()             # Fabric has issued ALLOW for this runtime_id

    # Cross-Plane Integrity (Phase F)
    PLANE_RECONCILIATION = auto()

    # Policy and Contracts (Phase E & I)
    POLICY_SNAPSHOT_FRESH = auto()
    CONTRACTS_DISCOVERED = auto()

    # Inventories (Phase G)
    CAPABILITIES_INVENTORIED = auto()
    TOOLS_INVENTORIED = auto()
    MODELS_INVENTORIED = auto()
    WORKERS_INVENTORIED = auto()
    CONNECTORS_INVENTORIED = auto()

    # Access and Context (Phase H & J)
    CRITICAL_ACCESS_VERIFIED = auto()
    DELEGATION_CONTEXT_BUILT = auto()

    # Continuity (Phase K)
    CONTINUITY_COHERENT = auto()


# Gates that are MANDATORY for ANNY_READY — all must pass.
MANDATORY_GATES = frozenset({
    ReadinessGate.RUNTIME_IDENTITY,
    ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT,
    ReadinessGate.CONRRAD_MANIFEST_AND_TRUST_VERIFIED,
    ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED,
    ReadinessGate.GITHUB_CONNECTED,
    ReadinessGate.GITHUB_ORG_BOUND,
    ReadinessGate.FABRIC_REACHABLE,
    ReadinessGate.FABRIC_IDENTITY_VERIFIED,
    ReadinessGate.FABRIC_TRUST_VERIFIED,
    ReadinessGate.FABRIC_TENANT_BOUND,
    ReadinessGate.FABRIC_STATE_READABLE,
    ReadinessGate.FABRIC_PROVENANCE_VALID,
    ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD,
    ReadinessGate.RUNTIME_REACHABLE,
    ReadinessGate.RUNTIME_HEALTH_VERIFIED,
    ReadinessGate.RUNTIME_BINDING_VERIFIED,
    ReadinessGate.RUNTIME_ADMITTED,
    ReadinessGate.PLANE_RECONCILIATION,
    ReadinessGate.POLICY_SNAPSHOT_FRESH,
    ReadinessGate.CONTRACTS_DISCOVERED,
    ReadinessGate.CAPABILITIES_INVENTORIED,
    ReadinessGate.TOOLS_INVENTORIED,
    ReadinessGate.MODELS_INVENTORIED,
    ReadinessGate.WORKERS_INVENTORIED,
    ReadinessGate.CONNECTORS_INVENTORIED,
    ReadinessGate.CRITICAL_ACCESS_VERIFIED,
    ReadinessGate.DELEGATION_CONTEXT_BUILT,
    ReadinessGate.CONTINUITY_COHERENT,
})


@dataclass
class GateResult:
    """The result of evaluating a single readiness gate."""
    gate: ReadinessGate
    passed: bool
    detail: str
    evidence: Optional[str] = None
