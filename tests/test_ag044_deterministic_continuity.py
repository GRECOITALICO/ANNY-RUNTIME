import os
import json
import shutil
import pytest
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

from runtime.continuity.models import ContinuityRecord, EventRecord, ContinuityStatus
from runtime.continuity.events import ContinuityEventType
from runtime.continuity.engine import ContinuityEngine, CorruptionSeverity
from runtime.core.generation import RuntimeGeneration, StaleGenerationError
from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus, FailureReason
from runtime.execution.manager import ExecutionManager
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


def make_test_task(task_id: str = "t-001", cap_id: str = "filesystem.inspect"):
    return Task(
        task_id=task_id,
        capability_id=cap_id,
        account_id="acc-1",
        project_id="proj-1",
        # A deterministic task must not use the process-level /tmp as an
        # implicit authority.  Relative paths resolve from its created,
        # authorized ephemeral workspace.
        input={"path": "."},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        workspace_policy="workspace_only",
        evidence_policy="required",
        requested_by="user-1",
        created_at=datetime.now(timezone.utc)
    )


# 1. persistence survives process recreation
def test_01_persistence_survives_process_recreation(temp_dir):
    engine1 = ContinuityEngine(data_dir=temp_dir)
    rec = ContinuityRecord.create(
        mission_id="m-1", task_id="t-1", step_id="s-1",
        actor_id="ANNY", actor_level="L0", objective="test"
    )
    engine1.save_record(rec)
    
    evt = EventRecord(
        event_id="e-1", sequence=1, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-1", task_id="t-1", step_id="s-1", parent_event_id=None,
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.TASK_CREATED, target="sys", intent="test",
        inputs={}, repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=[], observation="queued", result="OK", evidence_refs=["ref-1"],
        test_results=[], decision_ref=None, state_change="QUEUED",
        status="QUEUED", implementation_state="QUEUED", verification_state="PENDING",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
    )
    engine1.append_event(evt)
    
    # Process death simulation
    del engine1

    engine2 = ContinuityEngine(data_dir=temp_dir)
    loaded_rec = engine2.get_record(rec.continuity_id)
    assert loaded_rec is not None
    assert loaded_rec.objective == "test"
    
    events = engine2.get_events_by_mission("m-1")
    assert len(events) == 1
    assert events[0].event_id == "e-1"
    assert events[0].evidence_refs == ["ref-1"]


# 2. deterministic event sequence
def test_02_deterministic_event_sequence(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    for i in range(5):
        evt = EventRecord(
            event_id=f"evt-{i}", sequence=0, timestamp=datetime.now(timezone.utc).isoformat(),
            mission_id="m-seq", task_id="t-seq", step_id="s-seq", parent_event_id=None,
            actor_id="ANNY", actor_level="L0", parent_actor_id=None,
            event_type=ContinuityEventType.STEP_CREATED, target="sys", intent="seq",
            inputs={"idx": i}, repository=None, branch=None, commit_before=None, commit_after=None,
            files_changed=[], observation="step", result="OK", evidence_refs=[],
            test_results=[], decision_ref=None, state_change="RUNNING",
            status="RUNNING", implementation_state="RUNNING", verification_state="PENDING",
            certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
        )
        engine.append_event(evt)
    
    events = engine.get_events_by_mission("m-seq")
    sequences = [e.sequence for e in events]
    assert sequences == [1, 2, 3, 4, 5]


# 3. deterministic state reconstruction
def test_03_deterministic_state_reconstruction(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    evt1 = EventRecord(
        event_id="e-recon-1", sequence=1, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-recon", task_id="exec-123", step_id="cap-1", parent_event_id=None,
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.TASK_CREATED, target="cap-1", intent="dispatch",
        inputs={"execution_id": "exec-123", "routing_class": "DETERMINISTIC", "executor_id": "det-v1", "generation": 1},
        repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=[], observation="dispatch", result="QUEUED", evidence_refs=[],
        test_results=[], decision_ref=None, state_change="QUEUED",
        status="QUEUED", implementation_state="QUEUED", verification_state="PENDING",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
    )
    engine.append_event(evt1)

    evt2 = EventRecord(
        event_id="e-recon-2", sequence=2, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-recon", task_id="exec-123", step_id="cap-1", parent_event_id="e-recon-1",
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.ACTION_COMPLETED, target="cap-1", intent="complete",
        inputs={"execution_id": "exec-123", "routing_class": "DETERMINISTIC", "executor_id": "det-v1", "generation": 1},
        repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=["res.txt"], observation="complete", result="SUCCEEDED", evidence_refs=["ev-hash-99"],
        test_results=[], decision_ref=None, state_change="SUCCEEDED",
        status="SUCCEEDED", implementation_state="SUCCEEDED", verification_state="VERIFIED",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
    )
    engine.append_event(evt2)

    recon = engine.reconstruct_execution("exec-123")
    assert recon is not None
    assert recon["status"] == "SUCCEEDED"
    assert recon["events_count"] == 2
    assert recon["routing_class"] == "DETERMINISTIC"
    assert recon["evidence_refs"] == ["ev-hash-99"]


# 4. generation increment
def test_04_generation_increment(temp_dir):
    gen = RuntimeGeneration(data_dir=temp_dir)
    assert gen.current == 0
    g1 = gen.increment()
    assert g1 == 1
    assert gen.current == 1

    g2 = gen.increment()
    assert g2 == 2
    assert gen.current == 2

    # Reload from disk
    gen_reloaded = RuntimeGeneration(data_dir=temp_dir)
    assert gen_reloaded.current == 2


# 5. stale generation rejection
def test_05_stale_generation_rejection(temp_dir):
    gen = RuntimeGeneration(data_dir=temp_dir)
    gen.increment()  # generation = 1
    gen.increment()  # generation = 2

    assert gen.validate(2) is True
    assert gen.validate(1) is False

    with pytest.raises(StaleGenerationError) as exc_info:
        gen.fence(1)
    assert "Generation mismatch" in str(exc_info.value)


# 6. interrupted execution recovery
def test_06_interrupted_execution_recovery(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    evt = EventRecord(
        event_id="e-crash-1", sequence=1, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-crash", task_id="t-crash", step_id="s-crash", parent_event_id=None,
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.TASK_CREATED, target="s-crash", intent="start",
        inputs={"execution_id": "exec-crash-1", "generation": 1},
        repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=[], observation="QUEUED", result="QUEUED", evidence_refs=[],
        test_results=[], decision_ref=None, state_change="QUEUED",
        status="QUEUED", implementation_state="QUEUED", verification_state="PENDING",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action="EXECUTE"
    )
    engine.append_event(evt)

    # Process restarts
    restarted_engine = ContinuityEngine(data_dir=temp_dir)
    recon = restarted_engine.reconstruct_execution("exec-crash-1")
    assert recon is not None
    assert recon["status"] == "QUEUED"
    assert recon["latest_event_type"] == ContinuityEventType.TASK_CREATED


# 7. no duplicate completion
def test_07_no_duplicate_completion(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    evt = EventRecord(
        event_id="e-dup-1", sequence=1, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-dup", task_id="t-dup", step_id="s-dup", parent_event_id=None,
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.ACTION_COMPLETED, target="s-dup", intent="complete",
        inputs={"execution_id": "exec-dup-1"}, repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=[], observation="SUCCEEDED", result="SUCCEEDED", evidence_refs=["ref-dup"],
        test_results=[], decision_ref=None, state_change="SUCCEEDED",
        status="SUCCEEDED", implementation_state="SUCCEEDED", verification_state="VERIFIED",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
    )
    engine.append_event(evt)

    recon1 = engine.reconstruct_execution("exec-dup-1")
    recon2 = engine.reconstruct_execution("exec-dup-1")
    assert recon1 == recon2
    assert len(engine.get_events_by_mission("m-dup")) == 1


# 8. append-only event persistence
def test_08_append_only_event_persistence(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    evt1 = EventRecord(
        event_id="e-app-1", sequence=1, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-app", task_id="t-app", step_id="s-app", parent_event_id=None,
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.STEP_CREATED, target="s-app", intent="1",
        inputs={}, repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=[], observation="1", result="1", evidence_refs=[],
        test_results=[], decision_ref=None, state_change="1",
        status="RUNNING", implementation_state="RUNNING", verification_state="PENDING",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
    )
    engine.append_event(evt1)

    events_file = engine.events_path
    lines_after_1 = events_file.read_text().strip().splitlines()
    assert len(lines_after_1) == 1

    evt2 = EventRecord(
        event_id="e-app-2", sequence=2, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-app", task_id="t-app", step_id="s-app", parent_event_id="e-app-1",
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.ACTION_COMPLETED, target="s-app", intent="2",
        inputs={}, repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=[], observation="2", result="2", evidence_refs=[],
        test_results=[], decision_ref=None, state_change="2",
        status="SUCCEEDED", implementation_state="SUCCEEDED", verification_state="VERIFIED",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
    )
    engine.append_event(evt2)

    lines_after_2 = events_file.read_text().strip().splitlines()
    assert len(lines_after_2) == 2
    assert json.loads(lines_after_2[0])["event_id"] == "e-app-1"
    assert json.loads(lines_after_2[1])["event_id"] == "e-app-2"


# 9. flush durability
def test_09_flush_durability(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    rec = ContinuityRecord.create("m-f", "t-f", "s-f", "ANNY", "L0", "flush test")
    engine.save_record(rec)
    engine.flush()

    assert engine.records_path.exists()
    assert engine.records_path.stat().st_size > 0


# 10. malformed record handling
def test_10_malformed_record_handling(temp_dir):
    engine1 = ContinuityEngine(data_dir=temp_dir)
    rec = ContinuityRecord.create("m-bad", "t-bad", "s-bad", "ANNY", "L0", "good record")
    engine1.save_record(rec)

    # Inject malformed line
    with open(engine1.records_path, "a") as f:
        f.write("{ invalid json line ...\n")

    # Reload engine
    engine2 = ContinuityEngine(data_dir=temp_dir)
    assert engine2.corruption_status == CorruptionSeverity.QUARANTINED
    assert len(engine2.quarantined_records) >= 1
    assert engine2.get_record(rec.continuity_id) is not None


# 11. malformed event handling
def test_11_malformed_event_handling(temp_dir):
    engine1 = ContinuityEngine(data_dir=temp_dir)
    evt = EventRecord(
        event_id="e-good", sequence=1, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m-bad-evt", task_id="t-bad-evt", step_id="s-bad-evt", parent_event_id=None,
        actor_id="ANNY", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.STEP_CREATED, target="s", intent="good",
        inputs={}, repository=None, branch=None, commit_before=None, commit_after=None,
        files_changed=[], observation="good", result="good", evidence_refs=[],
        test_results=[], decision_ref=None, state_change="good",
        status="RUNNING", implementation_state="RUNNING", verification_state="PENDING",
        certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
    )
    engine1.append_event(evt)

    # Inject corrupt event line
    with open(engine1.events_path, "a") as f:
        f.write('{"event_id": "broken", "missing_required_fields": true}\n')

    engine2 = ContinuityEngine(data_dir=temp_dir)
    assert engine2.corruption_status == CorruptionSeverity.QUARANTINED
    assert len(engine2._events) == 1
    assert engine2._events[0].event_id == "e-good"


# 12. sequence inconsistency handling
def test_12_sequence_inconsistency_handling(temp_dir):
    engine1 = ContinuityEngine(data_dir=temp_dir)
    evt_data1 = {
        "event_id": "e-seq-1", "sequence": 5, "timestamp": datetime.now(timezone.utc).isoformat(),
        "mission_id": "m-seq-inc", "task_id": "t-1", "step_id": "s-1", "parent_event_id": None,
        "actor_id": "ANNY", "actor_level": "L0", "parent_actor_id": None,
        "event_type": "STEP_CREATED", "target": "s", "intent": "i", "inputs": {},
        "repository": None, "branch": None, "commit_before": None, "commit_after": None,
        "files_changed": [], "observation": "o", "result": "r", "evidence_refs": [],
        "test_results": [], "decision_ref": None, "state_change": "s",
        "status": "RUNNING", "implementation_state": "RUNNING", "verification_state": "PENDING",
        "certification_state": "NOT_CERTIFIED", "blocker_refs": [], "next_action": None
    }
    evt_data2 = dict(evt_data1, event_id="e-seq-2", sequence=2)

    with open(engine1.events_path, "a") as f:
        f.write(json.dumps(evt_data1) + "\n")
        f.write(json.dumps(evt_data2) + "\n")

    engine2 = ContinuityEngine(data_dir=temp_dir)
    assert engine2.corruption_status == CorruptionSeverity.RECOVERED
    assert len(engine2._events) == 2
    assert engine2._events[1].sequence > engine2._events[0].sequence


# 13. partial write handling
def test_13_partial_write_handling(temp_dir):
    engine1 = ContinuityEngine(data_dir=temp_dir)
    rec = ContinuityRecord.create("m-part", "t-part", "s-part", "ANNY", "L0", "partial test")
    engine1.save_record(rec)

    with open(engine1.records_path, "a") as f:
        f.write('{"continuity_id": "partial-123", "mission_id": "m-part", "task_id": "t-part"')

    engine2 = ContinuityEngine(data_dir=temp_dir)
    assert engine2.corruption_status == CorruptionSeverity.QUARANTINED
    assert engine2.get_record(rec.continuity_id) is not None


# 14. execution to continuity linkage
def test_14_execution_to_continuity_linkage(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    ws_mgr = EphemeralWorkspaceManager(base_dir=os.path.join(temp_dir, "workspaces"))
    exec_mgr = ExecutionManager(workspace_manager=ws_mgr, continuity_engine=engine)

    task = make_test_task("t-link-001")
    context = exec_mgr.submit_task(task)

    events = engine.get_events_by_task("t-link-001")
    assert len(events) == 1
    assert events[0].event_type == ContinuityEventType.TASK_CREATED
    assert events[0].inputs["execution_id"] == context.execution_id


# 15. plan to recovery linkage
def test_15_plan_to_recovery_linkage(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    ws_mgr = EphemeralWorkspaceManager(base_dir=os.path.join(temp_dir, "workspaces"))
    exec_mgr = ExecutionManager(workspace_manager=ws_mgr, continuity_engine=engine)

    task = make_test_task("t-plan-001", cap_id="filesystem.inspect")
    context = exec_mgr.submit_task(task)

    recon = engine.reconstruct_execution(context.execution_id)
    assert recon is not None
    assert recon["routing_class"] == "DETERMINISTIC"
    assert recon["executor_id"] == "deterministic-v1"


# 16. evidence reference preservation
def test_16_evidence_reference_preservation(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    ws_mgr = EphemeralWorkspaceManager(base_dir=os.path.join(temp_dir, "workspaces"))
    exec_mgr = ExecutionManager(workspace_manager=ws_mgr, continuity_engine=engine)

    task = make_test_task("t-ev-001", cap_id="filesystem.inspect")
    context = exec_mgr.submit_task(task)
    exec_mgr.execute_sync(context.execution_id)

    recon = engine.reconstruct_execution(context.execution_id)
    assert recon is not None
    assert recon["status"] == "SUCCEEDED"
    assert len(recon["evidence_refs"]) > 0


# 17. idempotent reconstruction
def test_17_idempotent_reconstruction(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    ws_mgr = EphemeralWorkspaceManager(base_dir=os.path.join(temp_dir, "workspaces"))
    exec_mgr = ExecutionManager(workspace_manager=ws_mgr, continuity_engine=engine)

    task = make_test_task("t-idem-001", cap_id="filesystem.inspect")
    context = exec_mgr.submit_task(task)
    exec_mgr.execute_sync(context.execution_id)

    r1 = engine.reconstruct_execution(context.execution_id)
    r2 = engine.reconstruct_execution(context.execution_id)
    r3 = engine.reconstruct_execution(context.execution_id)

    assert r1 == r2 == r3


# 18. recovery after process death
def test_18_recovery_after_process_death(temp_dir):
    engine1 = ContinuityEngine(data_dir=temp_dir)
    ws_mgr1 = EphemeralWorkspaceManager(base_dir=os.path.join(temp_dir, "workspaces"))
    exec_mgr1 = ExecutionManager(workspace_manager=ws_mgr1, continuity_engine=engine1)

    task = make_test_task("t-death-001", cap_id="filesystem.inspect")
    context1 = exec_mgr1.submit_task(task)
    exec_mgr1.execute_sync(context1.execution_id)

    del exec_mgr1, ws_mgr1, engine1

    engine2 = ContinuityEngine(data_dir=temp_dir)
    recon = engine2.reconstruct_execution(context1.execution_id)
    assert recon is not None
    assert recon["status"] == "SUCCEEDED"


# 19. recovery after generation change
def test_19_recovery_after_generation_change(temp_dir):
    gen = RuntimeGeneration(data_dir=temp_dir)
    gen.increment()  # generation = 1

    engine = ContinuityEngine(data_dir=temp_dir)
    ws_mgr = EphemeralWorkspaceManager(base_dir=os.path.join(temp_dir, "workspaces"))
    
    class DummyEngine:
        def __init__(self, generation):
            self.generation = generation
    
    runtime_eng = DummyEngine(gen)
    exec_mgr = ExecutionManager(workspace_manager=ws_mgr, runtime_engine=runtime_eng, continuity_engine=engine)

    task = make_test_task("t-gen-001", cap_id="filesystem.inspect")
    context = exec_mgr.submit_task(task)
    assert context.generation == 1

    # Advance generation
    gen.increment()  # generation = 2

    # Execute task with stale generation
    res_context = exec_mgr.execute_sync(context.execution_id)
    assert res_context.status == ExecutionStatus.FAILED
    assert res_context.failure_reason == FailureReason.AUTHORIZATION_DENIED

    recon = engine.reconstruct_execution(context.execution_id)
    assert recon["status"] == "FAILED"


# 20. concurrent continuity access behavior
def test_20_concurrent_continuity_access_behavior(temp_dir):
    engine = ContinuityEngine(data_dir=temp_dir)
    errors = []

    def worker_thread(thread_idx):
        try:
            for i in range(10):
                rec = ContinuityRecord.create(
                    mission_id=f"m-conc-{thread_idx}",
                    task_id=f"t-conc-{thread_idx}-{i}",
                    step_id="step-conc",
                    actor_id="ANNY", actor_level="L0", objective="conc"
                )
                engine.save_record(rec)

                evt = EventRecord(
                    event_id=f"evt-conc-{thread_idx}-{i}", sequence=0, timestamp=datetime.now(timezone.utc).isoformat(),
                    mission_id=f"m-conc-{thread_idx}", task_id=f"t-conc-{thread_idx}-{i}", step_id="step-conc",
                    parent_event_id=None, actor_id="ANNY", actor_level="L0", parent_actor_id=None,
                    event_type=ContinuityEventType.STEP_CREATED, target="conc", intent="conc",
                    inputs={}, repository=None, branch=None, commit_before=None, commit_after=None,
                    files_changed=[], observation="conc", result="OK", evidence_refs=[],
                    test_results=[], decision_ref=None, state_change="RUNNING",
                    status="RUNNING", implementation_state="RUNNING", verification_state="PENDING",
                    certification_state="NOT_CERTIFIED", blocker_refs=[], next_action=None
                )
                engine.append_event(evt)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker_thread, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(engine._records) == 50
    assert len(engine._events) == 50
    
    sequences = [e.sequence for e in engine._events]
    assert sequences == list(range(1, 51))
