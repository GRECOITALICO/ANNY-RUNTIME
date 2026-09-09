import os
import json
from datetime import datetime, timezone, timedelta
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import Task, ExecutionStatus

def run_task(exec_mgr, cap_id, path):
    print(f"\n--- Running {cap_id} on {path} ---")
    task = Task(
        task_id=f"fase13-{cap_id.replace('.', '-')}",
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
    print(f"Task submitted. Execution ID: {ctx.execution_id}")
    exec_mgr.execute_sync(ctx.execution_id)
    print(f"Status: {ctx.status.value}")
    
    if ctx.status == ExecutionStatus.SUCCEEDED:
        print(f"Result: {json.dumps(ctx.result)}")
    else:
        print(f"Failed: {ctx.failure_reason.value} - {ctx.error_message}")
        
    ev_path = os.path.join(ctx.workspace_path, "evidence", "evidence.json")
    if os.path.exists(ev_path):
        print("Evidence file generated.")
    else:
        print("Evidence file MISSING!")
        
    print("Cleaning up workspace...")
    exec_mgr.workspace_manager.destroy_workspace(ctx.workspace_path)
    
def main():
    print("FASE 13: REAL EXECUTIONS")
    base_dir = "/tmp/anny-workspaces-fase13"
    ws_mgr = EphemeralWorkspaceManager(base_dir=base_dir)
    exec_mgr = ExecutionManager(ws_mgr)
    
    test_target = "/tmp/anny_fase13_test.txt"
    with open(test_target, "w") as f:
        f.write("Hello FASE 13")
        
    run_task(exec_mgr, "filesystem.inspect", test_target)
    run_task(exec_mgr, "filesystem.hash", test_target)
    run_task(exec_mgr, "repository.inspect", "/tmp")
    
    os.remove(test_target)
    print("\nFASE 13 SUCCESSFUL.")

if __name__ == "__main__":
    main()
