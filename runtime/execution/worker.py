import uuid
import logging
import hashlib
import json
import re
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
from runtime.telemetry.telemetry import TelemetryEnvelope, TelemetryDomain
from runtime.orchestration.frontier import FrontierExecutor, FrontierExecutionReceipt

logger = logging.getLogger(__name__)


class WorkerManager:
    def __init__(self, workspace_manager, audit_manager=None, mcp_gateway=None, telemetry_collector=None, frontier_executor=None, model_registry=None):
        self.workspace_manager = workspace_manager
        self.audit_manager = audit_manager
        self.mcp_gateway = mcp_gateway
        self.telemetry_collector = telemetry_collector
        self.frontier_executor = frontier_executor
        self.model_registry = model_registry
        self.workers: Dict[str, WorkerDefinition] = {}
        self.deterministic_executor = DeterministicExecutor(workspace_manager)

    @staticmethod
    def _routing_class(executor_type: str) -> str:
        if executor_type == "DETERMINISTIC":
            return "DETERMINISTIC"
        if executor_type == "LOCAL_MODEL":
            return "LOCAL_MODEL"
        if executor_type == "REMOTE_MODEL":
            return "FRONTIER_MODEL"
        return "UNKNOWN"

    def _emit_telemetry(self, event_type: str, worker: WorkerDefinition, extra: Dict[str, Any] = None):
        if not self.telemetry_collector:
            return

        envelope = TelemetryEnvelope.create(
            component="worker",
            event_type=event_type,
            source="execution",
            execution_id=worker.execution_id,
            task_id=worker.task_id,
            worker_id=worker.worker_id,
            capability_id=worker.capability_id,
            capability_family=worker.capability_family,
            executor_type=worker.executor_type,
            routing_class=worker.routing_class,
            executor_id=worker.executor_id,
            model_id=worker.model_id,
            department_id=worker.department_id or "UNKNOWN",
            workspace_id=worker.workspace_id,
            status=worker.state.value,
            metadata=extra or {}
        )

        if worker.started_at and worker.finished_at:
            envelope.duration_ms = int((worker.finished_at - worker.started_at).total_seconds() * 1000)

        self.telemetry_collector.emit(envelope)

    def create_worker(self, context: TaskExecutionContext, selection: ExecutorSelection, task: Task) -> WorkerDefinition:
        worker_id = f"wrk-{uuid.uuid4().hex[:8]}"
        routing_class = self._routing_class(selection.executor_type.value)
        capability_family = getattr(getattr(self.mcp_gateway, "capability_registry", None), "get", lambda _: None)(task.capability_id)
        capability_family_name = getattr(capability_family, "family", None) or "unknown"

        context.routing_class = routing_class
        context.capability_family = capability_family_name
        context.department_id = task.department_id

        worker = WorkerDefinition(
            worker_id=worker_id,
            execution_id=context.execution_id,
            task_id=context.task_id,
            account_id=context.account_id,
            project_id=context.project_id,
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
            state=WorkerState.CREATED,
            department_id=task.department_id,
            routing_class=routing_class,
            capability_family=capability_family_name,
        )

        self.workers[worker_id] = worker
        self._emit_telemetry("task.routed", worker)
        return worker

    def get_worker(self, worker_id: str) -> Optional[WorkerDefinition]:
        return self.workers.get(worker_id)

    @staticmethod
    def _validate_frontier_receipt(
        receipt: FrontierExecutionReceipt,
        worker: WorkerDefinition,
        context: TaskExecutionContext,
        task: Task,
    ) -> None:
        """Reject uncorrelated or synthetic remote success material.

        Runtime can validate the receipt's bindings and digest but cannot turn a
        raw dictionary, locally generated digest, or missing evidence reference
        into physical remote execution evidence.
        """
        if not isinstance(receipt, FrontierExecutionReceipt):
            raise ExecutorSecurityError(
                "Frontier executor must return a correlated FrontierExecutionReceipt"
            )
        if (
            receipt.execution_id != context.execution_id
            or receipt.task_id != task.task_id
            or receipt.executor_id != worker.executor_id
            or receipt.model_id != worker.model_id
        ):
            raise ExecutorSecurityError("Frontier receipt identity binding mismatch")
        if not isinstance(receipt.result_data, dict) or not receipt.result_data:
            raise ExecutorSecurityError("Frontier receipt has no physical result payload")
        if not receipt.evidence_ref or not receipt.completed_at:
            raise ExecutorSecurityError("Frontier receipt lacks required execution evidence")
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.result_hash or ""):
            raise ExecutorSecurityError("Frontier receipt result hash is invalid")
        computed_hash = hashlib.sha256(
            json.dumps(receipt.result_data, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        if computed_hash != receipt.result_hash:
            raise ExecutorSecurityError("Frontier receipt result hash mismatch")

    @staticmethod
    def _validate_local_model_provenance(result, artifact_sha256: str) -> str:
        """Require Qwen's actual artifact and result provenance before success."""
        evidence = result.evidence if isinstance(getattr(result, "evidence", None), dict) else {}
        telemetry = evidence.get("telemetry") if isinstance(evidence.get("telemetry"), dict) else {}
        provenance = evidence.get("provenance") if isinstance(evidence.get("provenance"), dict) else {}
        result_hash = telemetry.get("result_hash")
        if provenance.get("executor_identity") != "QwenModelExecutor":
            raise ExecutorSecurityError("Local model executor provenance is missing")
        if provenance.get("artifact_sha256") != artifact_sha256:
            raise ExecutorSecurityError("Local model artifact provenance mismatch")
        if provenance.get("result_hash") != result_hash:
            raise ExecutorSecurityError("Local model result provenance mismatch")
        if not re.fullmatch(r"[0-9a-f]{64}", result_hash or ""):
            raise ExecutorSecurityError("Local model result hash is invalid")
        computed_hash = hashlib.sha256(
            json.dumps(result.result_data, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        if computed_hash != result_hash:
            raise ExecutorSecurityError("Local model result hash mismatch")
        return result_hash

    def list_workers(self) -> List[WorkerDefinition]:
        return list(self.workers.values())

    def start_worker(self, worker_id: str, context: TaskExecutionContext, task: Task, capability: CapabilityDefinition):
        worker = self.workers.get(worker_id)
        if not worker:
            raise ValueError(f"Worker {worker_id} not found")

        if worker.state != WorkerState.CREATED:
            raise ValueError(f"Worker {worker_id} is in state {worker.state}, cannot start")

        # Worker execution identity is derived from the submitted task/context
        # and cannot be self-escalated or retargeted between creation/start.
        if worker.capability_id != task.capability_id or worker.capability_id != context.capability_id:
            raise ExecutorSecurityError("Worker capability binding mismatch")
        if worker.account_id != task.account_id or worker.project_id != task.project_id:
            raise ExecutorSecurityError("Worker scope binding mismatch")
        if worker.deadline != context.deadline or worker.deadline != task.deadline:
            raise ExecutorSecurityError("Worker deadline binding mismatch")

        worker.state = WorkerState.STARTING
        worker.started_at = datetime.now(timezone.utc)
        worker.state = WorkerState.RUNNING
        self._emit_telemetry("execution.started", worker)

        try:
            if datetime.now(timezone.utc) > worker.deadline:
                raise TimeoutError("Deadline exceeded before execution")

            if worker.executor_type == "DETERMINISTIC":
                external_caps = {"fabric.read", "repository.read", "repository.search", "fabric.register"}
                if task.capability_id in external_caps:
                    if not self.mcp_gateway:
                        raise ValueError("MCP Gateway not configured for external capabilities")
                    from runtime.mcp import ToolRequest
                    req = ToolRequest.create(
                        tool_id=task.capability_id,
                        capability_id=task.capability_id,
                        worker_id=worker_id,
                        execution_id=context.execution_id,
                        input_data=task.input,
                        deadline=context.deadline
                    )
                    req.caller_context = {"workspace_path": context.workspace_path}
                    result = self.mcp_gateway.invoke(req)
                    if result.succeeded:
                        context.status = ExecutionStatus.SUCCEEDED
                        context.result = result.output_data
                        context.result_hash = result.evidence.get("result_hash")
                    else:
                        if result.status == "DENIED":
                            raise ExecutorSecurityError(result.error_message)
                        if result.status == "TIMED_OUT":
                            raise TimeoutError(result.error_message)
                        raise Exception(result.error_message)
                    self.deterministic_executor._finalize_workspace(task, context)
                else:
                    self.deterministic_executor.execute(task, context)

            elif worker.executor_type == "LOCAL_MODEL":
                real_artifact_path = os.environ.get("QWEN_MODEL_PATH")
                if not real_artifact_path or not os.path.exists(real_artifact_path):
                    context.status = ExecutionStatus.FAILED
                    context.failure_reason = FailureReason.EXECUTION_ERROR
                    context.error_message = "Local model unavailable"
                    worker.state = WorkerState.FAILED
                    self._emit_telemetry("execution.failed", worker, {"classification": "UNAVAILABLE"})
                    return

                context_package = ContextPackage(
                    task=task,
                    capability=capability,
                    authorized_input=task.input,
                    allowed_tools=capability.required_tools,
                    constraints=task.constraints,
                    evidence_policy=task.evidence_policy
                )
                model = getattr(self, "model_registry", None)
                definition = model.get(worker.model_id) if model and worker.model_id else None
                artifact_sha256 = getattr(definition, "artifact_sha256", None)
                if not artifact_sha256:
                    raise ExecutorSecurityError("Local model registry artifact SHA-256 is required")
                if not re.fullmatch(r"[0-9a-fA-F]{64}", artifact_sha256):
                    raise ExecutorSecurityError("Local model registry artifact SHA-256 is invalid")
                from runtime.execution.qwen_executor import QwenModelExecutor
                executor = QwenModelExecutor(
                    artifact_path=real_artifact_path,
                    expected_sha256=artifact_sha256,
                )
                result = executor.execute(context_package)
                if result.status != "SUCCEEDED":
                    context.status = ExecutionStatus.FAILED
                    context.failure_reason = FailureReason.EXECUTION_ERROR
                    context.error_message = f"Local model execution did not succeed: {result.status}"
                    context.result = result.result_data
                    context.result_hash = result.evidence.get("telemetry", {}).get("result_hash")
                    worker.state = WorkerState.FAILED
                    worker.finished_at = datetime.now(timezone.utc)
                    self._emit_telemetry(
                        "execution.failed",
                        worker,
                        {
                            "classification": "MODEL_EXECUTION_FAILED",
                            "model_status": result.status,
                        },
                    )
                    return
                result_hash = self._validate_local_model_provenance(
                    result, artifact_sha256
                )
                context.status = ExecutionStatus.SUCCEEDED
                context.result = result.result_data
                context.result_hash = result_hash
                self._emit_telemetry("inference_completed", worker, result.evidence.get("telemetry", {}))

            elif worker.executor_type in ("REMOTE_MODEL", "FRONTIER_MODEL"):
                from runtime.orchestration.plan import ExecutionPlan, RoutingClass
                plan = ExecutionPlan(
                    task_id=task.task_id,
                    capability_id=task.capability_id,
                    capability_version="1.0.0",
                    routing_class=RoutingClass.FRONTIER_MODEL,
                    executor_type="REMOTE_MODEL",
                    executor_id=worker.executor_id or "frontier-executor",
                    model_id=worker.model_id or "luna",
                    model_version="1.0.0",
                    policy_version="v1.0",
                )
                fe = self.frontier_executor
                if not isinstance(fe, FrontierExecutor) or not fe.is_authorized():
                    raise ExecutorSecurityError("Authorized FrontierExecutor injection is required")
                if fe.identity() != worker.executor_id:
                    raise ExecutorSecurityError("Frontier executor identity binding mismatch")

                if fe.is_available(plan.model_id):
                    receipt = fe.execute_plan(task, plan)
                    self._validate_frontier_receipt(receipt, worker, context, task)
                    context.status = ExecutionStatus.SUCCEEDED
                    context.result = receipt.result_data
                    context.result_hash = receipt.result_hash
                    context.evidence_ref = receipt.evidence_ref
                    self._emit_telemetry("inference_completed", worker, {
                        "executor": receipt.executor_id,
                        "result_hash": context.result_hash,
                        "evidence_ref": receipt.evidence_ref,
                    })
                else:
                    context.status = ExecutionStatus.FAILED
                    context.failure_reason = FailureReason.EXECUTION_ERROR
                    context.error_message = f"Frontier model {plan.model_id} unavailable"
                    worker.state = WorkerState.FAILED
                    self._emit_telemetry("execution.failed", worker, {"classification": "UNAVAILABLE"})
                    return

            else:
                context.status = ExecutionStatus.FAILED
                context.failure_reason = FailureReason.UNSUPPORTED_EXECUTOR
                worker.state = WorkerState.FAILED
                self._emit_telemetry("execution.failed", worker, {"classification": "UNSUPPORTED_EXECUTOR"})
                return

            if context.status == ExecutionStatus.SUCCEEDED:
                worker.state = WorkerState.SUCCEEDED
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("execution.completed", worker, {"result_hash": context.result_hash})
            elif context.status == ExecutionStatus.TIMED_OUT:
                worker.state = WorkerState.TIMED_OUT
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("execution.timeout", worker)
            elif context.status == ExecutionStatus.LIMIT_EXCEEDED:
                worker.state = WorkerState.LIMIT_EXCEEDED
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("execution.blocked", worker, {"exit_code": "LIMIT_EXCEEDED"})
            else:
                worker.state = WorkerState.FAILED
                worker.finished_at = datetime.now(timezone.utc)
                self._emit_telemetry("execution.failed", worker, {"exit_code": context.failure_reason.value if context.failure_reason else "UNKNOWN"})

        except TimeoutError:
            worker.state = WorkerState.TIMED_OUT
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.TIMED_OUT
            context.failure_reason = FailureReason.TIMEOUT
            self._emit_telemetry("execution.timeout", worker)

        except ExecutorLimitsExceeded as e:
            worker.state = WorkerState.LIMIT_EXCEEDED
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.LIMIT_EXCEEDED
            context.failure_reason = FailureReason.LIMIT_EXCEEDED
            context.error_message = str(e)
            self._emit_telemetry("execution.blocked", worker, {"exit_code": "LIMIT_EXCEEDED"})

        except ExecutorSecurityError as e:
            worker.state = WorkerState.FAILED
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.AUTHORIZATION_DENIED
            context.error_message = str(e)
            self._emit_telemetry("execution.blocked", worker, {"exit_code": "SECURITY_ERROR"})

        except Exception as e:
            logger.error(f"Worker {worker_id} crashed unexpectedly: {e}")
            worker.state = WorkerState.FAILED
            worker.finished_at = datetime.now(timezone.utc)
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.EXECUTION_ERROR
            context.error_message = f"Worker crash: {str(e)}"
            self._emit_telemetry("execution.failed", worker, {"exit_code": "CRASH", "reason": str(e)})

    def cancel_worker(self, worker_id: str):
        worker = self.workers.get(worker_id)
        if not worker:
            return
        if worker.state in (WorkerState.CREATED, WorkerState.STARTING, WorkerState.RUNNING):
            worker.state = WorkerState.CANCELLED
            worker.finished_at = datetime.now(timezone.utc)
            self._emit_telemetry("execution.cancelled", worker)

    def terminate_worker(self, worker_id: str):
        worker = self.workers.get(worker_id)
        if not worker:
            return
        if worker.state in (WorkerState.CREATED, WorkerState.STARTING, WorkerState.RUNNING):
            worker.state = WorkerState.TERMINATED
            self._emit_telemetry("execution.terminated", worker)
