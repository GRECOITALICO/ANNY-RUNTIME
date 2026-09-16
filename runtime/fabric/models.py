"""
Repository Fabric domain models.

These models represent the canonical organizational state held by the
Repository Fabric (resolved dynamically per deployment). They are NEVER
generated locally — they are READ from the Fabric and validated.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class FabricStatus(str, Enum):
    CONNECTED = "CONNECTED"
    UNREACHABLE = "UNREACHABLE"
    AUTH_ERROR = "AUTH_ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    IDENTITY_UNVERIFIED = "IDENTITY_UNVERIFIED"
    TRUST_UNVERIFIED = "TRUST_UNVERIFIED"
    TENANT_UNBOUND = "TENANT_UNBOUND"
    DEGRADED = "DEGRADED"


@dataclass
class FabricNode:
    """Represents a Repository Fabric control node (node_id resolved from Fabric)."""
    node_id: str          # e.g. "NODE-001" (resolved from Fabric, not hardcoded)
    org: str              # e.g. "my-org" (resolved from RuntimeConfig, not hardcoded)
    repo: str             # e.g. "my-fabric-repo" (resolved from RuntimeConfig, not hardcoded)
    purpose: str          # e.g. "REPOSITORY_FABRIC"
    created_at: str
    status: FabricStatus = FabricStatus.CONNECTED

    @classmethod
    def from_dict(cls, data: dict) -> "FabricNode":
        return cls(
            node_id=data["node_id"],
            org=data["org"],
            repo=data["repo"],
            purpose=data.get("purpose", "REPOSITORY_FABRIC"),
            created_at=data.get("created_at", ""),
        )


@dataclass
class FabricTenant:
    """A registered runtime tenant in the Fabric."""
    tenant_id: str
    runtime_id: str
    project_ids: List[str]
    enrolled_at: str
    public_key_fingerprint: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "FabricTenant":
        return cls(
            tenant_id=data["tenant_id"],
            runtime_id=data["runtime_id"],
            project_ids=data.get("project_ids", []),
            enrolled_at=data.get("enrolled_at", ""),
            public_key_fingerprint=data.get("public_key_fingerprint"),
        )


@dataclass
class FabricProject:
    """A project binding within a tenant."""
    project_id: str
    tenant_id: str
    repo: str
    branch: str

    @classmethod
    def from_dict(cls, data: dict) -> "FabricProject":
        return cls(
            project_id=data["project_id"],
            tenant_id=data["tenant_id"],
            repo=data.get("repo", ""),
            branch=data.get("branch", "main"),
        )


@dataclass
class FabricTrustToken:
    """A verified trust relationship between runtime and Fabric."""
    runtime_id: str
    node_id: str
    issued_at: str
    expires_at: str
    signature: str    # HMAC-SHA256 of runtime_id+node_id+issued_at
    verified: bool = False


@dataclass
class FabricHealthResult:
    """Result of a Fabric reachability probe."""
    reachable: bool
    node_id: Optional[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class FabricProvenanceEntry:
    """A single provenance record in the Fabric."""
    commit_sha: str
    runtime_id: str
    mission_id: str
    recorded_at: str
    verified: bool = False

@dataclass
class FabricPolicy:
    """Policy rules inherited from the Repository Fabric."""
    revision: str
    require_admission: bool = True
    allow_local_models: bool = True
    allow_remote_models: bool = True
    max_workspace_size_mb: int = 1024

    @classmethod
    def from_dict(cls, data: dict) -> "FabricPolicy":
        return cls(
            revision=data.get("revision", "UNKNOWN"),
            require_admission=data.get("require_admission", True),
            allow_local_models=data.get("allow_local_models", True),
            allow_remote_models=data.get("allow_remote_models", True),
            max_workspace_size_mb=data.get("max_workspace_size_mb", 1024),
        )

@dataclass
class FabricContract:
    """Execution boundaries and limits."""
    contract_id: str
    tenant_id: str
    granted_capabilities: List[str] = field(default_factory=list)
    revoked_capabilities: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "FabricContract":
        return cls(
            contract_id=data.get("contract_id", "UNKNOWN"),
            tenant_id=data.get("tenant_id", "UNKNOWN"),
            granted_capabilities=data.get("granted_capabilities", []),
            revoked_capabilities=data.get("revoked_capabilities", []),
        )
