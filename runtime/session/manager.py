import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone, timedelta

from contracts.identifiers import generate_id
from runtime.session.lease import SessionLease, SessionStatus
from runtime.identity.enrollment import EnrollmentManager, EnrollmentState
from runtime.identity.runtime_identity import RuntimeIdentity
from runtime.security.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages active sessions connected to the Runtime.
    Validates tenant association and heartbeat renewals.
    """
    
    def __init__(self, config: Any, runtime_identity: RuntimeIdentity, enrollment_manager: EnrollmentManager):
        self.config = config
        self.runtime_identity = runtime_identity
        self.enrollment_manager = enrollment_manager
        self._sessions: Dict[str, SessionLease] = {}
        
    def attach(self, principal: str, tenant_id: str, anny_instance_id: str, scope: str, provider_metadata: Dict[str, Any]) -> SessionLease:
        """
        Creates a new session if enrollment allows.
        Validates that the provided tenant_id matches the enrolled tenant_id.
        """
        if self.enrollment_manager.state != EnrollmentState.READY:
            raise RuntimeError("Cannot attach session: Runtime is not enrolled and READY")
            
        # Tenant safety check: NEVER trust client tenant_id blindly
        if self.enrollment_manager.tenant_id != tenant_id:
            logger.error(f"Tenant ID mismatch during attach. Expected {self.enrollment_manager.tenant_id}, got {tenant_id}")
            raise ValueError("Tenant ID mismatch: safety violation")
            
        session_id = generate_id("SES")
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=1)
        
        lease = SessionLease(
            session_id=session_id,
            principal=principal,
            tenant_id=tenant_id,
            anny_instance_id=anny_instance_id,
            runtime_id=self.runtime_identity.runtime_id,
            scope=scope,
            provider_metadata=provider_metadata,
            created_at=now,
            expires_at=expires_at,
            status=SessionStatus.ACTIVE
        )
        self._sessions[session_id] = lease
        logger.info(f"SESSION_ATTACHED: {session_id} for tenant {tenant_id}")
        return lease
        
    def detach(self, session_id: str, reason: str) -> None:
        """Detaches and closes an active session."""
        lease = self.get(session_id)
        if lease:
            lease.close()
            logger.info(f"SESSION_DETACHED: {session_id} - Reason: {reason}")
            
    def get(self, session_id: str) -> Optional[SessionLease]:
        """Fetch a session by ID."""
        return self._sessions.get(session_id)
        
    def validate_session(self, session_id: str, current_time: datetime) -> bool:
        """
        Validates if a session is currently active, not expired, and
        matches the enrollment tenant.
        """
        lease = self.get(session_id)
        if not lease or lease.status != SessionStatus.ACTIVE:
            return False
            
        if current_time >= lease.expires_at:
            return False
            
        if lease.tenant_id != self.enrollment_manager.tenant_id:
            return False
            
        return True

    def get_context_for_session(self, session_id: str, current_time: datetime) -> Optional[ExecutionContext]:
        if not self.validate_session(session_id, current_time):
            return None
            
        lease = self.get(session_id)
        return ExecutionContext(
            tenant_id=lease.tenant_id,
            anny_instance_id=lease.anny_instance_id,
            runtime_id=lease.runtime_id,
            session_id=lease.session_id,
            actor_id=lease.principal,
            operation_id=generate_id("OP"),
            execution_id=generate_id("EXEC"),
            generation=1,
            issued_at=current_time,
            expires_at=lease.expires_at,
            workspace_id=None,
            capabilities=set()
        )
        
    def heartbeat(self, session_id: str, extend_seconds: int = 3600) -> None:
        """Extend the lifetime of an active session."""
        lease = self.get(session_id)
        if lease and lease.is_valid():
            lease.extend(extend_seconds)
            logger.debug(f"Heartbeat received for session {session_id}, extended by {extend_seconds}s")
            
    def active_sessions(self) -> List[SessionLease]:
        """Return all currently active and valid sessions."""
        return [s for s in self._sessions.values() if s.is_valid()]
        
    def cleanup_expired(self) -> None:
        """Run periodic cleanup to expire stale sessions."""
        now = datetime.now(timezone.utc)
        for s in self._sessions.values():
            if s.status == SessionStatus.ACTIVE and now >= s.expires_at:
                s.expire()
                logger.info(f"SESSION_EXPIRED: {s.session_id}")
