import pytest
import os
import time
from datetime import datetime, timezone, timedelta
from runtime.execution.models import Task, ExecutionStatus, FailureReason
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.manager import ExecutionManager
from runtime.execution.deterministic_executor import ExecutorSecurityError, ExecutorLimitsExceeded

@pytest.fixture
def execution_manager(tmp_path):
    ws_manager = EphemeralWorkspaceManager(base_dir=str(tmp_path / "workspaces"))
    return ExecutionManager(ws_manager)

def create_mock_task(cap_id="filesystem.inspect", path="/tmp"):
    return Task(
        task_id="task-018",
        capability_id=cap_id,
        input={"path": path},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        workspace_policy="keep",
        evidence_policy="standard",
        requested_by="test",
        created_at=datetime.now(timezone.utc)
    )

def test_1_task_creation():
    t = create_mock_task()
    assert t.task_id == "task-018"
    assert t.capability_id == "filesystem.inspect"

def test_2_execution_context_creation(execution_manager):
    t = create_mock_task()
    ctx = execution_manager.submit_task(t)
    assert ctx.task_id == t.task_id
    assert ctx.status == ExecutionStatus.QUEUED

def test_3_workspace_isolation(execution_manager):
    t = create_mock_task()
    ctx = execution_manager.submit_task(t)
    assert os.path.exists(ctx.workspace_path)
    # Check isolation structure
    assert os.path.exists(os.path.join(ctx.workspace_path, "logs"))
    assert os.path.exists(os.path.join(ctx.workspace_path, "evidence"))
    assert os.path.exists(os.path.join(ctx.workspace_path, "result"))
    assert os.path.exists(os.path.join(ctx.workspace_path, "metadata"))

def test_4_deterministic_executor_success(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.SUCCEEDED
    assert ctx.result["size_bytes"] == 5

def test_5_executor_timeout(execution_manager):
    t = create_mock_task()
    # Force deadline to the past
    t.deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    ctx = execution_manager.submit_task(t)
    # Context deadline gets copied from task
    ctx.deadline = t.deadline
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.TIMED_OUT
    assert ctx.failure_reason == FailureReason.TIMEOUT

def test_6_output_limit(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    # Force very small output size
    ctx.resource_limits["max_output_size"] = 1
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.LIMIT_EXCEEDED
    assert ctx.failure_reason == FailureReason.LIMIT_EXCEEDED

def test_7_workspace_limit(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    # Force tiny workspace size
    ctx.resource_limits["max_workspace_size"] = 1
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.LIMIT_EXCEEDED
    assert ctx.failure_reason == FailureReason.LIMIT_EXCEEDED
    assert "Workspace size limit exceeded" in ctx.error_message

def test_8_network_disabled(execution_manager):
    t = create_mock_task()
    ctx = execution_manager.submit_task(t)
    assert ctx.network_policy == "disabled"

def test_9_denied_path(execution_manager):
    t = create_mock_task(path="/var/lib/anny-runtime/secrets")
    ctx = execution_manager.submit_task(t)
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.FAILED
    assert ctx.failure_reason == FailureReason.AUTHORIZATION_DENIED

def test_10_evidence_generated(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    execution_manager.execute_sync(ctx.execution_id)
    ev_file = os.path.join(ctx.workspace_path, "evidence", "evidence.json")
    assert os.path.exists(ev_file)

def test_11_result_hash(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    execution_manager.execute_sync(ctx.execution_id)
    rep_file = os.path.join(ctx.workspace_path, "metadata", "reproducibility.json")
    assert os.path.exists(rep_file)

def test_12_cleanup_after_success(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    t.workspace_policy = "destroy_on_complete"
    ctx = execution_manager.submit_task(t)
    ws_path = ctx.workspace_path
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.SUCCEEDED
    assert not os.path.exists(ws_path)

def test_13_cleanup_after_failure(execution_manager):
    # Invalid/unknown capability is now rejected at submit time
    t = create_mock_task(cap_id="invalid.cap")
    t.workspace_policy = "destroy_on_complete"
    with pytest.raises(ValueError, match="Unknown capability"):
        execution_manager.submit_task(t)

def test_14_lifetime_termination(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.completed_at is not None

def test_15_cannot_modify_deadline(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    original_deadline = ctx.deadline
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.deadline == original_deadline

def test_16_cannot_escalate_capability(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(cap_id="admin.escalate")
    # Unknown/unauthorized capability is rejected at submit time
    with pytest.raises(ValueError, match="Unknown capability"):
        execution_manager.submit_task(t)

def test_17_reproducible_execution(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t1 = create_mock_task(path=str(safe_path))
    ctx1 = execution_manager.submit_task(t1)
    execution_manager.execute_sync(ctx1.execution_id)
    
    t2 = create_mock_task(path=str(safe_path))
    ctx2 = execution_manager.submit_task(t2)
    execution_manager.execute_sync(ctx2.execution_id)
    
    assert ctx1.result == ctx2.result

def test_18_control_plane_visibility(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    execution_manager.submit_task(t)
    all_exec = execution_manager.get_all_executions()
    assert len(all_exec) == 1
    assert all_exec[0].status == ExecutionStatus.QUEUED
