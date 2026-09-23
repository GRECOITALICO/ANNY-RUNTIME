"""Batch 3: canonical Runtime admission and duplicate-route denial."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runtime.api.bridge import BridgeAuthError, BridgeRouter
from runtime.execution.deterministic_executor import DeterministicExecutor, ExecutorSecurityError
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import ExecutionStatus, Task, TaskExecutionContext
from runtime.mcp import ToolInvocationStatus, ToolRequest
from runtime.mcp.gateway import MCPGateway
from runtime.mcp.registry import ToolRegistry
from runtime.execution.capability import CapabilityRegistry
from runtime.security.execution_context import ExecutionContext
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


def _task(capability_id="filesystem.inspect", path="fixture.txt"):
    now = datetime.now(timezone.utc)
    return Task(
        task_id="batch3-task",
        capability_id=capability_id,
        account_id="batch3-account",
        project_id="batch3-project",
        input={"path": path},
        constraints={},
        deadline=now + timedelta(minutes=1),
        workspace_policy="keep",
        evidence_policy="required",
        requested_by="batch3-test",
        created_at=now,
    )


def _manager(tmp_path):
    return ExecutionManager(EphemeralWorkspaceManager(str(tmp_path / "workspaces")))


def test_canonical_execution_manager_path_admits_and_executes(tmp_path):
    manager = _manager(tmp_path)
    task = _task()
    context = manager.submit_task(task)
    assert context.admission_state == "AUTHORIZED"
    assert context.admitted_capability_id == "filesystem.inspect"
    assert context.admitted_executor_type == "DETERMINISTIC"

    target = Path(context.workspace_path) / "fixture.txt"
    target.write_text("ok")
    task.input["path"] = str(target)
    result = manager.execute_sync(context.execution_id)
    assert result.status == ExecutionStatus.SUCCEEDED


def test_capability_name_does_not_authorize_direct_executor(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "fixture.txt").write_text("ok")
    task = _task(path="fixture.txt")
    context = TaskExecutionContext(
        execution_id="direct-exec",
        task_id=task.task_id,
        account_id=task.account_id,
        project_id=task.project_id,
        capability_id=task.capability_id,
        workspace_path=str(root),
        environment={}, allowed_tools=[task.capability_id], deadline=task.deadline,
        resource_limits={}, network_policy="disabled", write_policy="read_only",
    )
    DeterministicExecutor(EphemeralWorkspaceManager(str(tmp_path / "unused"))).execute(task, context)
    assert context.status == ExecutionStatus.FAILED
    assert context.error_message == "CANONICAL_ADMISSION_REQUIRED"


def test_direct_worker_start_requires_canonical_admission(tmp_path):
    manager = _manager(tmp_path)
    task = _task()
    capability = manager.registry.get(task.capability_id)
    selection = manager.selector.select(task, capability, manager.policy)
    context = TaskExecutionContext(
        execution_id="direct-worker", task_id=task.task_id,
        account_id=task.account_id, project_id=task.project_id,
        capability_id=task.capability_id, workspace_path="", environment={},
        allowed_tools=[], deadline=task.deadline, resource_limits={},
        network_policy="disabled", write_policy="read_only",
    )
    worker = manager.worker_manager.create_worker(context, selection, task)
    with pytest.raises(ExecutorSecurityError, match="CANONICAL_ADMISSION_REQUIRED"):
        manager.worker_manager.start_worker(worker.worker_id, context, task, capability)


def test_forged_context_admission_cannot_replace_manager_admission(tmp_path):
    manager = _manager(tmp_path)
    task = _task()
    capability = manager.registry.get(task.capability_id)
    selection = manager.selector.select(task, capability, manager.policy)
    context = TaskExecutionContext(
        execution_id="forged-admission", task_id=task.task_id,
        account_id=task.account_id, project_id=task.project_id,
        capability_id=task.capability_id, workspace_path="", environment={},
        allowed_tools=[], deadline=task.deadline, resource_limits={},
        network_policy="disabled", write_policy="read_only",
        admission_id="forged", admission_state="AUTHORIZED",
        admitted_capability_id=task.capability_id,
        admitted_executor_type=selection.executor_type.value,
        admitted_executor_id=selection.executor_id,
    )
    worker = manager.worker_manager.create_worker(context, selection, task)
    with pytest.raises(ExecutorSecurityError, match="CANONICAL_ADMISSION_REQUIRED"):
        manager.worker_manager.start_worker(worker.worker_id, context, task, capability)


@pytest.mark.parametrize("capability_id", ["fabric.register", "unknown.capability"])
def test_disabled_and_unregistered_capabilities_cannot_enter_canonical_path(tmp_path, capability_id):
    manager = _manager(tmp_path)
    with pytest.raises(ValueError):
        manager.submit_task(_task(capability_id=capability_id))


def test_direct_mcp_and_tool_registry_do_not_grant_authorization(tmp_path):
    registry = ToolRegistry()
    assert registry.get_tool("filesystem.inspect") is not None  # implementation metadata only
    gateway = MCPGateway(registry, CapabilityRegistry(), workspace_path=str(tmp_path))
    request = ToolRequest.create(
        tool_id="filesystem.inspect", capability_id="filesystem.inspect",
        worker_id="forged-worker", execution_id="forged-execution",
        input_data={"path": "."}, deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    result = gateway.invoke(request)
    assert result.status == ToolInvocationStatus.DENIED
    assert result.error_message == "CANONICAL_WORKER_AUTHORIZATION_REQUIRED"


def test_bridge_rejects_expired_execution_context():
    now = datetime.now(timezone.utc)
    expired = ExecutionContext(
        "tenant", "account", "project", "anny", "runtime", "session", "actor",
        "operation", "execution", 1, now - timedelta(minutes=2), now - timedelta(minutes=1),
        "workspace", {"filesystem.inspect"},
    )
    with pytest.raises(BridgeAuthError):
        BridgeRouter({"execution_context": expired})._get_execution_context()
