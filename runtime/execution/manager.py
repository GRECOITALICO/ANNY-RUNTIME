from typing import List, Dict, Optional
import uuid

from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.capability import CapabilityRegistry
from runtime.execution.policy import RuntimePolicy
from runtime.execution.selector import ExecutorSelector
from runtime.execution.worker import WorkerManager


from runtime.telemetry.telemetry import TelemetryEnvelope

class ExecutionManager:
    """Manage queue and history of bounded workspace executions."""

    def __init__(self, workspace_manager: EphemeralWorkspaceManager, audit_manager=None, github_client=None, fabric_client=None, telemetry_collector=None, runtime_engine=None, continuity_engine=None):
        self._executions: Dict[str, TaskExecutionContext] = {}
        self._tasks: Dict[str, Task] = {}
        self.workspace_manager = workspace_manager
        self.runtime_engine = runtime_engine
        self.continuity_engine = continuity_engine or getattr(runtime_engine, "continuity_engine", None)

        self.registry = CapabilityRegistry()
        self.policy = RuntimePolicy()
        from runtime.execution.registry import ModelRegistry
        from runtime.core.config import get_data_dir
        registry_path = get_data_dir() / "registry" / "models.json"
        self.model_registry = ModelRegistry(storage_path=str(registry_path))
        self.selector = ExecutorSelector(self.model_registry)

        from runtime.mcp.registry import ToolRegistry
        from runtime.mcp.gateway import MCPGateway
        self.tool_registry = ToolRegistry()
        self.mcp_gateway = MCPGateway(
            tool_registry=self.tool_registry,
            capability_registry=self.registry,
            audit_manager=audit_manager,
            workspace_path="",
            fabric_data_dir=str(get_data_dir() / "fabric"),
            github_client=github_client,
            fabric_client=fabric_client
        )

        self.telemetry_collector = telemetry_collector
        self.worker_manager = WorkerManager(
            workspace_manager,
            audit_manager,
            mcp_gateway=self.mcp_gateway,
            telemetry_collector=self.telemetry_collector,
            model_registry=self.model_registry,
        )

    def submit_task(self, task: Task) -> TaskExecutionContext:
        execution_id = str(uuid.uuid4())
        if self.telemetry_collector:
            envelope = TelemetryEnvelope.create(
                component="manager",
                event_type="task.created",
                source="execution",
                execution_id=execution_id,
                task_id=task.task_id,
                capability_id=task.capability_id,
                department_id=task.department_id or "UNKNOWN",
                project_id=task.project_id
            )
            self.telemetry_collector.emit(envelope)
        cap = self.registry.get(task.capability_id)
        if not cap:
            raise ValueError(f"Unknown capability: {task.capability_id}")
        if not cap.enabled:
            raise ValueError(f"Capability is disabled: {task.capability_id}")
        if cap.side_effect != "read" and cap.deterministic_allowed:
            raise ValueError(f"Deterministic write capability requires a governed write executor: {task.capability_id}")

        selection = self.selector.select(task, cap, self.policy)
        try:
            workspace_path = self.workspace_manager.create_workspace(execution_id, task.project_id)
        except Exception as exc:
            raise RuntimeError(f"Failed to create workspace: {exc}") from exc

        routing_class = WorkerManager._routing_class(selection.executor_type.value)
        context = TaskExecutionContext(
            execution_id=execution_id,
            task_id=task.task_id,
            account_id=task.account_id,
            project_id=task.project_id,
            capability_id=task.capability_id,
            workspace_path=workspace_path,
            environment={},
            allowed_tools=list(cap.required_tools),
            deadline=task.deadline,
            resource_limits={"max_output_size": cap.max_output, "max_workspace_size": 10 * 1024 * 1024},
            network_policy=cap.network_policy,
            write_policy=cap.filesystem_policy,
            status=ExecutionStatus.QUEUED,
            department_id=task.department_id,
            capability_family=cap.family,
            routing_class=routing_class,
            # An execution workspace is an explicit ephemeral resource.  It is
            # not an implicit authorization for a repository or any other
            # path.  Repository resources must be supplied by a later,
            # authoritative resource-binding boundary.
            authorized_resource_id=f"workspace:{execution_id}",
            authorized_resource_project_id=task.project_id,
            authorized_resource_root=workspace_path,
            resource_access_mode="READ_ONLY",
            resource_kind="EPHEMERAL_WORKSPACE",
        )
        context.executor_type = selection.executor_type.value
        context.executor_id = selection.executor_id
        context.executor_version = selection.executor_version
        context.model_id = selection.model_id
        context.model_version = selection.model_version
        context.policy_version = selection.policy_version
        context.generation = self.runtime_engine.generation.current if self.runtime_engine else 1

        self._tasks[execution_id] = task
        self._executions[execution_id] = context
        self.worker_manager.create_worker(context, selection, task)

        if self.continuity_engine:
            from runtime.continuity.models import EventRecord, ContinuityRecord
            from runtime.continuity.events import ContinuityEventType
            from datetime import datetime, timezone
            
            record = ContinuityRecord.create(
                mission_id="DEFAULT_MISSION",
                task_id=task.task_id,
                step_id=task.capability_id,
                actor_id=getattr(task, "requested_by", "ANNY"),
                actor_level="L0",
                objective=f"Task queued: {task.task_id}",
                execution_id=execution_id
            )
            self.continuity_engine.save_record(record)

            event = EventRecord(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                sequence=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                mission_id="DEFAULT_MISSION",
                task_id=task.task_id,
                step_id=task.capability_id,
                parent_event_id=None,
                actor_id=getattr(task, "requested_by", "ANNY"),
                actor_level="L0",
                parent_actor_id=None,
                event_type=ContinuityEventType.TASK_CREATED,
                target=task.capability_id,
                intent=f"Task queued: {task.task_id}",
                inputs={
                    "execution_id": execution_id,
                    "routing_class": routing_class,
                    "executor_type": selection.executor_type.value,
                    "executor_id": selection.executor_id,
                    "model_id": selection.model_id,
                    "generation": context.generation,
                },
                repository=None, branch=None, commit_before=None, commit_after=None,
                files_changed=[], observation=f"Execution QUEUED ({execution_id})", result="QUEUED",
                evidence_refs=[], test_results=[], decision_ref=None, state_change="QUEUED",
                status="QUEUED", implementation_state="QUEUED", verification_state="PENDING", certification_state="NOT_CERTIFIED",
                blocker_refs=[], next_action="EXECUTE",
                execution_id=execution_id
            )
            self.continuity_engine.append_event(event)

        return context

    def execute_sync(self, execution_id: str) -> TaskExecutionContext:
        context = self._executions.get(execution_id)
        task = self._tasks.get(execution_id)
        if not context or not task:
            raise ValueError("Execution not found")

        cap = self.registry.get(task.capability_id)
        if not cap:
            raise ValueError("Capability not found for execution")
        worker = next((w for w in self.worker_manager.list_workers() if w.execution_id == execution_id), None)
        if not worker:
            raise ValueError("Worker not found for execution")

        if self.runtime_engine and context.generation is not None:
            from runtime.core.generation import StaleGenerationError
            try:
                self.runtime_engine.generation.fence(context.generation)
            except StaleGenerationError as e:
                import logging
                logging.getLogger(__name__).warning(f"Fencing execution {execution_id}: {e}")
                from runtime.execution.models import ExecutionStatus, FailureReason, WorkerState
                context.status = ExecutionStatus.FAILED
                context.failure_reason = FailureReason.AUTHORIZATION_DENIED
                context.error_message = str(e)
                worker.state = WorkerState.FAILED

                if self.continuity_engine:
                    from runtime.continuity.models import EventRecord
                    from runtime.continuity.events import ContinuityEventType
                    from datetime import datetime, timezone
                    event = EventRecord(
                        event_id=f"evt-{uuid.uuid4().hex[:8]}",
                        sequence=0,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        mission_id="DEFAULT_MISSION",
                        task_id=task.task_id,
                        step_id=task.capability_id,
                        parent_event_id=None,
                        actor_id=getattr(task, "requested_by", "ANNY"),
                        actor_level="L0",
                        parent_actor_id=None,
                        event_type=ContinuityEventType.ACTION_FAILED,
                        target=task.capability_id,
                        intent=f"Execution fenced for {execution_id}",
                        inputs={
                            "execution_id": execution_id,
                            "routing_class": context.routing_class,
                            "executor_type": context.executor_type,
                            "executor_id": context.executor_id,
                            "model_id": context.model_id,
                            "generation": context.generation,
                            "failure_reason": context.failure_reason.value if context.failure_reason else None,
                            "error_message": context.error_message
                        },
                        repository=None, branch=None, commit_before=None, commit_after=None,
                        files_changed=[], observation=f"Fencing failed: {str(e)}", result="FAILED",
                        evidence_refs=[], test_results=[], decision_ref=None, state_change="FAILED",
                        status="FAILED", implementation_state="FAILED", verification_state="FAILED", certification_state="NOT_CERTIFIED",
                        blocker_refs=[], next_action=None,
                        execution_id=execution_id
                    )
                    self.continuity_engine.append_event(event)

                return context

        self.worker_manager.start_worker(worker.worker_id, context, task, cap)
        self.worker_manager.terminate_worker(worker.worker_id)
        from runtime.execution.models import ExecutionStatus
        if context.status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT, ExecutionStatus.LIMIT_EXCEEDED):
            # Preserve evidence files to durable store before workspace destruction
            from runtime.core.config import get_data_dir
            from pathlib import Path
            import shutil
            base_dir = self.continuity_engine.data_dir if self.continuity_engine else get_data_dir()
            evidence_dir = Path(base_dir) / "evidence" / execution_id
            evidence_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir = Path(context.workspace_path)
            for fname in ("evidence.json", "reproducibility.json", "observability.json"):
                fpath = workspace_dir / fname if fname != "observability.json" else workspace_dir / "logs" / "observability.json"
                if fpath.exists():
                    shutil.copy2(fpath, evidence_dir / fpath.name)


            if task.workspace_policy == "destroy_on_complete":
                self.workspace_manager.destroy_workspace(context.workspace_path)

        if self.continuity_engine:
            from runtime.continuity.models import EventRecord
            from runtime.continuity.events import ContinuityEventType
            from datetime import datetime, timezone
            
            rec = self.continuity_engine.get_record(execution_id)
            if not rec:
                recs = self.continuity_engine.get_records_by_task(task.task_id)
                rec = recs[-1] if recs else None
            if rec:
                rec.status = context.status.value
                rec.completed_at = datetime.now(timezone.utc).isoformat()
                rec.verification_state = "VERIFIED" if context.status == ExecutionStatus.SUCCEEDED else "FAILED"
                if context.result_hash:
                    rec.evidence_refs.append(context.result_hash)
                self.continuity_engine.save_record(rec)

            event = EventRecord(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                sequence=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                mission_id="DEFAULT_MISSION",
                task_id=task.task_id,
                step_id=task.capability_id,
                parent_event_id=None,
                actor_id=getattr(task, "requested_by", "ANNY"),
                actor_level="L0",
                parent_actor_id=None,
                event_type=ContinuityEventType.ACTION_COMPLETED if context.status == ExecutionStatus.SUCCEEDED else ContinuityEventType.ACTION_FAILED,
                target=task.capability_id,
                intent=f"Execution completed for {execution_id}",
                inputs={
                    "execution_id": execution_id,
                    "routing_class": context.routing_class,
                    "executor_type": context.executor_type,
                    "executor_id": context.executor_id,
                    "model_id": context.model_id,
                    "generation": context.generation,
                    "failure_reason": context.failure_reason.value if context.failure_reason else None,
                    "error_message": context.error_message
                },
                repository=None, branch=None, commit_before=None, commit_after=None,
                files_changed=[], observation=f"Execution status: {context.status.value}", result=context.status.value,
                evidence_refs=[context.result_hash] if context.result_hash else [], test_results=[], decision_ref=None, state_change=context.status.value,
                status=context.status.value, implementation_state=context.status.value, verification_state="VERIFIED" if context.status == ExecutionStatus.SUCCEEDED else "FAILED", certification_state="NOT_CERTIFIED",
                blocker_refs=[], next_action=None,
                execution_id=execution_id
            )
            self.continuity_engine.append_event(event)

    def get_execution(self, execution_id: str) -> Optional[TaskExecutionContext]:
        if execution_id in self._executions:
            return self._executions[execution_id]
        if self.continuity_engine:
            recon = self.continuity_engine.reconstruct_execution(execution_id)
            if recon:
                from datetime import datetime, timezone
                status_val = recon.get("status", "FAILED")
                try:
                    exec_status = ExecutionStatus(status_val)
                except ValueError:
                    exec_status = ExecutionStatus.FAILED
                
                context = TaskExecutionContext(
                    execution_id=execution_id,
                    task_id=recon.get("task_id", execution_id),
                    account_id="RECONSTRUCTED",
                    project_id="RECONSTRUCTED",
                    capability_id=recon.get("capability_id", "unknown"),
                    workspace_path="",
                    environment={},
                    allowed_tools=[],
                    deadline=datetime.now(timezone.utc),
                    resource_limits={},
                    network_policy="none",
                    write_policy="none",
                    status=exec_status,
                    routing_class=recon.get("routing_class"),
                    executor_type=recon.get("executor_type"),
                    executor_id=recon.get("executor_id"),
                    model_id=recon.get("model_id"),
                    generation=recon.get("generation"),
                )
                self._executions[execution_id] = context
                return context
        return None

    def get_all_executions(self) -> List[TaskExecutionContext]:
        return sorted(list(self._executions.values()), key=lambda x: x.execution_id)
