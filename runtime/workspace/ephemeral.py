import tempfile
import shutil
import os
import time

class EphemeralWorkspaceManager:
    def __init__(self, base_dir: str = "/tmp/anny-workspaces"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        # Secure the base directory
        os.chmod(self.base_dir, 0o700)

    def create_workspace(self, execution_id: str) -> str:
        """
        Creates a securely isolated ephemeral workspace for an execution.
        Raises an error if the workspace already exists.
        """
        workspace_path = os.path.join(self.base_dir, execution_id)
        if os.path.exists(workspace_path):
            raise FileExistsError(f"Workspace {workspace_path} already exists")
        
        os.makedirs(workspace_path, mode=0o700)
        
        # Pre-create essential directories
        os.makedirs(os.path.join(workspace_path, "logs"), mode=0o700)
        os.makedirs(os.path.join(workspace_path, "evidence"), mode=0o700)
        os.makedirs(os.path.join(workspace_path, "result"), mode=0o700)
        os.makedirs(os.path.join(workspace_path, "metadata"), mode=0o700)
        
        return workspace_path

    def destroy_workspace(self, workspace_path: str):
        """
        Securely destroys the ephemeral workspace and all contents.
        """
        # Security check to prevent rm -rf /
        if not workspace_path or not workspace_path.startswith(self.base_dir):
            raise ValueError(f"Cannot destroy path outside ephemeral base: {workspace_path}")
            
        if os.path.exists(workspace_path):
            shutil.rmtree(workspace_path, ignore_errors=True)

    def get_workspace_size(self, workspace_path: str) -> int:
        """
        Returns the total size of the workspace in bytes.
        """
        total_size = 0
        for dirpath, _, filenames in os.walk(workspace_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size
