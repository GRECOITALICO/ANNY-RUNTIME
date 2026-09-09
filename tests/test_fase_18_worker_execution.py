import os
import json
from datetime import datetime, timezone, timedelta
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import Task, WorkerState

def run_task(exec_mgr, cap_id, path):
    print(f"\n--- Running {cap_id} on {path} ---")
    task = Task(
        task_id=f"fase18-{cap_id.replace('.', '-')}",
        capability_id=cap_id,
        input={"path": path},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        workspace_policy="keep",
        evidence_policy="standard",
        requested_by="operator",
        created_at=datetime.now(timezone.utc)
    )
    
    ctx = exec_mgr.submit_task(task)
    
    worker = exec_mgr.worker_manager.list_workers()[-1]
    print(f"Worker created. ID: {worker.worker_id}, State: {worker.state.value}")
    
    exec_mgr.execute_sync(ctx.execution_id)
    
    print(f"Worker finished. State: {worker.state.value}")
    
    if worker.state == WorkerState.SUCCEEDED:
        print(f"Result: {json.dumps(ctx.result)}")
    else:
        fail_val = ctx.failure_reason.value if ctx.failure_reason else "UNKNOWN"
        print(f"Failed: {fail_val} - {ctx.error_message}")
        
    ev_path = os.path.join(ctx.workspace_path, "evidence", "evidence.json")
    if os.path.exists(ev_path):
        print("Evidence file generated.")
    else:
        print("Evidence file MISSING!")
        
    print("Cleaning up workspace...")
    exec_mgr.workspace_manager.destroy_workspace(ctx.workspace_path)
    
def main():
    print("FASE 18: WORKER EXECUTION")
    class MockAudit:
        def record(self, *args, **kwargs):
            pass
            
    base_dir = "/tmp/anny-workspaces-fase18"
    ws_mgr = EphemeralWorkspaceManager(base_dir=base_dir)
    exec_mgr = ExecutionManager(ws_mgr, MockAudit())
    
    test_target = "/tmp/anny_fase18_test.txt"
    with open(test_target, "w") as f:
        f.write("Hello FASE 18 Worker")
        
    run_task(exec_mgr, "filesystem.inspect", test_target)
    run_task(exec_mgr, "filesystem.hash", test_target)
    
    os.remove(test_target)
    print("\nFASE 18 SUCCESSFUL.")

if __name__ == "__main__":
    main()
