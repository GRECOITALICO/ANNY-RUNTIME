"""Sanitized Data Transfer Objects for the admin panel.

These DTOs are the ONLY objects returned to the browser.
They NEVER contain tokens, private keys, credentials, or secret material.
"""
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any


@dataclass
class RuntimeStatusDTO:
    """Sanitized runtime status for admin display."""
    runtime_id: str
    installation_id: str
    version: str
    protocol_version: str
    generation: int
    state: str
    health: Dict[str, str]
    github_status: str
    fabric_status: str
    workspace_count: int
    active_operations: int
    current_sessions: int
    update_status: str
    platform: str
    admin_port: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GitHubStatusDTO:
    """Sanitized GitHub connection status. Never contains tokens."""
    connected: bool
    principal: Optional[str]
    auth_status: str       # AUTHORIZED, UNAUTHORIZED, EXPIRED, DEGRADED
    token_status: str      # VALID, EXPIRED, MISSING, UNKNOWN
    token_expiry: Optional[str]
    scopes: List[str]
    last_validation: Optional[str]
    last_failure: Optional[str]
    last_failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FabricStatusDTO:
    """Sanitized Fabric connection status. Never contains credentials."""
    connected: bool
    tenant: Optional[str]
    anny_instance: Optional[str]
    runtime_registration: Optional[str]
    last_heartbeat: Optional[str]
    last_reconciliation: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionStatusDTO:
    """Sanitized session info. No credentials exposed."""
    session_id: str
    provider: str
    principal: str
    tenant: str
    anny_instance: str
    created_at: str
    expires_at: str
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OperationSummaryDTO:
    """Sanitized operation summary."""
    operation_id: str
    actor: str
    tenant: str
    workspace: str
    state: str
    started_at: str
    updated_at: str
    runtime_generation: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReceiptSummaryDTO:
    """Sanitized execution receipt. No secrets."""
    receipt_id: str
    operation: str
    execution: str
    tool: str
    workspace: str
    runtime: str
    status: str
    timestamp: str
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =====================================================================
# CUSTOMER ZERO CONTINUITY DTOs
# =====================================================================

@dataclass
class OrganizationDTO:
    """Sanitized Organization info."""
    login: str
    display_name: Optional[str] = None
    repository_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepositoryDTO:
    """Sanitized Repository info."""
    full_name: str
    name: str
    owner: str
    visibility: str
    archived: bool
    default_branch: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissionDTO:
    """Sanitized Mission DTO."""
    id: str
    title: str
    status: str
    description: Optional[str] = None
    task_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskDTO:
    """Sanitized Task DTO."""
    id: str
    name: str
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NextActionDTO:
    """Sanitized Next Action DTO."""
    action: str
    actor: str
    target: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlockerDTO:
    """Sanitized Blocker DTO."""
    id: str
    description: str
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class L2WorkerSummaryDTO:
    """Sanitized L2 Worker Summary DTO."""
    count: int
    registered_workers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalStateDTO:
    """Sanitized Canonical State DTO."""
    repository_name: str
    revision: Optional[str]
    bootstrap_contract_version: Optional[str]
    operating_system_version: Optional[str]
    mission: Optional[MissionDTO]
    next_action: Optional[NextActionDTO]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContinuityDTO:
    """Sanitized Continuity Status DTO for Control Plane."""
    status: str                          # CONSISTENT, DEGRADED, CONFLICTED, UNKNOWN, BLOCKED
    canonical_source: str                # e.g., "GRECOITALICO/ANNY-OPERATIONAL"
    canonical_revision: Optional[str]
    current_mission: Optional[str]
    current_task: Optional[str]
    next_action: Optional[str]
    blocker_count: int
    reconciliation_status: str
    github_status: str
    runtime_status: str
    fabric_status: str = "NOT_CONFIGURED"  # MUST remain NOT_CONFIGURED
    organizations: List[OrganizationDTO] = field(default_factory=list)
    repositories: List[RepositoryDTO] = field(default_factory=list)
    blockers: List[BlockerDTO] = field(default_factory=list)
    l2_worker_summary: Optional[L2WorkerSummaryDTO] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
