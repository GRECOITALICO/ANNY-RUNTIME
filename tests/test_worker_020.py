import pytest
import os
from datetime import datetime, timezone, timedelta
from runtime.execution.worker import WorkerManager
from runtime.execution.models import WorkerState, Task, TaskExecutionContext, ExecutionStatus
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.manager import ExecutionManager
from runtime.admin.routes import AdminRouter

@pytest.fixture
def exec_mgr(tmp_path):
    ws_mgr=EphemeralWorkspaceManager(str(tmp_path))
    class MockAudit:
        def record(self,*args,**kwargs): pass
    return ExecutionManager(ws_mgr,MockAudit())

def create_task(cid="filesystem.inspect",path="authorized-fixture"):
    return Task(task_id="t1",capability_id=cid,account_id="test-account",project_id="test-project",input={"path":path},constraints={},deadline=datetime.now(timezone.utc)+timedelta(minutes=1),workspace_policy="keep",evidence_policy="standard",requested_by="t",created_at=datetime.now(timezone.utc))

def test_01_create_worker(exec_mgr):
    exec_mgr.submit_task(create_task()); assert exec_mgr.worker_manager.list_workers()[0].state==WorkerState.CREATED
def _bind_file(ctx, task, name="fixture.txt", content="hello"):
    path = os.path.join(ctx.workspace_path, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    task.input["path"] = path
    return path

def test_02_start_worker(exec_mgr):
    task=create_task()
    ctx=exec_mgr.submit_task(task)
    _bind_file(ctx, task)
    exec_mgr.execute_sync(ctx.execution_id)
    assert exec_mgr.worker_manager.list_workers()[0].state==WorkerState.SUCCEEDED

def test_03_running_worker(exec_mgr, monkeypatch):
    observed=[]
    original=exec_mgr.worker_manager.deterministic_executor.execute
    def observe(task, context):
        observed.append(exec_mgr.worker_manager.list_workers()[0].state)
        return original(task, context)
    monkeypatch.setattr(exec_mgr.worker_manager.deterministic_executor, "execute", observe)
    task=create_task()
    ctx=exec_mgr.submit_task(task)
    _bind_file(ctx, task)
    exec_mgr.execute_sync(ctx.execution_id)
    assert WorkerState.RUNNING in observed

def test_04_success(exec_mgr):
    task=create_task()
    ctx=exec_mgr.submit_task(task)
    _bind_file(ctx, task)
    exec_mgr.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.SUCCEEDED
    assert ctx.result["is_file"] is True
def test_05_failure(exec_mgr):
    ctx=exec_mgr.submit_task(create_task(path="")); exec_mgr.execute_sync(ctx.execution_id); assert exec_mgr.worker_manager.list_workers()[0].state==WorkerState.FAILED
def test_06_timeout(exec_mgr):
    t=create_task(); t.deadline=datetime.now(timezone.utc)-timedelta(minutes=1); ctx=exec_mgr.submit_task(t); ctx.deadline=t.deadline; exec_mgr.execute_sync(ctx.execution_id); assert exec_mgr.worker_manager.list_workers()[0].state==WorkerState.TIMED_OUT
def test_07_cancellation(exec_mgr):
    ctx=exec_mgr.submit_task(create_task()); worker=exec_mgr.worker_manager.list_workers()[0]; exec_mgr.worker_manager.cancel_worker(worker.worker_id); assert worker.state==WorkerState.CANCELLED
def test_08_unexpected_crash(exec_mgr,monkeypatch):
    monkeypatch.setattr(exec_mgr.worker_manager.deterministic_executor,"execute",lambda *args: (_ for _ in ()).throw(RuntimeError("Crash")))
    ctx=exec_mgr.submit_task(create_task()); exec_mgr.execute_sync(ctx.execution_id); assert exec_mgr.worker_manager.list_workers()[0].state==WorkerState.FAILED; assert ctx.failure_reason.name=="EXECUTION_ERROR"
def test_09_cleanup(exec_mgr):
    t=create_task(); t.workspace_policy="destroy_on_complete"; ctx=exec_mgr.submit_task(t); _bind_file(ctx, t); exec_mgr.execute_sync(ctx.execution_id); assert not os.path.exists(ctx.workspace_path)
def test_10_resource_limits(exec_mgr):
    t=create_task(cid="filesystem.hash")
    ctx=exec_mgr.submit_task(t)
    _bind_file(ctx, t)
    ctx.resource_limits["max_output_size"]=1
    exec_mgr.execute_sync(ctx.execution_id)
    assert exec_mgr.worker_manager.list_workers()[0].state==WorkerState.LIMIT_EXCEEDED
def test_11_network_disabled(exec_mgr): assert exec_mgr.submit_task(create_task()).network_policy=="disabled"
def test_12_filesystem_isolation(exec_mgr):
    ctx=exec_mgr.submit_task(create_task(path="/var/lib/anny-runtime/secrets")); exec_mgr.execute_sync(ctx.execution_id); assert exec_mgr.worker_manager.list_workers()[0].state==WorkerState.FAILED
def test_13_capability_isolation(exec_mgr):
    with pytest.raises(ValueError, match="Capability is disabled"):
        exec_mgr.submit_task(create_task(cid="fabric.register"))

def test_14_worker_cannot_self_escalate(exec_mgr):
    task=create_task()
    ctx=exec_mgr.submit_task(task)
    worker=exec_mgr.worker_manager.list_workers()[0]
    worker.capability_id = "fabric.register"
    with pytest.raises(ValueError, match="cannot start"):
        exec_mgr.worker_manager.start_worker(worker.worker_id, ctx, task, exec_mgr.registry.get(task.capability_id))

def test_15_worker_cannot_change_deadline(exec_mgr):
    task=create_task()
    ctx=exec_mgr.submit_task(task)
    worker=exec_mgr.worker_manager.list_workers()[0]
    original=worker.deadline
    ctx.deadline = ctx.deadline + timedelta(hours=1)
    assert worker.deadline == original

def test_16_worker_cannot_create_worker(exec_mgr):
    task=create_task()
    ctx=exec_mgr.submit_task(task)
    worker=exec_mgr.worker_manager.list_workers()[0]
    assert not hasattr(worker, "create_worker")
    assert not hasattr(worker, "spawn_worker")
def test_17_evidence(exec_mgr):
    task=create_task()
    ctx=exec_mgr.submit_task(task)
    _bind_file(ctx, task)
    exec_mgr.execute_sync(ctx.execution_id)
    assert os.path.exists(os.path.join(ctx.workspace_path,"evidence","evidence.json"))

def test_18_telemetry(tmp_path):
    from runtime.telemetry.collector import TelemetryCollector
    collector=TelemetryCollector(str(tmp_path / "telemetry"))
    ws_mgr=EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    manager=ExecutionManager(ws_mgr, telemetry_collector=collector)
    task=create_task()
    ctx=manager.submit_task(task)
    _bind_file(ctx, task)
    manager.execute_sync(ctx.execution_id)
    events=collector.get_live()
    event_types={event.event_type for event in events}
    assert "task.routed" in event_types
    assert "execution.started" in event_types
    assert "execution.completed" in event_types

def test_19_reproducibility(exec_mgr):
    hashes=[]
    for _ in range(2):
        task=create_task(cid="filesystem.hash")
        ctx=exec_mgr.submit_task(task)
        _bind_file(ctx, task, content="stable")
        exec_mgr.execute_sync(ctx.execution_id)
        hashes.append(ctx.result["sha256"])
    assert hashes[0] == hashes[1]
def test_20_control_plane(exec_mgr):
    router=AdminRouter({"execution_manager":exec_mgr})
    class MockParsed: path="/workers"
    assert "Ephemeral Workers" in router.handle_workers(MockParsed())
def test_21_lifecycle_termination(exec_mgr):
    ctx=exec_mgr.submit_task(create_task()); worker=exec_mgr.worker_manager.list_workers()[0]; exec_mgr.worker_manager.terminate_worker(worker.worker_id); assert worker.state==WorkerState.TERMINATED
def test_22_multiple_concurrent_workers(exec_mgr):
    exec_mgr.submit_task(create_task()); exec_mgr.submit_task(create_task()); assert len(exec_mgr.worker_manager.list_workers())==2
def test_23_unsupported_executor_fails_closed(exec_mgr):
    class Sel:
        class TypeVal: value="UNSUPPORTED_EXECUTOR"
        executor_type=TypeVal(); executor_id="frontier"; model_id="mod"
    class Cap: required_tools=[]; network_policy="disabled"
    ctx=TaskExecutionContext(execution_id="ex-unsupported",task_id="t-u",account_id="a",project_id="p",capability_id="cap",workspace_path="",environment={},allowed_tools=[],deadline=datetime.now(timezone.utc)+timedelta(minutes=5),resource_limits={},network_policy="disabled",write_policy="allow")
    task=Task("t-u","cap","a","p",{}, {},datetime.now(timezone.utc)+timedelta(minutes=5),"","","me",datetime.now(timezone.utc))
    worker=exec_mgr.worker_manager.create_worker(ctx,Sel(),task); exec_mgr.worker_manager.start_worker(worker.worker_id,ctx,task,Cap())
    assert worker.state==WorkerState.FAILED and ctx.status==ExecutionStatus.FAILED and ctx.failure_reason.name=="UNSUPPORTED_EXECUTOR"
def test_24_local_model_unavailable_fails_closed(exec_mgr,monkeypatch):
    monkeypatch.delenv("QWEN_MODEL_PATH",raising=False)
    class TypeVal: value="LOCAL_MODEL"
    class Sel: executor_type=TypeVal(); executor_id="local"; model_id="qwen"
    class Cap: required_tools=[]; network_policy="disabled"
    ctx=TaskExecutionContext(execution_id="ex-local",task_id="t-l",account_id="a",project_id="p",capability_id="cap",workspace_path="",environment={},allowed_tools=[],deadline=datetime.now(timezone.utc)+timedelta(minutes=5),resource_limits={},network_policy="disabled",write_policy="allow")
    task=Task("t-l","cap","a","p",{}, {},datetime.now(timezone.utc)+timedelta(minutes=5),"","","me",datetime.now(timezone.utc))
    worker=exec_mgr.worker_manager.create_worker(ctx,Sel(),task); exec_mgr.worker_manager.start_worker(worker.worker_id,ctx,task,Cap())
    assert worker.state==WorkerState.FAILED and ctx.status==ExecutionStatus.FAILED and ctx.failure_reason.name=="EXECUTION_ERROR" and ctx.error_message=="Local model unavailable"
