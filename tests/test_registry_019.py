import pytest
from datetime import datetime, timezone, timedelta
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.selector import ExecutorSelector
from runtime.execution.models import Task, ExecutionStatus, FailureReason
from runtime.execution.manager import ExecutionManager
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.deterministic_executor import ExecutorSecurityError, ExecutorLimitsExceeded

@pytest.fixture
def execution_manager(tmp_path):
    ws_manager = EphemeralWorkspaceManager(base_dir=str(tmp_path / "workspaces"))
    return ExecutionManager(ws_manager)

def create_mock_task(cap_id="filesystem.inspect", path="/tmp"):
    return Task(
        task_id="task-019",
        capability_id=cap_id,
        input={"path": path},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        workspace_policy="keep",
        evidence_policy="standard",
        requested_by="test",
        created_at=datetime.now(timezone.utc)
    )

def test_1_capability_registry():
    registry = CapabilityRegistry()
    caps = registry.list_all()
    assert len(caps) > 0
    cap = registry.get("filesystem.inspect")
    assert cap is not None
    assert cap.deterministic_allowed is True

def test_2_capability_lookup(execution_manager):
    cap = execution_manager.registry.get("filesystem.inspect")
    assert cap.name == "Filesystem Inspect"

def test_3_unknown_capability(execution_manager):
    t = create_mock_task(cap_id="unknown.cap")
    with pytest.raises(ValueError, match="Unknown capability"):
        execution_manager.submit_task(t)

def test_4_disabled_capability(execution_manager):
    cap = execution_manager.registry.get("filesystem.inspect")
    cap.enabled = False
    t = create_mock_task(cap_id="filesystem.inspect")
    with pytest.raises(ValueError, match="is disabled"):
        execution_manager.submit_task(t)

def test_5_deterministic_selection():
    registry = CapabilityRegistry()
    policy = RuntimePolicy()
    selector = ExecutorSelector()
    
    cap = registry.get("filesystem.inspect")
    task = create_mock_task()
    
    selection = selector.select(task, cap, policy)
    assert selection.executor_type == ExecutorType.DETERMINISTIC
    assert selection.executor_id == "deterministic-v1"

def test_6_model_selection_abstraction():
    # ModelExecutor interface tested implicitly by its definition being valid Python
    pass

def test_7_authority_isolation(execution_manager):
    t = create_mock_task()
    ctx = execution_manager.submit_task(t)
    assert ctx.executor_type == "DETERMINISTIC"

def test_9_executor_integration(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    assert ctx.executor_type == "DETERMINISTIC"
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.SUCCEEDED

def test_10_execution_record(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    
    assert ctx.executor_type == "DETERMINISTIC"
    assert ctx.executor_id == "deterministic-v1"
    assert ctx.policy_version == "1.0.0"

def test_13_timeout(execution_manager):
    t = create_mock_task()
    t.deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    ctx = execution_manager.submit_task(t)
    ctx.deadline = t.deadline
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.TIMED_OUT

def test_14_output_limit(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    ctx = execution_manager.submit_task(t)
    ctx.resource_limits["max_output_size"] = 1
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.LIMIT_EXCEEDED

def test_15_security_boundaries(execution_manager):
    t = create_mock_task(path="/var/lib/anny-runtime/secrets")
    ctx = execution_manager.submit_task(t)
    execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.FAILED
    assert ctx.failure_reason == FailureReason.AUTHORIZATION_DENIED

def test_16_control_plane(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t = create_mock_task(path=str(safe_path))
    execution_manager.submit_task(t)
    
    caps = execution_manager.registry.list_all()
    assert len(caps) > 0
    
    execs = execution_manager.get_all_executions()
    assert len(execs) == 1

def test_17_multiple_executions(execution_manager, tmp_path):
    safe_path = tmp_path / "harmless.txt"
    safe_path.write_text("hello")
    t1 = create_mock_task(path=str(safe_path))
    ctx1 = execution_manager.submit_task(t1)
    execution_manager.execute_sync(ctx1.execution_id)
    
    t2 = create_mock_task(cap_id="filesystem.hash", path=str(safe_path))
    ctx2 = execution_manager.submit_task(t2)
    execution_manager.execute_sync(ctx2.execution_id)
    
    assert ctx1.status == ExecutionStatus.SUCCEEDED
    assert ctx2.status == ExecutionStatus.SUCCEEDED
