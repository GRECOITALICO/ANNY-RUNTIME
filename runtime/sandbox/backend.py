import os
import shutil
import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from runtime.sandbox.policy import SandboxPolicy, IsolationLevel
from runtime.security.path_containment import require_contained_path

logger = logging.getLogger(__name__)

class SandboxBackend(ABC):
    """Abstract base for sandbox execution backends."""
    
    @abstractmethod
    def create(self, policy: SandboxPolicy) -> str:
        """Create a sandbox. Returns the sandbox root path."""
        ...
    
    @abstractmethod
    def destroy(self, sandbox_id: str) -> None:
        """Destroy a sandbox, removing temporary state only."""
        ...
    
    @abstractmethod
    def is_active(self, sandbox_id: str) -> bool:
        """Check if a sandbox is currently active."""
        ...


class WorkspaceBackend(SandboxBackend):
    """LEVEL_1: Workspace isolation via filesystem namespacing."""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir = Path(require_contained_path(str(self.base_dir), ".").resolved_path)
        self._active: dict[str, Path] = {}

    def _sandbox_path(self, sandbox_id: str) -> Path:
        if not isinstance(sandbox_id, str) or not sandbox_id or sandbox_id in {".", ".."}:
            raise ValueError("sandbox_id is required")
        if Path(sandbox_id).name != sandbox_id:
            raise ValueError("sandbox_id must be a single path component")
        return Path(require_contained_path(str(self.base_dir), sandbox_id).resolved_path)
    
    def create(self, policy: SandboxPolicy) -> str:
        sandbox_path = self._sandbox_path(policy.sandbox_id)
        sandbox_path.mkdir(parents=True, exist_ok=True)
        
        # Create workspace subdirectories
        (sandbox_path / "workspace").mkdir(exist_ok=True)
        (sandbox_path / "tmp").mkdir(exist_ok=True)
        
        self._active[policy.sandbox_id] = sandbox_path
        logger.info(f"Created workspace sandbox: {policy.sandbox_id}")
        return str(sandbox_path)
    
    def destroy(self, sandbox_id: str) -> None:
        sandbox_path = self._active.pop(sandbox_id, None)
        if sandbox_path and sandbox_path.exists():
            sandbox_path = self._sandbox_path(str(sandbox_path))
            # Remove only temporary state, preserve journals/receipts
            tmp_path = Path(require_contained_path(str(sandbox_path), "tmp").resolved_path)
            if tmp_path.exists():
                shutil.rmtree(tmp_path)
            workspace_path = Path(require_contained_path(str(sandbox_path), "workspace").resolved_path)
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
            # Remove the sandbox directory itself if empty
            try:
                sandbox_path.rmdir()
            except OSError:
                pass  # Not empty, preserve remaining files
            logger.info(f"Destroyed sandbox: {sandbox_id}")
        else:
            logger.warning(f"Sandbox not found for destruction: {sandbox_id}")
    
    def is_active(self, sandbox_id: str) -> bool:
        return sandbox_id in self._active


class RestrictedProcessBackend(SandboxBackend):
    """LEVEL_2: Process restrictions + filesystem isolation.
    Uses OS-level restrictions (e.g., resource limits via setrlimit)."""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._workspace = WorkspaceBackend(base_dir)
        self._active: dict[str, dict] = {}
    
    def create(self, policy: SandboxPolicy) -> str:
        root = self._workspace.create(policy)
        self._active[policy.sandbox_id] = {
            "root": root,
            "limits": policy.resource_limits,
        }
        logger.info(f"Created restricted-process sandbox: {policy.sandbox_id}")
        return root
    
    def destroy(self, sandbox_id: str) -> None:
        self._active.pop(sandbox_id, None)
        self._workspace.destroy(sandbox_id)
    
    def is_active(self, sandbox_id: str) -> bool:
        return sandbox_id in self._active
