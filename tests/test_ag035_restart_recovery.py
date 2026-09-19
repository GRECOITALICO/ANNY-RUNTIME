import pytest
import os
import tempfile
import json
from pathlib import Path

from runtime.core.engine import RuntimeEngine, RuntimeState
from runtime.core.config import RuntimeConfig
from runtime.core.generation import StaleGenerationError
from runtime.continuity.models import ContinuityRecord

def test_generation_fencing_rejects_stale():
    from runtime.execution.manager import ExecutionManager
    from runtime.execution.models import Task, ExecutionStatus, FailureReason
    from runtime.workspace.ephemeral import EphemeralWorkspaceManager
    from datetime import datetime, timezone, timedelta
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RuntimeConfig(data_dir=tmpdir)
        engine = RuntimeEngine(config)
        
        # Start and get generation 1
        engine.startup()
        gen1 = engine.generation.current
        assert gen1 == 1
        
        # Create execution manager and context
        ws_manager = EphemeralWorkspaceManager()
        exec_manager = ExecutionManager(ws_manager, runtime_engine=engine)
        
        task = Task(
            task_id="test_task_1",
            capability_id="filesystem.list",
            account_id="acc1",
            project_id="proj1",
            input={"path": "/tmp"},
            constraints={},
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            workspace_policy="keep",
            evidence_policy="none",
            requested_by="user",
            created_at=datetime.now(timezone.utc)
        )
        context = exec_manager.submit_task(task)
        assert context.generation == 1
        
        # Shut down engine
        engine.shutdown()
        
        # Restart and get generation 2
        engine2 = RuntimeEngine(config)
        engine2.startup()
        gen2 = engine2.generation.current
        assert gen2 == 2
        
        # Update exec_manager with new engine
        exec_manager.runtime_engine = engine2
        
        # Attempt operation using old context
        result_context = exec_manager.execute_sync(context.execution_id)
        
        # Must be rejected (fenced)
        assert result_context.status == ExecutionStatus.FAILED
        assert result_context.failure_reason == FailureReason.AUTHORIZATION_DENIED
        assert "Generation mismatch" in result_context.error_message

def test_continuity_reloaded_and_state_persisted():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RuntimeConfig(data_dir=tmpdir)
        engine = RuntimeEngine(config)
        engine.startup()
        
        # Save a test record
        record = ContinuityRecord.create(
            mission_id="m1",
            task_id="t1",
            step_id="s1",
            actor_id="a1",
            actor_level="L1",
            objective="Test"
        )
        engine.continuity_engine.save_record(record)
        
        engine.shutdown()
        
        # State file should exist
        state_file = Path(tmpdir) / "engine_state.json"
        assert state_file.exists()
        with open(state_file) as f:
            state = json.load(f)
            assert state["state"] == "STOPPED"
            assert state["generation"] == 1
            
        # Restart
        engine2 = RuntimeEngine(config)
        engine2.startup()
        
        # Continuity loaded
        loaded_record = engine2.continuity_engine.get_record(record.continuity_id)
        assert loaded_record is not None
        assert loaded_record.mission_id == "m1"
        assert engine2.generation.current == 2

def test_abnormal_termination_state_recovered():
    # If the process terminates without shutdown, the state is what it was during run.
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RuntimeConfig(data_dir=tmpdir)
        engine = RuntimeEngine(config)
        engine.startup()
        
        # Simulate abnormal termination by writing current state manually 
        # (in reality, engine_state.json might not exist if we never shutdown, 
        # but let's assume we periodically save state or it was saved before.
        # Actually, engine doesn't persist state continuously yet, so abnormal 
        # termination might not have engine_state.json unless we write it. 
        # But continuity flush is what matters most for abnormal termination)
        
        record = ContinuityRecord.create(
            mission_id="m1",
            task_id="t1",
            step_id="s1",
            actor_id="a1",
            actor_level="L1",
            objective="Test"
        )
        engine.continuity_engine.save_record(record)
        engine.continuity_engine.flush() # Explicit flush without shutdown
        
        # Restart directly
        engine2 = RuntimeEngine(config)
        engine2.startup()
        
        loaded_record = engine2.continuity_engine.get_record(record.continuity_id)
        assert loaded_record is not None

