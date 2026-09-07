import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from runtime.sandbox.policy import SandboxPolicy, IsolationLevel
from runtime.sandbox.backend import SandboxBackend, WorkspaceBackend, RestrictedProcessBackend

logger = logging.getLogger(__name__)


class SandboxManager:
    """Manages sandbox lifecycle for operation isolation."""
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        sandbox_base = f"{data_dir}/sandboxes"
        self._backends: Dict[IsolationLevel, SandboxBackend] = {
            IsolationLevel.LEVEL_1: WorkspaceBackend(sandbox_base),
            IsolationLevel.LEVEL_2: RestrictedProcessBackend(sandbox_base),
        }
        self._policies: Dict[str, SandboxPolicy] = {}
    
    def create_sandbox(
        self,
        tenant_id: str,
        actor_id: str,
        workspace_id: str,
        isolation_level: IsolationLevel = IsolationLevel.LEVEL_1,
        filesystem_scope: list = None,
        ttl_seconds: int = 3600,
    ) -> SandboxPolicy:
        """Create a new sandbox with the specified policy."""
        sandbox_id = f"sbx-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        
        policy = SandboxPolicy(
            sandbox_id=sandbox_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            workspace_id=workspace_id,
            isolation_level=isolation_level,
            filesystem_scope=filesystem_scope or [],
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat(),
        )
        
        backend = self._backends.get(isolation_level)
        if not backend:
            raise ValueError(f"No backend available for isolation level: {isolation_level}")
        
        backend.create(policy)
        self._policies[sandbox_id] = policy
        logger.info(f"Sandbox {sandbox_id} created for actor {actor_id} at level {isolation_level.value}")
        return policy
    
    def check_access(self, sandbox_id: str, path: str) -> bool:
        """Check if a path access is allowed within a sandbox."""
        policy = self._policies.get(sandbox_id)
        if not policy:
            logger.warning(f"Access check for unknown sandbox: {sandbox_id}")
            return False
        return policy.allows_path(path)
    
    def destroy_sandbox(self, sandbox_id: str) -> None:
        """Destroy a sandbox, cleaning up temporary state."""
        policy = self._policies.pop(sandbox_id, None)
        if not policy:
            logger.warning(f"Cannot destroy unknown sandbox: {sandbox_id}")
            return
        
        backend = self._backends.get(policy.isolation_level)
        if backend:
            backend.destroy(sandbox_id)
        logger.info(f"Sandbox {sandbox_id} destroyed")
    
    def get_policy(self, sandbox_id: str) -> Optional[SandboxPolicy]:
        return self._policies.get(sandbox_id)
    
    def list_active(self) -> list:
        return list(self._policies.keys())
