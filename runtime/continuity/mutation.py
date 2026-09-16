from typing import List, Optional
from datetime import datetime, timezone
import uuid

from runtime.continuity.models import ContinuityRecord, EventRecord, ContinuityStatus
from runtime.continuity.events import ContinuityEventType
from runtime.continuity.engine import ContinuityEngine

class RepositoryMutationContract:
    """Enforces that all repository mutations are continuity-critical and properly recorded in two phases."""
    def __init__(self, engine: ContinuityEngine):
        self.engine = engine

    def prepare_mutation(
        self,
        mission_id: str,
        task_id: str,
        step_id: str,
        actor_id: str,
        actor_level: str,
        repository: str,
        branch: str,
        commit_before: str,
        reason: str,
        action: str,
        next_action: str
    ) -> EventRecord:
        # Find active record for this step
        records = [r for r in self.engine.get_records_by_mission(mission_id) if r.step_id == step_id]
        if not records:
            raise ValueError(f"Cannot mutate repository: No active continuity record for step {step_id}")
        
        record = records[-1] # Get latest

        # Update ContinuityRecord for PREPARE phase
        record.repository = repository
        record.branch = branch
        record.commit_before = commit_before
        record.reason = reason
        record.next_action = next_action
        
        # Implementation state transitions to ACTIVE (prepared, but not final)
        record.implementation_state = ContinuityStatus.ACTIVE.value
        record.updated_at = datetime.now(timezone.utc).isoformat()
        
        self.engine.save_record(record)

        # Create EventRecord
        event = EventRecord(
            event_id=uuid.uuid4().hex,
            sequence=0, # Engine sets this
            timestamp=datetime.now(timezone.utc).isoformat(),
            mission_id=mission_id,
            task_id=task_id,
            step_id=step_id,
            parent_event_id=None,
            actor_id=actor_id,
            actor_level=actor_level,
            parent_actor_id=None,
            event_type=ContinuityEventType.MUTATION_PREPARED,
            target=repository,
            intent=action,
            inputs={"branch": branch},
            repository=repository,
            branch=branch,
            commit_before=commit_before,
            commit_after=None,
            files_changed=[],
            observation=f"Prepared mutation for repository {repository}",
            result="PREPARED",
            evidence_refs=[],
            test_results=[],
            decision_ref=None,
            state_change=ContinuityStatus.ACTIVE.value,
            status=ContinuityStatus.ACTIVE.value,
            implementation_state=ContinuityStatus.ACTIVE.value,
            verification_state=record.verification_state,
            certification_state=record.certification_state,
            blocker_refs=[],
            next_action=next_action
        )
        self.engine.append_event(event)
        self.engine.flush()
        
        return event

    def finalize_mutation(
        self,
        prepare_event: EventRecord,
        commit_after: str,
        files_changed: List[str],
        tests: List[str],
        evidence_refs: List[str]
    ) -> EventRecord:
        
        records = [r for r in self.engine.get_records_by_mission(prepare_event.mission_id) if r.step_id == prepare_event.step_id]
        if not records:
            raise ValueError(f"Cannot finalize: No active continuity record for step {prepare_event.step_id}")
        
        record = records[-1]

        # Update ContinuityRecord for FINALIZE phase
        record.commit_after = commit_after
        record.files_changed.extend(files_changed)
        record.tests.extend(tests)
        record.evidence_refs.extend(evidence_refs)
        
        record.implementation_state = ContinuityStatus.COMPLETE.value
        record.updated_at = datetime.now(timezone.utc).isoformat()
        
        self.engine.save_record(record)

        # Create EventRecord
        event = EventRecord(
            event_id=uuid.uuid4().hex,
            sequence=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            mission_id=prepare_event.mission_id,
            task_id=prepare_event.task_id,
            step_id=prepare_event.step_id,
            parent_event_id=prepare_event.event_id,
            actor_id=prepare_event.actor_id,
            actor_level=prepare_event.actor_level,
            parent_actor_id=None,
            event_type=ContinuityEventType.MUTATION_FINALIZED,
            target=prepare_event.target,
            intent=prepare_event.intent,
            inputs=prepare_event.inputs,
            repository=prepare_event.repository,
            branch=prepare_event.branch,
            commit_before=prepare_event.commit_before,
            commit_after=commit_after,
            files_changed=files_changed,
            observation=f"Finalized mutation for repository {prepare_event.repository}",
            result="SUCCESS",
            evidence_refs=evidence_refs,
            test_results=[],
            decision_ref=None,
            state_change=ContinuityStatus.COMPLETE.value,
            status=ContinuityStatus.COMPLETE.value,
            implementation_state=ContinuityStatus.COMPLETE.value,
            verification_state=record.verification_state,
            certification_state=record.certification_state,
            blocker_refs=[],
            next_action=prepare_event.next_action
        )
        self.engine.append_event(event)
        
        # Backwards compatibility event
        event_compat = EventRecord(
            event_id=uuid.uuid4().hex,
            sequence=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            mission_id=prepare_event.mission_id,
            task_id=prepare_event.task_id,
            step_id=prepare_event.step_id,
            parent_event_id=event.event_id,
            actor_id=prepare_event.actor_id,
            actor_level=prepare_event.actor_level,
            parent_actor_id=None,
            event_type=ContinuityEventType.REPOSITORY_MUTATED,
            target=prepare_event.target,
            intent=prepare_event.intent,
            inputs=prepare_event.inputs,
            repository=prepare_event.repository,
            branch=prepare_event.branch,
            commit_before=prepare_event.commit_before,
            commit_after=commit_after,
            files_changed=files_changed,
            observation=f"Mutated repository {prepare_event.repository}",
            result="SUCCESS",
            evidence_refs=evidence_refs,
            test_results=[],
            decision_ref=None,
            state_change=ContinuityStatus.COMPLETE.value,
            status=ContinuityStatus.COMPLETE.value,
            implementation_state=ContinuityStatus.COMPLETE.value,
            verification_state=record.verification_state,
            certification_state=record.certification_state,
            blocker_refs=[],
            next_action=prepare_event.next_action
        )
        self.engine.append_event(event_compat)
        
        self.engine.flush()
        
        return event
