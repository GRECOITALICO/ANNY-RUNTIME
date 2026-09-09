import os
import json
from datetime import datetime, timezone, timedelta
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import Task, ExecutionStatus

def main():
    print("FASE 14: REPRODUCIBILITY")
    base_dir = "/tmp/anny-workspaces-fase14"
    ws_mgr = EphemeralWorkspaceManager(base_dir=base_dir)
    exec_mgr = ExecutionManager(ws_mgr)
    
    test_target = "/tmp/anny_fase14_test.txt"
    with open(test_target, "w") as f:
        f.write("Reproducible content")
        
    def create_task():
        return Task(
            task_id="fase14-reproducibility",
            capability_id="filesystem.hash",
            input={"path": test_target},
            constraints={},
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            workspace_policy="keep",
            evidence_policy="standard",
            requested_by="operator",
            created_at=datetime.now(timezone.utc)
        )
        
    # Execution 1
    t1 = create_task()
    ctx1 = exec_mgr.submit_task(t1)
    exec_mgr.execute_sync(ctx1.execution_id)
    
    rep1_path = os.path.join(ctx1.workspace_path, "metadata", "reproducibility.json")
    with open(rep1_path, "r") as f:
        rep1 = json.load(f)
        
    # Execution 2
    t2 = create_task()
    ctx2 = exec_mgr.submit_task(t2)
    exec_mgr.execute_sync(ctx2.execution_id)
    
    rep2_path = os.path.join(ctx2.workspace_path, "metadata", "reproducibility.json")
    with open(rep2_path, "r") as f:
        rep2 = json.load(f)
        
    print(f"Exec 1 Input Hash:  {rep1['input_hash']}")
    print(f"Exec 2 Input Hash:  {rep2['input_hash']}")
    print(f"Exec 1 Output Hash: {rep1['output_hash']}")
    print(f"Exec 2 Output Hash: {rep2['output_hash']}")
    
    assert rep1['input_hash'] == rep2['input_hash']
    assert rep1['output_hash'] == rep2['output_hash']
    
    print("\nFASE 14 SUCCESSFUL: Deterministic capabilities yield identical hashes.")
    
    ws_mgr.destroy_workspace(ctx1.workspace_path)
    ws_mgr.destroy_workspace(ctx2.workspace_path)
    os.remove(test_target)

if __name__ == "__main__":
    main()
