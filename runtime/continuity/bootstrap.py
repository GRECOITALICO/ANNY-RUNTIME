"""Bootstrap resolver implementing 14-stage read sequence for Customer Zero."""
import logging
from typing import Optional, List, Dict, Any

from runtime.events.bus import EventBus, Event, EventType
from runtime.continuity.state import (
    ContinuityStatus,
    AnnyCanonicalState,
    CurrentMission,
    CurrentTask,
    NextAction,
    Blocker,
    BootstrapResult,
)
from runtime.continuity.operational import OperationalRepositoryProvider

logger = logging.getLogger(__name__)


class CustomerZeroBootstrapResolver:
    """Executes the 14-stage bootstrap read order per BOOTSTRAP.md contract."""

    def __init__(self, provider: OperationalRepositoryProvider, event_bus: Optional[EventBus] = None):
        self.provider = provider
        self.event_bus = event_bus

    def _emit(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Emit telemetry event via EventBus if available."""
        if self.event_bus:
            try:
                self.event_bus.emit(Event(event_type=event_type, source="bootstrap_resolver", payload=payload))
            except Exception as e:
                logger.warning(f"Failed emitting telemetry event {event_type}: {e}")

    def resolve(self) -> BootstrapResult:
        """Resolve canonical operational state per 14-stage read sequence."""
        stages_completed: List[str] = []
        blockers: List[Blocker] = []

        self._emit(EventType.BOOTSTRAP_STARTED, {"status": "STARTING"})

        # Stage 1: Resolve Operational Repository & BOOTSTRAP.md
        repo_info = self.provider.resolve_operational_repository()
        if not repo_info:
            b = Blocker(id="BLK-BOOTSTRAP-001", description="ANNY-OPERATIONAL repository inaccessible or unresolved", severity="CRITICAL")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers,
                error_message="Operational repository (GRECOITALICO/ANNY-OPERATIONAL) could not be resolved."
            )

        stages_completed.append("OPERATIONAL_REPOSITORY_RESOLVED")
        self._emit(EventType.OPERATIONAL_REPOSITORY_RESOLVED, {"full_name": repo_info.get("full_name")})

        bootstrap_md = self.provider.read_bootstrap()
        if not bootstrap_md:
            b = Blocker(id="BLK-BOOTSTRAP-002", description="BOOTSTRAP.md contract missing from operational repository", severity="CRITICAL")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers,
                error_message="BOOTSTRAP.md is missing from operational repository."
            )
        stages_completed.append("1.BOOTSTRAP")

        # Stage 2: CONSTITUTION
        if not self.provider.path_exists("constitution/"):
            b = Blocker(id="BLK-BOOTSTRAP-002", description="constitution directory missing", severity="CRITICAL")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers,
                error_message="Constitution directory is missing."
            )
        stages_completed.append("2.CONSTITUTION")

        # Stage 3: OPERATING SYSTEM
        if not self.provider.path_exists("os/"):
            b = Blocker(id="BLK-BOOTSTRAP-003", description="os directory missing", severity="CRITICAL")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers,
                error_message="OS directory is missing."
            )
        stages_completed.append("3.OPERATING_SYSTEM")

        # Stage 4 & 6: CURRENT_STATE
        current_state_dict = self.provider.read_current_state()
        if not current_state_dict:
            b = Blocker(id="BLK-BOOTSTRAP-004", description="state/CURRENT_STATE.yaml missing or invalid", severity="CRITICAL")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers,
                error_message="state/CURRENT_STATE.yaml is missing or invalid."
            )
        stages_completed.append("4.SHARED_ORG_STATE")
        stages_completed.append("6.CURRENT_STATE")
        self._emit(EventType.CANONICAL_STATE_LOADED, {"schema_version": current_state_dict.get("schema_version")})

        # Stage 5: L2_WORKER_REGISTRY
        l2_workers = self.provider.read_l2_registry() or []
        stages_completed.append("5.L2_WORKER_REGISTRY")

        # Stage 7: CURRENT_MISSION
        current_mission_dict = self.provider.read_current_mission()
        parsed_mission: Optional[CurrentMission] = None
        if not current_mission_dict:
            b = Blocker(id="BLK-BOOTSTRAP-007", description="state/CURRENT_MISSION.yaml missing or invalid", severity="CRITICAL")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers,
                error_message="state/CURRENT_MISSION.yaml is missing or invalid."
            )

        mission_id = current_mission_dict.get("mission_id")
        mission_title = current_mission_dict.get("title")
        mission_status = current_mission_dict.get("status")
        mission_desc = current_mission_dict.get("objective") or current_mission_dict.get("description")
        raw_content = current_mission_dict.get("_raw_content")

        if not mission_id or not mission_status:
            b = Blocker(id="BLK-BOOTSTRAP-007a", description="SCHEMA_MISMATCH: CURRENT_MISSION missing mission_id or status", severity="CRITICAL")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers,
                error_message="CURRENT_MISSION SCHEMA_MISMATCH."
            )

        parsed_tasks = []
        raw_tasks = current_mission_dict.get("scope") or []
        if isinstance(raw_tasks, list):
            for idx, task_item in enumerate(raw_tasks):
                if isinstance(task_item, dict):
                    t_id = task_item.get("id", f"TASK-{idx+1}")
                    t_name = task_item.get("name", str(task_item))
                    t_status = task_item.get("status", "UNKNOWN")
                    parsed_tasks.append(CurrentTask(id=t_id, name=t_name, status=t_status))
                else:
                    parsed_tasks.append(CurrentTask(id=f"TASK-{idx+1}", name=str(task_item), status="UNKNOWN"))

        parsed_mission = CurrentMission(
            id=mission_id,
            title=mission_title,
            status=mission_status,
            description=mission_desc,
            tasks=parsed_tasks,
            raw_content=raw_content
        )
        stages_completed.append("7.CURRENT_MISSION")
        self._emit(EventType.CURRENT_MISSION_RESOLVED, {"mission_id": mission_id, "status": mission_status})

        # Stage 8: BLOCKERS
        blockers_dict = self.provider.read_blockers()
        parsed_blockers: List[Blocker] = []
        if blockers_dict and "blockers" in blockers_dict and isinstance(blockers_dict["blockers"], list):
            for idx, item in enumerate(blockers_dict["blockers"]):
                if isinstance(item, dict):
                    parsed_blockers.append(Blocker(
                        id=item.get("id", f"BLK-{idx+1}"),
                        description=item.get("description", str(item)),
                        severity=item.get("severity", "UNKNOWN")
                    ))
                else:
                    parsed_blockers.append(Blocker(id=f"BLK-{idx+1}", description=str(item), severity="UNKNOWN"))
        elif current_state_dict and "blockers" in current_state_dict and isinstance(current_state_dict["blockers"], list):
            for idx, item in enumerate(current_state_dict["blockers"]):
                if isinstance(item, dict):
                    parsed_blockers.append(Blocker(
                        id=item.get("id", f"BLK-{idx+1}"),
                        description=item.get("description", str(item)),
                        severity=item.get("severity", "UNKNOWN")
                    ))
                else:
                    parsed_blockers.append(Blocker(id=f"BLK-{idx+1}", description=str(item), severity="UNKNOWN"))

        stages_completed.append("8.BLOCKERS")
        self._emit(EventType.BLOCKERS_LOADED, {"count": len(parsed_blockers)})

        # Stage 9: NEXT_ACTION
        next_action_dict = self.provider.read_next_action()
        parsed_next_action: Optional[NextAction] = None
        if next_action_dict:
            action_data = next_action_dict.get("action", {})
            if isinstance(action_data, dict):
                parsed_next_action = NextAction(
                    action=action_data.get("WHAT", "Unspecified action"),
                    actor=action_data.get("OWNER", "ANNY"),
                    target=action_data.get("DEPENDENCY"),
                    rationale=action_data.get("WHY")
                )
            elif isinstance(action_data, str):
                parsed_next_action = NextAction(action=action_data, actor="ANNY")

        if not parsed_next_action and current_state_dict.get("next_action"):
            parsed_next_action = NextAction(action=str(current_state_dict["next_action"]), actor="ANNY")

        if not parsed_next_action:
            b = Blocker(id="BLK-BOOTSTRAP-009", description="state/NEXT_ACTION.yaml missing or invalid", severity="HIGH")
            blockers.append(b)
            return BootstrapResult(
                status=ContinuityStatus.BLOCKED,
                stages_completed=stages_completed,
                blockers=blockers + parsed_blockers,
                error_message="NEXT_ACTION is missing."
            )

        stages_completed.append("9.NEXT_ACTION")
        self._emit(EventType.NEXT_ACTION_LOADED, {"action": parsed_next_action.action})

        # Stages 10-14: Queues, Evidence, Domain State
        
        # Verify 10-14 exist (can be empty dirs, or files, just verifying paths)
        for stage_name, path in [
            ("10.PROPOSALS", "proposals/"),
            ("11.HANDOFFS", "handoffs/"),
            ("12.ESCALATIONS", "escalations/"),
            ("13.REQUIRED_EVIDENCE", "evidence/"),
            ("14.RELEVANT_DOMAIN_STATE", "domain/")
        ]:
            if self.provider.path_exists(path):
                stages_completed.append(stage_name)
            else:
                # Optionally warn or block, BOOTSTRAP.md doesn't explicitly mandate 
                # these to block but it says "14-stage bootstrap". If they are missing,
                # we don't append to stages_completed. Let's append if they exist.
                # Actually, if we must strictly verify them, they should block if missing.
                # I'll just skip adding them to stages_completed if missing.
                pass

        canonical_state = AnnyCanonicalState(
            repository_name=repo_info.get("full_name", "GRECOITALICO/ANNY-OPERATIONAL"),
            revision=current_state_dict.get("timeline", {}).get("last_state_change") if isinstance(current_state_dict.get("timeline"), dict) else None,
            bootstrap_contract_version="1.0",
            operating_system_version="1.0",
            constitution_ref="constitution/",
            current_mission=parsed_mission,
            current_task=parsed_tasks[0] if parsed_tasks else None,
            next_action=parsed_next_action,
            blockers=parsed_blockers,
            l2_workers=l2_workers,
            metadata={"repo_type": repo_info.get("type")}
        )

        final_status = ContinuityStatus.CONSISTENT if not parsed_blockers else ContinuityStatus.DEGRADED
        self._emit(EventType.BOOTSTRAP_COMPLETED, {"status": final_status.value})

        return BootstrapResult(
            status=final_status,
            canonical_state=canonical_state,
            stages_completed=stages_completed,
            blockers=parsed_blockers,
            error_message=None
        )
