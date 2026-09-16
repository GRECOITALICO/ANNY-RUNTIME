import os
import shutil
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from runtime.continuity.models import ContinuityRecord, EventRecord, ContinuityStatus, BootstrapStatus
from runtime.continuity.events import ContinuityEventType
from runtime.continuity.engine import ContinuityEngine
from runtime.continuity.mutation import RepositoryMutationContract
from runtime.continuity.reconciler import Reconciler

@pytest.fixture
def temp_data_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_continuity_engine_step_sequence(temp_data_dir):
    """
    Test the strict A-B-B.1-B.2-C-C.1-C.2 sequence, 
    process death simulation, and state separation.
    """
    engine = ContinuityEngine(data_dir=temp_data_dir)
    mutation_contract = RepositoryMutationContract(engine)
    
    # 1. STEP C.2 Creation
    record_c2 = ContinuityRecord.create(
        mission_id="TEST-MISSION-1",
        task_id="TASK-C",
        step_id="STEP-C.2",
        actor_id="ANNY",
        actor_level="L0",
        objective="Run C.2 test"
    )
    # Simulate we completed C.1 before this
    record_c2.last_completed_step = "STEP-C.1"
    engine.save_record(record_c2)

    # 2. Modifying repository and creating commit
    event = mutation_contract.record_mutation(
        mission_id="TEST-MISSION-1",
        task_id="TASK-C",
        step_id="STEP-C.2",
        actor_id="ANNY",
        actor_level="L0",
        repository="ANNY-OPERATIONAL",
        branch="main",
        commit_before="abc1234",
        commit_after="def5678",
        files_changed=["README.md"],
        reason="Updated documentation",
        action="commit",
        tests=["test_doc.py"],
        evidence_refs=["evidence-doc-001"],
        next_action="RUN_TESTS"
    )

    # 3. NO certification!
    assert event.implementation_state == ContinuityStatus.COMPLETE.value
    assert event.verification_state == ContinuityStatus.PENDING.value
    assert event.certification_state == ContinuityStatus.NOT_CERTIFIED.value

    # Simulate process death (memory wiped)
    del mutation_contract
    del engine

    # 4. Bootstrap Recovery (Restart)
    restarted_engine = ContinuityEngine(data_dir=temp_data_dir)
    reconciler = Reconciler(restarted_engine)
    status = reconciler.reconcile()

    # EXPECTED:
    # current_step = C.2
    # last_completed_step = C.1
    # implementation state = COMPLETE
    # verification state = PENDING
    # certification state = NOT_CERTIFIED
    recovered_c2 = restarted_engine.get_record(record_c2.continuity_id)
    
    assert recovered_c2 is not None
    assert recovered_c2.current_step == "STEP-C.2"
    assert recovered_c2.last_completed_step == "STEP-C.1"
    assert recovered_c2.implementation_state == ContinuityStatus.COMPLETE.value
    assert recovered_c2.verification_state == ContinuityStatus.PENDING.value
    assert recovered_c2.certification_state == ContinuityStatus.NOT_CERTIFIED.value
    
    # Recover attributes
    assert recovered_c2.commit_after == "def5678"
    assert "README.md" in recovered_c2.files_changed
    assert "test_doc.py" in recovered_c2.tests
    assert "evidence-doc-001" in recovered_c2.evidence_refs
    assert recovered_c2.next_action == "RUN_TESTS"
    
    assert status == BootstrapStatus.COHERENT

def test_discrepancy_detection(temp_data_dir):
    engine = ContinuityEngine(data_dir=temp_data_dir)
    
    # Simulate a step marked as complete with repository assigned, 
    # but no mutation event generated (Contract bypass)
    record = ContinuityRecord.create(
        mission_id="TEST-MISSION-2",
        task_id="TASK-X",
        step_id="STEP-X",
        actor_id="ANNY",
        actor_level="L0",
        objective="Break things"
    )
    record.status = ContinuityStatus.COMPLETE.value
    record.repository = "ANNY-RUNTIME"
    engine.save_record(record)
    
    reconciler = Reconciler(engine)
    status = reconciler.reconcile()
    
    assert status == BootstrapStatus.RECONCILIATION_REQUIRED
    
    # A gap event should have been created
    events = engine.get_events_by_mission("TEST-MISSION-2")
    gap_events = [e for e in events if e.observation.startswith("CONTINUITY_GAP")]
    
    assert len(gap_events) == 1
    assert gap_events[0].state_change == ContinuityStatus.BLOCKED.value
