import uuid
import logging
from datetime import datetime, timezone
import os
from typing import Dict, List, Optional, Any

from runtime.execution.models import (
    WorkerDefinition, WorkerState, Task, TaskExecutionContext, ExecutionStatus, FailureReason
)
from runtime.execution.capability import CapabilityDefinition
from runtime.execution.selector import ExecutorSelection
from runtime.execution.interfaces import ContextPackage, ModelExecutor
from runtime.execution.deterministic_executor import DeterministicExecutor, ExecutorSecurityError, ExecutorLimitsExceeded

logger = logging.getLogger(__name__)

class WorkerManager:
    def __init__(self, workspace_manager, audit_manager=None):
        self.workspace_manager = workspace_manager
        self.audit_manager = audit_manager
        self.workers: Dict[str, WorkerDefinition] = {}
        
        # Executor bindings
        self.deterministic_executor = DeterministicExecutor(workspace_manager)

    def _emit_telemetry(self, event_type: str, worker: WorkerDefinition, extra: Dict[str, Any] = None):
        if not self.audit_manager:
            return
            
        payload = {
            "worker_id": worker.worker_id,
            "execution_id": worker.execution_id,
            "task_id": worker.task_id,
            "capability_id": worker.capability_id,
            "executor_type": worker.executor_type,
            "executor_id": worker.executor_id,
            "model_id": worker.model_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        if worker.started_at and worker.finished_at:
            payload["duration"] = int((worker.finished_at - worker.started_at).total_seconds() * 1000)
            
        if extra:
            payload.update(extra)
            
        self.audit_manager.record("system", event_type, "WorkerManager", "SUCCESS", str(payload))

    def create_worker(self, context: TaskExecutionContext, selection: ExecutorSelection, task: Task) -> WorkerDefinition:
        worker_id = f"wrk-{uuid.uuid4().hex[:8]}"
        
        # Worker inherently inherits constraints and isolation from Context
        worker = WorkerDefinition(
            worker_id=worker_id,
            execution_id=context.execution_id,
            task_id=context.task_id,
            capability_id=context.capability_id,
            executor_type=selection.executor_type.value,
            executor_id=selection.executor_id,
            model_id=selection.model_id,
            workspace_id=context.workspace_path,
            created_at=datetime.now(timezone.utc),
            deadline=context.deadline,
            resource_limits=context.resource_limits,
            network_policy=context.network_policy,
            filesystem_policy=context.write_policy,
            state=WorkerState.CREATED
        )
        
        self.workers[worker_id] = worker
        self._emit_telemetry("worker_created", worker)
        return worker

    def get_worker(self, worker_id: str) -> Optional[WorkerDefinition]:
        return self.workers.get(worker_id)

    def list_workers(self) -> List[WorkerDefinition]:
        return list(self.workers.values())

    def start_worker(self, worker_id: str, context: TaskExecutionContext, task: Task, capability: CapabilityDefinition):
        worker = self.workers.get(worker_id)
        if not worker:
            raise ValueError(f"Worker {worker_id} not found")
            
        if worker.state != WorkerState.CREATED:
            raise ValueError(f"Worker {worker_id} is in state {worker.state}, cannot start")
            
        worker.state = WorkerState.STARTING
        self._emit_telemetry("worker_starting", worker)
        
        worker.started_at = datetime.now(timezone.utc)
        worker.state = WorkerState.RUNNING
        self._emit_telemetry("worker_started", worker)
        
        try:
            # Re-enforce deadline
            if datetime.now(timezone.utc) > worker.deadline:
                raise TimeoutError("Deadline exceeded before execution")
                
            # Model execution flow (currently only Deterministic implemented)
            if worker.executor_type == "DETERMINISTIC":
                # Deterministic executor gets full context for now
                self.deterministic_executor.execute(task, context)
            elif worker.executor_type == "LOCAL_MODEL":
                context_package = ContextPackage(
                    task=task,
                    capability=capability,
                    authorized_input=task.input,
                    allowed_tools=capability.required_tools,
                    constraints=task.constraints,
                    evidence_policy=task.evidence_policy
                )
                from runtime.execution.qwen_executor import QwenModelExecutor
                dummy_artifact_path = os.path.join(self.workspace_manager.base_dir, "qwen_mock.json")
                if not os.path.exists(dummy_artifact_path):
                    with open(dummy_artifact_path, "w") as f:
                        f.write("{}")
                
                executor = QwenModelExecutor(artifact_path=dummy_artifact_path)
                result = executor.execute(context_package)
                
                context.status = ExecutionStatus.SUCCEEDED
                context.result = result.result_data
                context.result_hash = result.evidence.get("telemetry", {}).get("result_hash")
                
                self._emit_telemetry("inference_completed", worker, result.evidence.get("telemetry", {}))
                
            else:
                raise NotImplementedError(f"Execution for {worker.executor_type} not yet implemented")
                
            # Map ExecutionStatus to WorkerState
            if context.status == ExecutionStatus.SUCCEEDED:
                worker.state = WorkerState.SUCCEEDED
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("worker_completed", worker, {"result_hash": context.result_hash})
            elif context.status == ExecutionStatus.TIMED_OUT:
                worker.state = WorkerState.TIMED_OUT
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("worker_timed_out", worker)
            elif context.status == ExecutionStatus.LIMIT_EXCEEDED:
                worker.state = WorkerState.LIMIT_EXCEEDED
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("worker_failed", worker, {"exit_code": "LIMIT_EXCEEDED"})
            else:
                worker.state = WorkerState.FAILED
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("worker_failed", worker, {"exit_code": context.failure_reason.value if context.failure_reason else "UNKNOWN"})
                
        except TimeoutError:
            worker.state = WorkerState.TIMED_OUT
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.TIMED_OUT
            context.failure_reason = FailureReason.TIMEOUT
            self._emit_telemetry("worker_timed_out", worker)
            
        except ExecutorLimitsExceeded as e:
            worker.state = WorkerState.LIMIT_EXCEEDED
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.LIMIT_EXCEEDED
            context.failure_reason = FailureReason.LIMIT_EXCEEDED
            context.error_message = str(e)
            self._emit_telemetry("worker_failed", worker, {"exit_code": "LIMIT_EXCEEDED"})
            
        except ExecutorSecurityError as e:
            worker.state = WorkerState.FAILED
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.AUTHORIZATION_DENIED
            context.error_message = str(e)
            self._emit_telemetry("worker_failed", worker, {"exit_code": "SECURITY_ERROR"})
            
        except Exception as e:
            # Catch unexpected crashes (Phase 10)
            logger.error(f"Worker {worker_id} crashed unexpectedly: {e}")
            worker.state = WorkerState.FAILED
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.EXECUTION_ERROR
            context.error_message = f"Worker crash: {str(e)}"
            self._emit_telemetry("worker_failed", worker, {"exit_code": "CRASH", "reason": str(e)})

    def cancel_worker(self, worker_id: str):
        worker = self.workers.get(worker_id)
        if not worker:
            return
            
        if worker.state in (WorkerState.CREATED, WorkerState.STARTING, WorkerState.RUNNING):
            worker.state = WorkerState.CANCELLED
            worker.finished_at = datetime.now(timezone.utc)
            self._emit_telemetry("worker_cancelled", worker)

    def terminate_worker(self, worker_id: str):
        worker = self.workers.get(worker_id)
        if not worker:
            return
            
        if worker.state in (WorkerState.CREATED, WorkerState.STARTING, WorkerState.RUNNING):
            worker.state = WorkerState.TERMINATED
            self._emit_telemetry("worker_terminated", worker)
