from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone
import logging
import subprocess

from runtime.continuity.models import ContinuityRecord, EventRecord, BootstrapStatus, ContinuityStatus
from runtime.continuity.events import ContinuityEventType
from runtime.continuity.engine import ContinuityEngine

logger = logging.getLogger(__name__)

class Reconciler:
    """Reconciles Runtime Activity, Operational State, and Git History."""
    def __init__(self, engine: ContinuityEngine):
        self.engine = engine

    def reconcile(self) -> BootstrapStatus:
        """
        Detects if the runtime advanced but operational state didn't,
        or if the repository changed but the mission journal missed the mutation,
        or if the mission journal indicates a step but the commit/evidence doesn't exist.
        """
        status = BootstrapStatus.COHERENT
        
        records = list(self.engine._records.values())
        events = self.engine._events
        
        for record in records:
            # Check for orphaned PREPARE mutations
            if record.implementation_state == ContinuityStatus.ACTIVE.value and record.repository:
                prepared_events = [
                    e for e in events 
                    if e.step_id == record.step_id and e.event_type == ContinuityEventType.MUTATION_PREPARED
                ]
                finalized_events = [
                    e for e in events 
                    if e.step_id == record.step_id and e.event_type == ContinuityEventType.MUTATION_FINALIZED
                ]
                
                if prepared_events and not finalized_events:
                    prep = prepared_events[-1]
                    # We have a PREPARED mutation that was never finalized.
                    # Compare with git history.
                    try:
                        # Fallback for dummy tests
                        res = subprocess.run(
                            "git rev-parse HEAD || echo ''", 
                            shell=True, capture_output=True, text=True, cwd=prep.repository
                        )
                        current_head = res.stdout.strip()
                    except Exception:
                        current_head = ""

                    if current_head and prep.commit_before and current_head != prep.commit_before:
                        # The commit happened, but continuity didn't finalize.
                        # Preserve commit, block mission, require reconciliation.
                        record.status = "COMMITTED_UNFINALIZED"
                        self.engine.save_record(record)
                        
                        self._create_gap_event(
                            mission_id=record.mission_id,
                            task_id=record.task_id,
                            step_id=record.step_id,
                            reason=f"COMMITTED_UNFINALIZED: Found unfinalized commit {current_head} for prepared mutation from {prep.commit_before}"
                        )
                        status = BootstrapStatus.RECONCILIATION_REQUIRED
                    else:
                        # No commit happened
                        record.status = "PREPARED_NO_COMMIT"
                        self.engine.save_record(record)
                        self._create_gap_event(
                            mission_id=record.mission_id,
                            task_id=record.task_id,
                            step_id=record.step_id,
                            reason="PREPARED_NO_COMMIT: Process died before git commit was executed."
                        )
                        status = BootstrapStatus.RECONCILIATION_REQUIRED

            # Retro-compatibility / logical check for fully COMPLETE records
            if record.status == ContinuityStatus.COMPLETE.value and record.repository:
                mutation_events = [
                    e for e in events 
                    if e.step_id == record.step_id and e.event_type in (ContinuityEventType.REPOSITORY_MUTATED, ContinuityEventType.MUTATION_FINALIZED)
                ]
                
                if not mutation_events:
                    self._create_gap_event(
                        mission_id=record.mission_id,
                        task_id=record.task_id,
                        step_id=record.step_id,
                        reason="Step marked COMPLETE with repository, but no MUTATION_FINALIZED or REPOSITORY_MUTATED event found."
                    )
                    status = BootstrapStatus.RECONCILIATION_REQUIRED
                    
            if record.mission_id == "MISSION-002-R2-PHYSICAL":
                self.reconcile_mission_002(record)

        return status

    def _create_gap_event(self, mission_id: str, task_id: str, step_id: str, reason: str) -> None:
        gap_event = EventRecord(
            event_id=uuid.uuid4().hex,
            sequence=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            mission_id=mission_id,
            task_id=task_id,
            step_id=step_id,
            parent_event_id=None,
            actor_id="SYSTEM",
            actor_level="L0",
            parent_actor_id=None,
            event_type=ContinuityEventType.BLOCKER_CREATED,
            target="CONTINUITY",
            intent="RECONCILIATION",
            inputs={"reason": reason},
            repository=None,
            branch=None,
            commit_before=None,
            commit_after=None,
            files_changed=[],
            observation=f"CONTINUITY_GAP: {reason}",
            result="FAILED",
            evidence_refs=[],
            test_results=[],
            decision_ref=None,
            state_change=ContinuityStatus.BLOCKED.value,
            status=ContinuityStatus.BLOCKED.value,
            implementation_state=ContinuityStatus.PENDING.value,
            verification_state=ContinuityStatus.PENDING.value,
            certification_state=ContinuityStatus.NOT_CERTIFIED.value,
            blocker_refs=[],
            next_action="RECONCILE_STATE"
        )
        self.engine.append_event(gap_event)
        self.engine.flush()

    def reconcile_mission_002(self, record: ContinuityRecord) -> None:
        """
        Specific instructions for MISSION-002-R2-PHYSICAL
        """
        if not record.evidence_refs and record.status == ContinuityStatus.COMPLETE.value:
            record.status = "ORPHANED_REQUIRES_RECONCILIATION"
            record.reason = "Mission 002-R2-PHYSICAL marked as COMPLETE but missing physical evidence refs."
            self.engine.save_record(record)
            
            self._create_gap_event(
                mission_id=record.mission_id,
                task_id=record.task_id,
                step_id=record.step_id,
                reason="MISSION-002-R2-PHYSICAL is missing required evidence."
            )
