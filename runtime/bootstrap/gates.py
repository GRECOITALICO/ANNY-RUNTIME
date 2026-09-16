"""
Bootstrap Readiness Gates.

Defines the 11 mandatory gates required for ANNY_READY to be true.
"""
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class ReadinessGate(Enum):
    # Plane 1 - Local Runtime Identity
    RUNTIME_IDENTITY = auto()
    
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
    
    # Cross-Plane Integrity
    PLANE_RECONCILIATION = auto()
    CONTINUITY_COHERENT = auto()


@dataclass
class GateResult:
    """The result of evaluating a single readiness gate."""
    gate: ReadinessGate
    passed: bool
    detail: str
    evidence: Optional[str] = None
