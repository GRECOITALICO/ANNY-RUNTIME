import os
import shutil

from runtime.security.path_containment import require_contained_path


class EphemeralWorkspaceManager:
    """Manage bounded local workspaces used by Runtime executions."""

    def __init__(self, base_dir: str = "/tmp/anny-workspaces"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        os.chmod(self.base_dir, 0o700)
        self.base_dir = require_contained_path(self.base_dir, ".").resolved_path

    @staticmethod
    def _component(value: str, field: str) -> str:
        """Accept one namespace component, never a path or traversal token."""
        if not isinstance(value, str) or not value or value in {".", ".."}:
            raise ValueError(f"{field} is required")
        if os.path.basename(value) != value or os.path.sep in value or (os.path.altsep and os.path.altsep in value):
            raise ValueError(f"{field} must be a single path component")
        return value

    def _contained(self, workspace_path: str) -> str:
        return require_contained_path(self.base_dir, workspace_path).resolved_path

    def create_workspace(self, execution_id: str, project_id: str = "default") -> str:
        safe_project = self._component(project_id, "project_id")
        safe_execution = self._component(execution_id, "execution_id")
        workspace_path = self._contained(os.path.join(safe_project, safe_execution))
        if os.path.exists(workspace_path):
            raise FileExistsError(f"Workspace {workspace_path} already exists")

        os.makedirs(workspace_path, mode=0o700)
        for name in ("input", "work", "output", "logs", "evidence", "result", "metadata", "cache"):
            os.makedirs(os.path.join(workspace_path, name), mode=0o700)
        return workspace_path

    def destroy_workspace(self, workspace_path: str):
        normalized = self._contained(workspace_path)
        if os.path.exists(normalized):
            shutil.rmtree(normalized, ignore_errors=True)

    def get_workspace_size(self, workspace_path: str) -> int:
        workspace_path = self._contained(workspace_path)
        total_size = 0
        for dirpath, _, filenames in os.walk(workspace_path):
            for filename in filenames:
                fp = os.path.join(dirpath, filename)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size

    def get_workspace_paths(self, workspace_path: str):
        """Return canonical workspace paths for task orchestration."""
        base = self._contained(workspace_path)
        return {
            "base": base,
            "input": os.path.join(base, "input"),
            "work": os.path.join(base, "work"),
            "output": os.path.join(base, "output"),
            "logs": os.path.join(base, "logs"),
            "evidence": os.path.join(base, "evidence"),
            "result": os.path.join(base, "result"),
            "metadata": os.path.join(base, "metadata"),
            "cache": os.path.join(base, "cache"),
        }
