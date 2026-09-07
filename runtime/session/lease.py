from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, Any

class SessionStatus(Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CLOSED = "CLOSED"

@dataclass
class SessionLease:
    """
    Represents a time-bound lease granted to an Anny instance for interacting with the runtime.
    """
    session_id: str
    principal: str
    tenant_id: str
    anny_instance_id: str
    runtime_id: str
    scope: str
    provider_metadata: Dict[str, Any]
    created_at: datetime
    expires_at: datetime
    status: SessionStatus = SessionStatus.PENDING
    
    def is_valid(self) -> bool:
        """Check if the session is currently active and not expired."""
        return self.status == SessionStatus.ACTIVE and datetime.now(timezone.utc) < self.expires_at
        
    def remaining_seconds(self) -> float:
        """Get the remaining time in seconds for the session."""
        now = datetime.now(timezone.utc)
        if now > self.expires_at:
            return 0.0
        return (self.expires_at - now).total_seconds()
        
    def extend(self, seconds: int) -> None:
        """Extend the session's expiration time."""
        if self.status != SessionStatus.ACTIVE:
            return
            
        self.expires_at = self.expires_at + timedelta(seconds=seconds)
        
    def close(self) -> None:
        """Gracefully close the session."""
        self.status = SessionStatus.CLOSED
        
    def revoke(self) -> None:
        """Forcefully revoke the session (e.g. security breach)."""
        self.status = SessionStatus.REVOKED
        
    def expire(self) -> None:
        """Mark the session as expired."""
        self.status = SessionStatus.EXPIRED
