from datetime import datetime, timedelta, timezone

import pytest

from runtime.filesystem.service import FilesystemService
from runtime.security.execution_context import ExecutionContext
from runtime.shell.executor import ShellEffectClass, ShellExecutor


def context():
    now = datetime.now(timezone.utc)
    return ExecutionContext(
        tenant_id="tenant",
        account_id="account",
        project_id="project",
        anny_instance_id="anny",
        runtime_id="runtime",
        session_id="session",
        actor_id="ANNY",
        operation_id="operation",
        execution_id="execution",
        generation=1,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=5),
        workspace_id="workspace",
        capabilities={"PROCESS_EXECUTION", "FILE_READ", "FILE_WRITE", "GIT_READ", "GIT_WRITE"},
    )


def test_shell_rejects_command_chaining():
    with pytest.raises(PermissionError):
        ShellExecutor._validate_command_syntax("git status && cat secret")


def test_shell_rejects_redirection():
    with pytest.raises(PermissionError):
        ShellExecutor._validate_command_syntax("cat file > output")


def test_git_remote_requires_network_capability():
    required = ShellExecutor._required_capabilities(
        "git push origin branch",
        ShellEffectClass.REMOTE_MUTATION,
    )
    assert required == {
        "PROCESS_EXECUTION",
        "REMOTE_REPOSITORY_MUTATION",
        "NETWORK_ACCESS",
    }


class FakeWorkspaceManager:
    def __init__(self, local_path):
        from runtime.workspace.manager import Workspace, WorkspaceState
        self.workspace = Workspace(
            workspace_id="workspace",
            tenant_id="tenant",
            project_id="project",
            actor_scope=["ANNY"],
            repository="repo",
            source_revision="HEAD",
            state=WorkspaceState.READY,
            generation=1,
            local_path=local_path,
            created_at="now",
        )

    def status(self, ctx, workspace_id):
        return self.workspace


def test_filesystem_prefix_collision_is_rejected(tmp_path):
    base = tmp_path / "workspace"
    sibling = tmp_path / "workspace-escape"
    base.mkdir()
    sibling.mkdir()

    service = FilesystemService(FakeWorkspaceManager(str(base)))
    with pytest.raises(ValueError, match="OUTSIDE_WORKSPACE"):
        service.read(context(), "../workspace-escape/file.txt")


def test_deterministic_executor_rejects_workspace_escape(tmp_path):
    from runtime.execution.deterministic_executor import DeterministicExecutor, ExecutorSecurityError

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    executor = DeterministicExecutor(None)

    with pytest.raises(ExecutorSecurityError, match="outside execution workspace"):
        executor._enforce_path(str(outside), type("C", (), {"workspace_path": str(workspace)})())
