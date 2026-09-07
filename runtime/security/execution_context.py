from dataclasses import dataclass, field
from typing import Set, Optional
from datetime import datetime

@dataclass(frozen=True)
class ExecutionContext:
    """
    The canonical ExecutionContext for all physical operations in ANNY-RUNTIME.
    No physical tool should execute without a verified instance of this context.
    """
    tenant_id: str
    anny_instance_id: str
    runtime_id: str
    session_id: str
    actor_id: str
    operation_id: str
    execution_id: str
    generation: int
    issued_at: datetime
    expires_at: datetime
    
    # Optional context scope limits
    workspace_id: Optional[str] = None
    
    # Authorized capabilities for this specific execution
    capabilities: Set[str] = field(default_factory=set)

    def has_capability(self, capability: str) -> bool:
        """Check if the context possesses a specific capability grant."""
        return capability in self.capabilities

    def is_valid(self, current_time: datetime, current_generation: int) -> bool:
        """
        Validates the context against generation fencing and temporal expiration.
        """
        if self.generation != current_generation:
            return False
        if current_time > self.expires_at:
            return False
        if current_time < self.issued_at:
            return False
        return True
