import os
import shutil


class EphemeralWorkspaceManager:
    """Manage bounded local workspaces used by Runtime executions."""

    def __init__(self, base_dir: str = "/tmp/anny-workspaces"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        os.chmod(self.base_dir, 0o700)

    def create_workspace(self, execution_id: str, project_id: str = "default") -> str:
        if not execution_id or not project_id:
            raise ValueError("execution_id and project_id are required")
        safe_project = os.path.basename(project_id)
        workspace_path = os.path.abspath(os.path.join(self.base_dir, safe_project, execution_id))
        if not workspace_path.startswith(self.base_dir + os.sep):
            raise ValueError("Workspace path escapes ephemeral base")
        if os.path.exists(workspace_path):
            raise FileExistsError(f"Workspace {workspace_path} already exists")

        os.makedirs(workspace_path, mode=0o700)
        for name in ("input", "work", "output", "logs", "evidence", "result", "metadata", "cache"):
            os.makedirs(os.path.join(workspace_path, name), mode=0o700)
        return workspace_path

    def destroy_workspace(self, workspace_path: str):
        normalized = os.path.abspath(workspace_path)
        if not normalized.startswith(self.base_dir + os.sep):
            raise ValueError(f"Cannot destroy path outside ephemeral base: {workspace_path}")
        if os.path.exists(normalized):
            shutil.rmtree(normalized, ignore_errors=True)

    def get_workspace_size(self, workspace_path: str) -> int:
        total_size = 0
        for dirpath, _, filenames in os.walk(workspace_path):
            for filename in filenames:
                fp = os.path.join(dirpath, filename)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size

    def get_workspace_paths(self, workspace_path: str):
        """Return canonical workspace paths for task orchestration."""
        base = os.path.abspath(workspace_path)
        if not base.startswith(self.base_dir + os.sep):
            raise ValueError("Workspace path escapes ephemeral base")
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
