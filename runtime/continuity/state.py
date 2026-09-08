"""Continuity state objects and status definitions."""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional


class ContinuityStatus(str, Enum):
    """Allowed continuity status values."""
    CONSISTENT = "CONSISTENT"
    DEGRADED = "DEGRADED"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


@dataclass
class Blocker:
    """Representation of an operational blocker."""
    id: str
    description: str
    severity: str = "HIGH"
    source: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CurrentTask:
    """Representation of current task within a mission."""
    id: str
    name: str
    status: str = "IN_PROGRESS"
    description: Optional[str] = None
    assigned_worker: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CurrentMission:
    """Representation of current mission."""
    id: str
    title: str
    status: str = "ACTIVE"
    description: Optional[str] = None
    tasks: List[CurrentTask] = field(default_factory=list)
    raw_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NextAction:
    """Representation of next required action."""
    action: str
    actor: str = "ANNY"
    target: Optional[str] = None
    rationale: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnnyCanonicalState:
    """Canonical state of ANNY derived from ANNY-OPERATIONAL repository."""
    repository_name: str = "GRECOITALICO/ANNY-OPERATIONAL"
    revision: Optional[str] = None
    bootstrap_contract_version: Optional[str] = None
    operating_system_version: Optional[str] = None
    constitution_ref: Optional[str] = None
    current_mission: Optional[CurrentMission] = None
    current_task: Optional[CurrentTask] = None
    next_action: Optional[NextAction] = None
    blockers: List[Blocker] = field(default_factory=list)
    l2_workers: List[Dict[str, Any]] = field(default_factory=list)
    referenced_evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BootstrapResult:
    """Result of running the Customer Zero bootstrap resolver."""
    status: ContinuityStatus
    canonical_state: Optional[AnnyCanonicalState] = None
    stages_completed: List[str] = field(default_factory=list)
    blockers: List[Blocker] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
