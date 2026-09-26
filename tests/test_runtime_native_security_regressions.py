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


def test_deterministic_filesystem_list_rejects_workspace_escape(tmp_path):
    from runtime.execution.deterministic_executor import DeterministicExecutor, ExecutorSecurityError
    from runtime.execution.models import TaskExecutionContext, ExecutionStatus

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()

    now = datetime.now(timezone.utc)
    ctx = TaskExecutionContext(
        execution_id="e",
        task_id="t",
        account_id="a",
        project_id="p",
        capability_id="filesystem.list",
        workspace_path=str(workspace),
        environment={},
        allowed_tools=[],
        deadline=now + timedelta(minutes=1),
        resource_limits={"max_output_size": 1024 * 1024},
        network_policy="none",
        write_policy="none",
        status=ExecutionStatus.QUEUED,
    )
    task = __import__("runtime.execution.models", fromlist=["Task"]).Task(
        task_id="t",
        capability_id="filesystem.list",
        account_id="a",
        project_id="p",
        input={"path": str(outside)},
        constraints={},
        deadline=now + timedelta(minutes=1),
        workspace_policy="retain",
        evidence_policy="required",
        requested_by="ANNY",
        created_at=now,
    )

    with pytest.raises(ExecutorSecurityError, match="outside execution workspace"):
        DeterministicExecutor(None)._execute_filesystem_list(task, ctx)


def test_execute_sync_preserves_governed_workspace_on_destroy_policy(tmp_path, monkeypatch):
    from runtime.execution.manager import ExecutionManager
    from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus, WorkerDefinition, WorkerState

    now = datetime.now(timezone.utc)
    workspace = tmp_path / "governed"
    workspace.mkdir()

    context = TaskExecutionContext(
        execution_id="exec-1",
        task_id="task-1",
        account_id="account",
        project_id="project",
        capability_id="repository.inspect",
        workspace_path=str(workspace),
        environment={},
        allowed_tools=[],
        deadline=now + timedelta(minutes=1),
        resource_limits={"max_output_size": 1024 * 1024},
        network_policy="none",
        write_policy="read_only",
        status=ExecutionStatus.QUEUED,
        governed_workspace_id="governed-1",
        generation=1,
    )
    task = Task(
        task_id="task-1",
        capability_id="repository.inspect",
        account_id="account",
        project_id="project",
        input={"path": str(workspace)},
        constraints={},
        deadline=now + timedelta(minutes=1),
        workspace_policy="destroy_on_complete",
        evidence_policy="required",
        requested_by="ANNY",
        created_at=now,
    )
    worker = WorkerDefinition(
        worker_id="wrk-1",
        execution_id="exec-1",
        task_id="task-1",
        account_id="account",
        project_id="project",
        capability_id="repository.inspect",
        executor_type="DETERMINISTIC",
        executor_id="deterministic",
        model_id=None,
        workspace_id=str(workspace),
        created_at=now,
        deadline=task.deadline,
        resource_limits={},
        network_policy="none",
        filesystem_policy="read_only",
        state=WorkerState.CREATED,
    )

    class CapRegistry:
        def get(self, _): return type("Cap", (), {})()

    class WorkerManager:
        def list_workers(self): return [worker]
        def start_worker(self, *_): context.status = ExecutionStatus.SUCCEEDED
        def terminate_worker(self, *_): worker.state = WorkerState.TERMINATED

    class WorkspaceManager:
        def __init__(self): self.destroyed = False
        def destroy_workspace(self, _): self.destroyed = True

    manager = ExecutionManager.__new__(ExecutionManager)
    manager._executions = {"exec-1": context}
    manager._tasks = {"exec-1": task}
    manager.registry = CapRegistry()
    manager.worker_manager = WorkerManager()
    manager.runtime_engine = None
    manager.continuity_engine = None
    manager.workspace_manager = WorkspaceManager()

    monkeypatch.setattr("runtime.core.config.get_data_dir", lambda: tmp_path / "data")
    result = manager.execute_sync("exec-1")

    assert result.status is ExecutionStatus.SUCCEEDED
    assert manager.workspace_manager.destroyed is False
