import os
import json
from datetime import datetime, timezone, timedelta
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import Task, ExecutionStatus

def main():
    print("FASE 12: REAL LOCAL EXECUTION")
    
    # 1. Setup Manager
    base_dir = "/tmp/anny-workspaces-fase12"
    ws_mgr = EphemeralWorkspaceManager(base_dir=base_dir)
    exec_mgr = ExecutionManager(ws_mgr)
    
    # 2. Setup Harmless path
    test_target = "/tmp/anny_fase12_harmless.txt"
    with open(test_target, "w") as f:
        f.write("Hello FASE 12")
        
    # 3. Create Task
    task = Task(
        task_id="fase12-test-task",
        capability_id="filesystem.inspect",
        input={"path": test_target},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        workspace_policy="keep",  # Keep to inspect evidence, cleanup later
        evidence_policy="standard",
        requested_by="operator",
        created_at=datetime.now(timezone.utc)
    )
    
    # 4. Context Creation
    ctx = exec_mgr.submit_task(task)
    print(f"Task submitted. Execution ID: {ctx.execution_id}")
    print(f"Workspace path: {ctx.workspace_path}")
    
    # 5. Execute
    exec_mgr.execute_sync(ctx.execution_id)
    
    print(f"Status: {ctx.status.value}")
    if ctx.status == ExecutionStatus.SUCCEEDED:
        print(f"Result: {json.dumps(ctx.result)}")
    else:
        print(f"Failed: {ctx.failure_reason.value} - {ctx.error_message}")
        return
        
    # 6. Verify Evidence
    ev_path = os.path.join(ctx.workspace_path, "evidence", "evidence.json")
    if os.path.exists(ev_path):
        print("Evidence file generated.")
    else:
        print("Evidence file MISSING!")
        
    # 7. Cleanup
    print("Cleaning up workspace...")
    ws_mgr.destroy_workspace(ctx.workspace_path)
    if not os.path.exists(ctx.workspace_path):
        print("Cleanup successful.")
    else:
        print("Cleanup failed.")
        
    os.remove(test_target)
    print("FASE 12 SUCCESSFUL.")

if __name__ == "__main__":
    main()
