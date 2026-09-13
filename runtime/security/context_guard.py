from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .execution_context import ExecutionContext
    from ..workspace.manager import Workspace

class ContextAccessError(Exception):
    code = "CONTEXT_ACCESS_DENIED"

@dataclass
class ContextGuard:
    @staticmethod
    def assert_account(ctx: 'ExecutionContext', resource_account_id: str) -> None:
        if ctx.account_id != resource_account_id:
            raise ContextAccessError(f"CONTEXT_ACCESS_DENIED: Account mismatch. Context={ctx.account_id}, Resource={resource_account_id}")

    @staticmethod
    def assert_project(ctx: 'ExecutionContext', resource_project_id: str) -> None:
        if ctx.project_id != resource_project_id:
            raise ContextAccessError(f"CONTEXT_ACCESS_DENIED: Project mismatch. Context={ctx.project_id}, Resource={resource_project_id}")

    @staticmethod
    def assert_workspace(ctx: 'ExecutionContext', workspace: 'Workspace') -> None:
        if getattr(workspace, 'project_id', None) != ctx.project_id:
            raise ContextAccessError(f"CONTEXT_ACCESS_DENIED: Workspace project mismatch. Context={ctx.project_id}, Workspace Project={getattr(workspace, 'project_id', None)}")

    @staticmethod
    def assert_credential_ref(ctx: 'ExecutionContext', ref: str) -> None:
        if not ref.startswith(f"acct-{ctx.account_id}-"):
            raise ContextAccessError(f"CONTEXT_ACCESS_DENIED: Invalid credential namespace. Context={ctx.account_id}, Ref={ref}")

    @staticmethod
    def assert_fabric_namespace(ctx: 'ExecutionContext', namespace: str) -> None:
        if not namespace.startswith(f"{ctx.project_id}/"):
            raise ContextAccessError(f"CONTEXT_ACCESS_DENIED: Fabric namespace mismatch. Context={ctx.project_id}, Namespace={namespace}")
