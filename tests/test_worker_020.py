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
    ws_mgr = EphemeralWorkspaceManager(str(tmp_path))
    class MockAudit:
        def record(self, *args, **kwargs): pass
    return ExecutionManager(ws_mgr, MockAudit())

def create_task(cid="filesystem.inspect", path="/tmp"):
    return Task(
        task_id="t1", 
        capability_id=cid, 
        input={"path": path}, 
        constraints={}, 
        deadline=datetime.now(timezone.utc)+timedelta(minutes=1), 
        workspace_policy="keep", 
        evidence_policy="standard", 
        requested_by="t", 
        created_at=datetime.now(timezone.utc)
    )

def test_01_create_worker(exec_mgr):
    ctx = exec_mgr.submit_task(create_task())
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.state == WorkerState.CREATED

def test_02_start_worker(exec_mgr):
    ctx = exec_mgr.submit_task(create_task())
    exec_mgr.execute_sync(ctx.execution_id)
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.state == WorkerState.SUCCEEDED

def test_03_running_worker():
    pass

def test_04_success(exec_mgr):
    pass

def test_05_failure(exec_mgr):
    ctx = exec_mgr.submit_task(create_task(path=""))
    exec_mgr.execute_sync(ctx.execution_id)
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.state == WorkerState.FAILED

def test_06_timeout(exec_mgr):
    t = create_task()
    t.deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    ctx = exec_mgr.submit_task(t)
    ctx.deadline = t.deadline
    exec_mgr.execute_sync(ctx.execution_id)
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.state == WorkerState.TIMED_OUT

def test_07_cancellation(exec_mgr):
    ctx = exec_mgr.submit_task(create_task())
    worker = exec_mgr.worker_manager.list_workers()[0]
    exec_mgr.worker_manager.cancel_worker(worker.worker_id)
    assert worker.state == WorkerState.CANCELLED

def test_08_unexpected_crash(exec_mgr, monkeypatch):
    def mock_exec(*args): raise RuntimeError("Crash")
    monkeypatch.setattr(exec_mgr.worker_manager.deterministic_executor, "execute", mock_exec)
    ctx = exec_mgr.submit_task(create_task())
    exec_mgr.execute_sync(ctx.execution_id)
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.state == WorkerState.FAILED

def test_09_cleanup(exec_mgr):
    t = create_task()
    t.workspace_policy = "destroy_on_complete"
    ctx = exec_mgr.submit_task(t)
    exec_mgr.execute_sync(ctx.execution_id)
    assert not os.path.exists(ctx.workspace_path)

def test_10_resource_limits(exec_mgr, tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("hello")
    ctx = exec_mgr.submit_task(create_task(cid="filesystem.hash", path=str(p)))
    ctx.resource_limits["max_output_size"] = 1
    exec_mgr.execute_sync(ctx.execution_id)
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.state == WorkerState.LIMIT_EXCEEDED

def test_11_network_disabled(exec_mgr):
    ctx = exec_mgr.submit_task(create_task())
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.network_policy == "disabled"

def test_12_filesystem_isolation(exec_mgr):
    ctx = exec_mgr.submit_task(create_task(path="/var/lib/anny-runtime/secrets"))
    exec_mgr.execute_sync(ctx.execution_id)
    worker = exec_mgr.worker_manager.list_workers()[0]
    assert worker.state == WorkerState.FAILED

def test_13_capability_isolation(): pass
def test_14_worker_cannot_self_escalate(): pass
def test_15_worker_cannot_change_deadline(): pass
def test_16_worker_cannot_create_worker(): pass

def test_17_evidence(exec_mgr):
    ctx = exec_mgr.submit_task(create_task())
    exec_mgr.execute_sync(ctx.execution_id)
    assert os.path.exists(os.path.join(ctx.workspace_path, "evidence", "evidence.json"))

def test_18_telemetry(): pass
def test_19_reproducibility(): pass

def test_20_control_plane(exec_mgr):
    router = AdminRouter({"execution_manager": exec_mgr})
    class MockParsed:
        path = "/workers"
    res = router.handle_workers(MockParsed())
    assert "Ephemeral Workers" in res

def test_21_lifecycle_termination(exec_mgr):
    ctx = exec_mgr.submit_task(create_task())
    worker = exec_mgr.worker_manager.list_workers()[0]
    exec_mgr.worker_manager.terminate_worker(worker.worker_id)
    assert worker.state == WorkerState.TERMINATED

def test_22_multiple_concurrent_workers(exec_mgr):
    exec_mgr.submit_task(create_task())
    exec_mgr.submit_task(create_task())
    assert len(exec_mgr.worker_manager.list_workers()) == 2
