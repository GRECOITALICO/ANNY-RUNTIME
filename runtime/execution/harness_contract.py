"""Fail-closed schema boundary for a future ANNY Harness dispatcher.

This module deliberately validates a dispatch *request* only.  It does not
call ``ExecutionManager``, start a worker, emit a durable receipt, or establish
Runtime execution/ANNY-first-use evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import AbstractSet, Optional

from runtime.execution.capability import CapabilityRegistry
from runtime.execution.models import Task, TaskExecutionContext, WorkerDefinition
from runtime.security.execution_context import ExecutionContext


class DispatchDecision(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"


class DispatchReason(str, Enum):
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    MISSING_AUTHORIZATION = "MISSING_AUTHORIZATION"
    MISSING_EXECUTION_CONTEXT = "MISSING_EXECUTION_CONTEXT"
    CONTEXT_CAPABILITY_MISMATCH = "CONTEXT_CAPABILITY_MISMATCH"
    WORKSPACE_BINDING_FAILURE = "WORKSPACE_BINDING_FAILURE"
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    REPLAY_CONFLICT = "REPLAY_CONFLICT"
    EXECUTOR_UNAVAILABLE = "EXECUTOR_UNAVAILABLE"
    EVIDENCE_POLICY_UNSATISFIED = "EVIDENCE_POLICY_UNSATISFIED"
    STALE_SOURCE_SNAPSHOT = "STALE_SOURCE_SNAPSHOT"
    ACCEPTED_FOR_FUTURE_HANDOFF = "ACCEPTED_FOR_FUTURE_HANDOFF"


@dataclass(frozen=True)
class ReceiptContractSlot:
    """Required future receipt fields; this is not a stored receipt."""

    receipt_contract_id: str
    durable_evidence_required: bool
    evidence_hash_required: bool


@dataclass(frozen=True)
class HarnessDispatchRequest:
    """Harness request binding semantic fields to existing Runtime models.

    ``task`` owns the existing Task names: task_id, capability_id, account_id,
    project_id, input, constraints, deadline, workspace_policy, evidence_policy,
    requested_by, and created_at.  ``execution_context_id`` binds to the
    existing ``ExecutionContext.execution_id``; it is not a second context ID.
    """

    request_id: str
    task: Task
    actor_id: str
    actor_level: str
    execution_context_id: str
    workspace_id: str
    source_snapshot_id: str
    timeout_seconds: int
    authorization_scope: frozenset[str]
    idempotency_key: str
    receipt_contract: Optional[ReceiptContractSlot]

    @property
    def input_payload(self) -> dict:
        return self.task.input


@dataclass(frozen=True)
class HarnessDispatchOutcome:
    decision: DispatchDecision
    reason: DispatchReason
    request_id: str

    @property
    def is_success(self) -> bool:
        return self.decision is DispatchDecision.ACCEPTED


@dataclass(frozen=True)
class HarnessExecutionHandoff:
    """Stable mapping after a future dispatcher has selected a Runtime worker."""

    execution_id: str
    worker_id: str
    executor_id: str
    capability_id: str
    execution_context_id: str
    workspace_id: str
    source_snapshot_id: str
    authorization_decision: DispatchDecision
    routing_class: Optional[str]

    @classmethod
    def from_runtime(
        cls,
        context: TaskExecutionContext,
        worker: WorkerDefinition,
        source_snapshot_id: str,
    ) -> "HarnessExecutionHandoff":
        return cls(
            execution_id=context.execution_id,
            worker_id=worker.worker_id,
            executor_id=worker.executor_id,
            capability_id=context.capability_id,
            execution_context_id=context.execution_id,
            workspace_id=context.workspace_path,
            source_snapshot_id=source_snapshot_id,
            authorization_decision=DispatchDecision.ACCEPTED,
            routing_class=context.routing_class,
        )


@dataclass(frozen=True)
class HarnessResultEnvelope:
    """Result shape for a future handoff; it is not proof of execution."""

    execution_id: str
    capability_id: str
    execution_status: str
    capability_result: object
    validation_status: Optional[str]
    evidence_reference: Optional[str]
    evidence_hash: Optional[str]
    failure_classification: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]

    @classmethod
    def from_runtime(cls, context: TaskExecutionContext) -> "HarnessResultEnvelope":
        return cls(
            execution_id=context.execution_id,
            capability_id=context.capability_id,
            execution_status=context.status.value,
            capability_result=context.result,
            validation_status=context.validation_status,
            evidence_reference=context.evidence_ref,
            evidence_hash=context.result_hash,
            failure_classification=context.failure_reason.value if context.failure_reason else None,
            started_at=context.started_at.isoformat() if context.started_at else None,
            completed_at=context.completed_at.isoformat() if context.completed_at else None,
        )


class HarnessDispatchContract:
    """Pure, fail-closed validation boundary; no Runtime dispatch occurs here."""

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        supported_capabilities: frozenset[str] = frozenset({"repository.inspect"}),
    ):
        self.registry = registry or CapabilityRegistry()
        self.supported_capabilities = supported_capabilities

    def evaluate(
        self,
        request: HarnessDispatchRequest,
        execution_context: Optional[ExecutionContext],
        replay_keys: AbstractSet[str] = frozenset(),
        executor_available: bool = True,
        source_snapshot_current: bool = True,
    ) -> HarnessDispatchOutcome:
        if not request.request_id or not request.idempotency_key:
            return self._reject(request, DispatchReason.INVALID_INPUT)
        if request.idempotency_key in replay_keys:
            return self._reject(request, DispatchReason.REPLAY_CONFLICT)
        if not self.registry.get(request.task.capability_id):
            return self._reject(request, DispatchReason.UNKNOWN_CAPABILITY)
        if request.task.capability_id not in self.supported_capabilities:
            return HarnessDispatchOutcome(
                DispatchDecision.UNSUPPORTED,
                DispatchReason.UNSUPPORTED_CAPABILITY,
                request.request_id,
            )
        if not request.task.input or not self._valid_input(request.task):
            return self._reject(request, DispatchReason.INVALID_INPUT)
        if execution_context is None:
            return self._reject(request, DispatchReason.MISSING_EXECUTION_CONTEXT)
        if not request.authorization_scope or request.task.capability_id not in request.authorization_scope:
            return self._reject(request, DispatchReason.MISSING_AUTHORIZATION)
        if not execution_context.has_capability(request.task.capability_id):
            return self._reject(request, DispatchReason.CONTEXT_CAPABILITY_MISMATCH)
        if (
            request.execution_context_id != execution_context.execution_id
            or request.actor_id != execution_context.actor_id
            or request.task.project_id != execution_context.project_id
        ):
            return self._reject(request, DispatchReason.CONTEXT_CAPABILITY_MISMATCH)
        if not request.workspace_id or request.workspace_id != execution_context.workspace_id:
            return self._reject(request, DispatchReason.WORKSPACE_BINDING_FAILURE)
        if not request.source_snapshot_id or not source_snapshot_current:
            return self._block(request, DispatchReason.STALE_SOURCE_SNAPSHOT)
        if request.timeout_seconds <= 0:
            return self._reject(request, DispatchReason.INVALID_INPUT)
        if request.task.evidence_policy == "required" and (
            request.receipt_contract is None
            or not request.receipt_contract.durable_evidence_required
            or not request.receipt_contract.evidence_hash_required
        ):
            return self._block(request, DispatchReason.EVIDENCE_POLICY_UNSATISFIED)
        if not executor_available:
            return self._block(request, DispatchReason.EXECUTOR_UNAVAILABLE)
        return HarnessDispatchOutcome(
            DispatchDecision.ACCEPTED,
            DispatchReason.ACCEPTED_FOR_FUTURE_HANDOFF,
            request.request_id,
        )

    @staticmethod
    def _valid_input(task: Task) -> bool:
        if task.capability_id == "repository.inspect":
            return isinstance(task.input.get("path"), str) and bool(task.input["path"])
        return True

    @staticmethod
    def _reject(request: HarnessDispatchRequest, reason: DispatchReason) -> HarnessDispatchOutcome:
        return HarnessDispatchOutcome(DispatchDecision.REJECTED, reason, request.request_id)

    @staticmethod
    def _block(request: HarnessDispatchRequest, reason: DispatchReason) -> HarnessDispatchOutcome:
        return HarnessDispatchOutcome(DispatchDecision.BLOCKED, reason, request.request_id)
