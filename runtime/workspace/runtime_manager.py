"""Composite Runtime workspace manager.

Bridges the existing governed WorkspaceManager with the execution manager's
ephemeral-workspace protocol. The governed workspace remains authoritative for
context ownership; ephemeral execution directories remain implementation
storage only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.workspace.manager import Workspace, WorkspaceManager


class RuntimeWorkspaceManager:
    def __init__(self, base_dir: str | Path, config: Optional[dict] = None) -> None:
        root = Path(base_dir)
        self.governed = WorkspaceManager(str(root / "governed"), config or {})
        self.ephemeral = EphemeralWorkspaceManager(str(root / "executions"))

    def status(self, context, workspace_id: str) -> Optional[Workspace]:
        return self.governed.status(context, workspace_id)

    def create(
        self,
        context,
        actor_scope,
        repository: str,
        source_revision: str,
    ) -> Workspace:
        return self.governed.create(
            context,
            actor_scope=actor_scope,
            repository=repository,
            source_revision=source_revision,
        )

    def lock(self, context, workspace_id: str) -> bool:
        return self.governed.lock(context, workspace_id)

    def unlock(self, context, workspace_id: str) -> bool:
        return self.governed.unlock(context, workspace_id)

    def recover(self, context, workspace_id: str) -> bool:
        return self.governed.recover(context, workspace_id)

    def destroy_governed(self, context, workspace_id: str) -> bool:
        return self.governed.destroy(context, workspace_id)

    # Compatibility protocol used by ExecutionManager's unbound legacy path.
    def create_workspace(self, execution_id: str, project_id: str = "default") -> str:
        return self.ephemeral.create_workspace(execution_id, project_id)

    def destroy_workspace(self, workspace_path: str) -> None:
        self.ephemeral.destroy_workspace(workspace_path)

    def get_workspace_size(self, workspace_path: str) -> int:
        normalized = Path(workspace_path).resolve()
        allowed_roots = (
            self.governed.base_dir.resolve(),
            Path(self.ephemeral.base_dir).resolve(),
        )
        if not any(
            normalized == root or normalized.is_relative_to(root)
            for root in allowed_roots
        ):
            raise ValueError("Workspace path is outside Runtime-managed workspace roots")

        total = 0
        if normalized.exists():
            for path in normalized.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
        return total

    def get_workspace_paths(self, workspace_path: str) -> Dict[str, str]:
        normalized = Path(workspace_path).resolve()
        allowed_roots = (
            self.governed.base_dir.resolve(),
            Path(self.ephemeral.base_dir).resolve(),
        )
        if not any(
            normalized == root or normalized.is_relative_to(root)
            for root in allowed_roots
        ):
            raise ValueError("Workspace path is outside Runtime-managed workspace roots")
        base = str(normalized)
        return {
            "base": base,
            "input": str(normalized / "input"),
            "work": str(normalized / "work"),
            "output": str(normalized / "output"),
            "logs": str(normalized / "logs"),
            "evidence": str(normalized / "evidence"),
            "result": str(normalized / "result"),
            "metadata": str(normalized / "metadata"),
            "cache": str(normalized / "cache"),
        }
