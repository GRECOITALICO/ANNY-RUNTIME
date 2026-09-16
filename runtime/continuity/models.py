from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid

from runtime.continuity.events import ContinuityEventType

class ContinuityStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    NOT_CERTIFIED = "NOT_CERTIFIED"
    CERTIFIED = "CERTIFIED"
    BLOCKED = "BLOCKED"

class BootstrapStatus(str, Enum):
    COHERENT = "COHERENT"
    DEGRADED = "DEGRADED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    UNVERIFIED = "UNVERIFIED"

@dataclass
class ContinuityRecord:
    continuity_id: str
    mission_id: str
    task_id: str
    parent_task_id: Optional[str]
    step_id: str
    parent_step_id: Optional[str]

    created_at: str
    started_at: Optional[str]
    updated_at: str
    completed_at: Optional[str]
    certified_at: Optional[str]

    actor_id: str
    actor_level: str
    parent_actor_id: Optional[str]

    status: str
    implementation_state: str
    verification_state: str
    certification_state: str

    objective: str
    reason: str

    repository: Optional[str]
    branch: Optional[str]

    commit_before: Optional[str]
    commit_after: Optional[str]

    files_changed: List[str]
    change_summary: Optional[str]

    actions: List[str]
    tools: List[str]

    tests: List[str]
    test_results: List[Dict[str, Any]]

    evidence_refs: List[str]
    artifact_refs: List[str]
    decision_refs: List[str]
    blocker_refs: List[str]

    # Three-Plane fields — Repository Fabric binding
    fabric_node: Optional[str]      # e.g. "NODE-001"
    fabric_tenant: Optional[str]
    fabric_project: Optional[str]
    resource_ids: List[str]
    state_before: Optional[str]     # JSON-serialized state snapshot
    state_after: Optional[str]      # JSON-serialized state snapshot

    current_step: Optional[str]
    last_completed_step: Optional[str]
    next_action: Optional[str]

    handoff_target: Optional[str]
    handoff_status: Optional[str]

    @classmethod
    def create(cls, mission_id: str, task_id: str, step_id: str, actor_id: str, actor_level: str, objective: str) -> "ContinuityRecord":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            continuity_id=uuid.uuid4().hex,
            mission_id=mission_id,
            task_id=task_id,
            parent_task_id=None,
            step_id=step_id,
            parent_step_id=None,
            created_at=now,
            started_at=None,
            updated_at=now,
            completed_at=None,
            certified_at=None,
            actor_id=actor_id,
            actor_level=actor_level,
            parent_actor_id=None,
            status=ContinuityStatus.PENDING.value,
            implementation_state=ContinuityStatus.PENDING.value,
            verification_state=ContinuityStatus.PENDING.value,
            certification_state=ContinuityStatus.NOT_CERTIFIED.value,
            objective=objective,
            reason="",
            repository=None,
            branch=None,
            commit_before=None,
            commit_after=None,
            files_changed=[],
            change_summary=None,
            actions=[],
            tools=[],
            tests=[],
            test_results=[],
            evidence_refs=[],
            artifact_refs=[],
            decision_refs=[],
            blocker_refs=[],
            fabric_node=None,
            fabric_tenant=None,
            fabric_project=None,
            resource_ids=[],
            state_before=None,
            state_after=None,
            current_step=step_id,
            last_completed_step=None,
            next_action=None,
            handoff_target=None,
            handoff_status=None
        )

@dataclass
class EventRecord:
    event_id: str
    sequence: int
    timestamp: str

    mission_id: str
    task_id: str
    step_id: str
    parent_event_id: Optional[str]

    actor_id: str
    actor_level: str
    parent_actor_id: Optional[str]

    event_type: ContinuityEventType
    target: str
    intent: str
    inputs: Dict[str, Any]

    repository: Optional[str]
    branch: Optional[str]
    commit_before: Optional[str]
    commit_after: Optional[str]

    files_changed: List[str]

    observation: str
    result: str

    evidence_refs: List[str]
    test_results: List[Dict[str, Any]]

    decision_ref: Optional[str]
    state_change: Optional[str]

    status: str
    implementation_state: str
    verification_state: str
    certification_state: str

    blocker_refs: List[str]
    next_action: Optional[str]

    # Three-Plane fields — Repository Fabric binding
    fabric_node: Optional[str] = None
    fabric_tenant: Optional[str] = None
    fabric_project: Optional[str] = None
    resource_ids: List[str] = None
    state_before: Optional[str] = None
    state_after: Optional[str] = None
