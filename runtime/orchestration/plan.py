import enum
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


class RoutingClass(str, enum.Enum):
    DETERMINISTIC = "DETERMINISTIC"
    LOCAL_MODEL = "LOCAL_MODEL"
    FRONTIER_MODEL = "FRONTIER_MODEL"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    DEFERRED = "DEFERRED"


@dataclass
class ExecutionPlan:
    task_id: str
    capability_id: str
    capability_version: str
    routing_class: RoutingClass
    executor_type: str
    executor_id: str
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    policy_version: str = "1.0.0"
    authority: str = "anny-kernel"
    workspace_policy: str = "workspace_only"
    deadline: Optional[str] = None
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    fallback_policy: Optional[str] = None
    evidence_policy: Dict[str, Any] = field(default_factory=dict)
    decision_reason: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert ExecutionPlan to a secret-free serializable dictionary."""
        data = asdict(self)
        data["routing_class"] = self.routing_class.value if isinstance(self.routing_class, enum.Enum) else str(self.routing_class)
        # Sanitize any accidental sensitive keys from provenance/limits if present
        if "secrets" in data["provenance"]:
            del data["provenance"]["secrets"]
        if "api_key" in data["provenance"]:
            del data["provenance"]["api_key"]
        return data
