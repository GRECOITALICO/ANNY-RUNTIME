from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional, Dict
import os
import uuid
import time
import shutil
from pathlib import Path

class WorkspaceState(Enum):
    CREATING = auto()
    READY = auto()
    ACTIVE = auto()
    IDLE = auto()
    RECOVERING = auto()
    DESTROYING = auto()
    DESTROYED = auto()

@dataclass
class Workspace:
    workspace_id: str
    tenant_id: str
    actor_scope: List[str]
    repository: str
    source_revision: str
    state: WorkspaceState
    generation: int
    local_path: str
    created_at: str
    locked_by: Optional[str] = None

class WorkspaceManager:
    def __init__(self, base_dir: str, config: dict) -> None:
        self.base_dir = Path(base_dir)
        self.config = config
        self._workspaces: Dict[str, Workspace] = {}
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _validate_context_ownership(self, context, workspace_id: str) -> Optional[Workspace]:
        ws = self._workspaces.get(workspace_id)
        if not ws:
            return None
        if ws.tenant_id != context.tenant_id:
            raise PermissionError("Access denied: tenant mismatch")
        if context.actor_id not in ws.actor_scope and '*' not in ws.actor_scope:
            raise PermissionError("Access denied: actor mismatch")
        return ws

    def create(self, context, actor_scope: List[str], repository: str, source_revision: str) -> Workspace:
        """Creates a new workspace and directory."""
        if not context.has_capability("WORKSPACE_CREATE"):
            raise PermissionError("Access denied: missing WORKSPACE_CREATE")
            
        workspace_id = str(uuid.uuid4())
        local_path = self.base_dir / workspace_id
        
        ws = Workspace(
            workspace_id=workspace_id,
            tenant_id=context.tenant_id,
            actor_scope=actor_scope,
            repository=repository,
            source_revision=source_revision,
            state=WorkspaceState.CREATING,
            generation=context.generation,
            local_path=str(local_path),
            created_at=str(time.time()),
        )
        self._workspaces[workspace_id] = ws
        
        local_path.mkdir(parents=True, exist_ok=True)
        ws.state = WorkspaceState.READY
        return ws

    def status(self, context, workspace_id: str) -> Optional[Workspace]:
        """Returns workspace status securely."""
        return self._validate_context_ownership(context, workspace_id)

    def lock(self, context, workspace_id: str) -> bool:
        """Locks a workspace to an actor."""
        ws = self._validate_context_ownership(context, workspace_id)
        if ws and ws.locked_by is None:
            ws.locked_by = context.actor_id
            return True
        return False

    def unlock(self, context, workspace_id: str) -> bool:
        """Unlocks a workspace."""
        ws = self._validate_context_ownership(context, workspace_id)
        if ws and ws.locked_by == context.actor_id:
            ws.locked_by = None
            return True
        return False

    def destroy(self, context, workspace_id: str) -> bool:
        """Destroys a workspace and its directory."""
        if not context.has_capability("WORKSPACE_DELETE"):
            raise PermissionError("Access denied: missing WORKSPACE_DELETE")
            
        ws = self._validate_context_ownership(context, workspace_id)
        if ws:
            if ws.generation != context.generation:
                raise PermissionError("Access denied: generation stale")
            ws.state = WorkspaceState.DESTROYING
            shutil.rmtree(ws.local_path, ignore_errors=True)
            ws.state = WorkspaceState.DESTROYED
            del self._workspaces[workspace_id]
            return True
        return False

    def recover(self, context, workspace_id: str) -> bool:
        """Recovers a workspace."""
        ws = self._validate_context_ownership(context, workspace_id)
        if ws and ws.state != WorkspaceState.DESTROYED:
            ws.state = WorkspaceState.RECOVERING
            ws.state = WorkspaceState.READY
            return True
        return False

    def validate_access(self, workspace_id: str, tenant_id: str, actor_id: str) -> bool:
        """Legacy compatibility wrapper. Avoid using directly."""
        ws = self._workspaces.get(workspace_id)
        if not ws: return False
        if ws.tenant_id != tenant_id: return False
        if actor_id not in ws.actor_scope and '*' not in ws.actor_scope: return False
        return True
