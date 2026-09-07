from pathlib import Path
from runtime.workspace.manager import WorkspaceManager
from runtime.security.execution_context import ExecutionContext

class FilesystemService:
    def __init__(self, workspace_manager: WorkspaceManager) -> None:
        self.workspace_manager = workspace_manager

    def _resolve_safe_path(self, context: ExecutionContext, path: str) -> Path:
        """Resolves a path safely blocking traversals outside the workspace."""
        if not context.workspace_id:
            raise ValueError("No workspace_id in context")
            
        ws = self.workspace_manager.status(context, context.workspace_id)
        if not ws:
            raise ValueError("Workspace not found")
            
        base = Path(ws.local_path).resolve()
        requested = (base / path).resolve()
        
        if not str(requested).startswith(str(base)):
            raise ValueError("OUTSIDE_WORKSPACE error")
            
        return requested

    def read(self, context: ExecutionContext, path: str) -> str:
        """Reads a file securely within a workspace."""
        if not context.has_capability("FILE_READ"):
            raise PermissionError("Access denied: missing FILE_READ capability")
            
        if not context.workspace_id:
            raise PermissionError("Access denied: missing workspace scope")

        if not self.workspace_manager.validate_access(context.workspace_id, context.tenant_id, context.actor_id):
            raise PermissionError("Access denied: workspace tenant/actor mismatch")
            
        safe_path = self._resolve_safe_path(context, path)
        if not safe_path.exists() or not safe_path.is_file():
            raise FileNotFoundError("File not found")
            
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()

    def write(self, context: ExecutionContext, path: str, content: str) -> bool:
        """Writes content to a file securely."""
        if not context.has_capability("FILE_WRITE"):
            raise PermissionError("Access denied: missing FILE_WRITE capability")
            
        if not context.workspace_id:
            raise PermissionError("Access denied: missing workspace scope")

        if not self.workspace_manager.validate_access(context.workspace_id, context.tenant_id, context.actor_id):
            raise PermissionError("Access denied: workspace tenant/actor mismatch")
            
        safe_path = self._resolve_safe_path(context, path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True

    def patch(self, context: ExecutionContext, path: str, search: str, replace: str) -> bool:
        """Patches a file."""
        if not context.has_capability("FILE_WRITE"):
            raise PermissionError("Access denied: missing FILE_WRITE capability")
            
        content = self.read(context, path)
        patched = content.replace(search, replace)
        if patched == content:
            return False
        return self.write(context, path, patched)

    def delete(self, context: ExecutionContext, path: str) -> bool:
        """Deletes a file securely."""
        if not context.has_capability("FILE_WRITE"):
            raise PermissionError("Access denied: missing FILE_WRITE capability")
            
        if not context.workspace_id:
            raise PermissionError("Access denied: missing workspace scope")
            
        if not self.workspace_manager.validate_access(context.workspace_id, context.tenant_id, context.actor_id):
            raise PermissionError("Access denied: workspace tenant/actor mismatch")
            
        safe_path = self._resolve_safe_path(context, path)
        if safe_path.exists():
            if safe_path.is_file():
                safe_path.unlink()
            else:
                import shutil
                shutil.rmtree(safe_path, ignore_errors=True)
            return True
        return False
