"""Minimum governed Harness dispatcher for ANNY-native Runtime work.

The dispatcher is the boundary between an ANNY intent and Runtime execution.
It validates canonical Runtime identity/capability/context before producing a
handoff. It does not create authority and does not bypass ExecutionManager.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Set

from runtime.execution.capability import CapabilityRegistry, ExecutorType
from runtime.execution.models import ExecutionResult, ExecutionStatus, Task
from runtime.security.execution_context import ExecutionContext
from runtime.workspace.manager import WorkspaceManager, WorkspaceState


class DispatchStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"


class FailureCode(str, Enum):
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED"
    INVALID_REQUEST = "INVALID_REQUEST"
    MISSING_AUTHORIZATION = "MISSING_AUTHORIZATION"
    MISSING_EXECUTION_CONTEXT = "MISSING_EXECUTION_CONTEXT"
    CONTEXT_CAPABILITY_MISMATCH = "CONTEXT_CAPABILITY_MISMATCH"
    WORKSPACE_BINDING_FAILURE = "WORKSPACE_BINDING_FAILURE"
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    DUPLICATE_REPLAY_CONFLICT = "DUPLICATE_REPLAY_CONFLICT"
    EXECUTOR_UNAVAILABLE = "EXECUTOR_UNAVAILABLE"
    EVIDENCE_REQUIREMENT_UNSATISFIED = "EVIDENCE_REQUIREMENT_UNSATISFIED"
    STALE_SOURCE_SNAPSHOT = "STALE_SOURCE_SNAPSHOT"


_REJECT_CODES = {
    FailureCode.INVALID_REQUEST,
    FailureCode.UNKNOWN_CAPABILITY,
    FailureCode.CAPABILITY_DISABLED,
    FailureCode.MISSING_AUTHORIZATION,
    FailureCode.CONTEXT_CAPABILITY_MISMATCH,
    FailureCode.INVALID_INPUT,
    FailureCode.DUPLICATE_REPLAY_CONFLICT,
}


@dataclass(frozen=True)
class HarnessDispatchRequest:
    request_id: str
    capability_id: str
    requested_by: str
    actor_id: str
    actor_level: str
    execution_context_id: str
    account_id: str
    project_id: str
    workspace_id: str
    source_snapshot: str
    input: Dict[str, Any]
    constraints: Dict[str, Any]
    deadline: datetime
    workspace_policy: str
    evidence_policy: str
    authorization_scope: str
    idempotency_key: str

    def canonical_digest(self) -> str:
        payload = {
            "request_id": self.request_id,
            "capability_id": self.capability_id,
            "requested_by": self.requested_by,
            "actor_id": self.actor_id,
            "actor_level": self.actor_level,
            "execution_context_id": self.execution_context_id,
            "account_id": self.account_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "source_snapshot": self.source_snapshot,
            "input": self.input,
            "constraints": self.constraints,
            "deadline": self.deadline.isoformat(),
            "workspace_policy": self.workspace_policy,
            "evidence_policy": self.evidence_policy,
            "authorization_scope": self.authorization_scope,
            "idempotency_key": self.idempotency_key,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class HarnessExecutionHandoff:
    request_id: str
    execution_context_id: str
    task_id: str
    capability_id: str
    classification: str
    executor_type: str
    executor_id: Optional[str]
    account_id: str
    project_id: str
    workspace_id: str
    source_snapshot: str
    authorization_state: str
    evidence_policy: str


@dataclass(frozen=True)
class HarnessDispatchDecision:
    status: DispatchStatus
    request_id: str
    capability_id: str
    reason_code: Optional[FailureCode] = None
    message: str = ""
    handoff: Optional[HarnessExecutionHandoff] = None


@dataclass(frozen=True)
class HarnessResultEnvelope:
    request_id: str
    execution_id: Optional[str]
    capability_id: str
    dispatch_status: DispatchStatus
    execution_status: Optional[str]
    result: Optional[Dict[str, Any]]
    validation_status: Optional[str]
    evidence_ref: Optional[str]
    evidence_hash: Optional[str]
    failure_reason: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime] = None

    @classmethod
    def from_execution(
        cls,
        *,
        request_id: str,
        capability_id: str,
        execution: ExecutionResult,
        validation_status: Optional[str] = None,
    ) -> "HarnessResultEnvelope":
        dispatch_status = (
            DispatchStatus.ACCEPTED
            if execution.status == ExecutionStatus.SUCCEEDED
            else DispatchStatus.BLOCKED
        )
        failure_reason = (
            execution.failure_reason.value
            if execution.failure_reason is not None
            else execution.error_message
        )
        timestamp = execution.completed_at or datetime.now(timezone.utc)
        return cls(
            request_id=request_id,
            execution_id=execution.execution_id,
            capability_id=capability_id,
            dispatch_status=dispatch_status,
            execution_status=execution.status.value,
            result=execution.result_data,
            validation_status=validation_status,
            evidence_ref=execution.evidence_ref,
            evidence_hash=execution.result_hash,
            failure_reason=failure_reason,
            created_at=timestamp,
            completed_at=execution.completed_at,
        )


class HarnessDispatcher:
    """Fail-closed request validator for the future governed execution path."""

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        *,
        supported_execution_types: Optional[Set[ExecutorType]] = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.supported_execution_types = supported_execution_types or {
            ExecutorType.DETERMINISTIC,
            ExecutorType.LOCAL_MODEL,
            ExecutorType.REMOTE_MODEL,
        }
        self._idempotency: Dict[str, str] = {}

    def validate(
        self,
        request: HarnessDispatchRequest,
        context: Optional[ExecutionContext],
    ) -> HarnessDispatchDecision:
        if not isinstance(request, HarnessDispatchRequest):
            return self._reject(
                None,
                FailureCode.INVALID_REQUEST,
                "Invalid Harness request type",
            )

        required_strings = {
            "request_id": request.request_id,
            "capability_id": request.capability_id,
            "requested_by": request.requested_by,
            "actor_id": request.actor_id,
            "actor_level": request.actor_level,
            "execution_context_id": request.execution_context_id,
            "account_id": request.account_id,
            "project_id": request.project_id,
            "workspace_id": request.workspace_id,
            "source_snapshot": request.source_snapshot,
            "workspace_policy": request.workspace_policy,
            "evidence_policy": request.evidence_policy,
            "authorization_scope": request.authorization_scope,
            "idempotency_key": request.idempotency_key,
        }
        if any(not isinstance(value, str) or not value.strip() for value in required_strings.values()):
            return self._reject(
                request,
                FailureCode.INVALID_REQUEST,
                "Required Harness request fields are missing",
            )

        if not isinstance(request.input, dict) or not isinstance(request.constraints, dict):
            return self._reject(
                request,
                FailureCode.INVALID_REQUEST,
                "Input and constraints must be objects",
            )

        if request.deadline.tzinfo is None:
            return self._reject(
                request,
                FailureCode.INVALID_REQUEST,
                "Deadline must be timezone-aware",
            )

        if context is None:
            return self._reject(
                request,
                FailureCode.MISSING_EXECUTION_CONTEXT,
                "ExecutionContext is required",
            )

        if request.requested_by != context.actor_id or request.actor_id != context.actor_id:
            return self._reject(
                request,
                FailureCode.MISSING_AUTHORIZATION,
                "Caller identity does not match ExecutionContext actor",
            )

        if request.execution_context_id != context.execution_id:
            return self._reject(
                request,
                FailureCode.CONTEXT_CAPABILITY_MISMATCH,
                "ExecutionContext id mismatch",
            )

        if request.account_id != context.account_id or request.project_id != context.project_id:
            return self._reject(
                request,
                FailureCode.CONTEXT_CAPABILITY_MISMATCH,
                "Account/project binding mismatch",
            )

        if not context.workspace_id or request.workspace_id != context.workspace_id:
            return self._reject(
                request,
                FailureCode.WORKSPACE_BINDING_FAILURE,
                "Workspace is not bound to ExecutionContext",
            )

        now = datetime.now(timezone.utc)
        if not context.is_valid(now, context.generation):
            return self._reject(
                request,
                FailureCode.MISSING_AUTHORIZATION,
                "ExecutionContext is expired or temporally invalid",
            )

        if request.deadline <= now:
            return self._reject(
                request,
                FailureCode.STALE_SOURCE_SNAPSHOT,
                "Execution deadline has elapsed",
            )

        capability = self.capability_registry.get(request.capability_id)
        if capability is None:
            return self._reject(
                request,
                FailureCode.UNKNOWN_CAPABILITY,
                "Capability is not registered",
            )

        if not capability.enabled:
            return self._reject(
                request,
                FailureCode.CAPABILITY_DISABLED,
                "Capability is disabled",
            )

        if not context.has_capability(request.capability_id):
            return self._reject(
                request,
                FailureCode.MISSING_AUTHORIZATION,
                "ExecutionContext does not grant capability",
            )

        if capability.evidence_required and request.evidence_policy.lower() not in {"required", "mandatory"}:
            return self._reject(
                request,
                FailureCode.EVIDENCE_REQUIREMENT_UNSATISFIED,
                "Capability requires evidence but request evidence policy is weaker",
            )

        if not self._valid_input(request.capability_id, request.input):
            return self._reject(
                request,
                FailureCode.INVALID_INPUT,
                "Capability input contract is invalid",
            )

        digest = request.canonical_digest()
        if request.idempotency_key in self._idempotency:
            return self._reject(
                request,
                FailureCode.DUPLICATE_REPLAY_CONFLICT,
                "Idempotency key has already been used",
            )

        selected = capability.preferred_executor
        if selected not in self.supported_execution_types:
            return self._reject(
                request,
                FailureCode.UNSUPPORTED_CAPABILITY,
                f"Preferred executor {selected.value} is not supported by this Harness",
            )

        self._idempotency[request.idempotency_key] = digest

        handoff = HarnessExecutionHandoff(
            request_id=request.request_id,
            execution_context_id=request.execution_context_id,
            task_id=request.request_id,
            capability_id=request.capability_id,
            classification=selected.value,
            executor_type=selected.value,
            executor_id=None,
            account_id=request.account_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            source_snapshot=request.source_snapshot,
            authorization_state="AUTHORIZED_BY_EXECUTION_CONTEXT",
            evidence_policy=request.evidence_policy,
        )
        return HarnessDispatchDecision(
            status=DispatchStatus.ACCEPTED,
            request_id=request.request_id,
            capability_id=request.capability_id,
            message="Harness request validated; Runtime handoff is ready",
            handoff=handoff,
        )

    def dispatch_and_execute(
        self,
        request: HarnessDispatchRequest,
        context: Optional[ExecutionContext],
        *,
        execution_manager: Any,
        workspace_manager: WorkspaceManager,
    ) -> HarnessResultEnvelope | HarnessDispatchDecision:
        """Execute only after Harness validation and governed workspace binding.

        The Harness never invokes an executor directly. It creates a canonical
        Runtime Task and hands it to ExecutionManager after validating the
        caller context, source revision, and workspace ownership.
        """
        decision = self.validate(request, context)
        if decision.status is not DispatchStatus.ACCEPTED:
            return decision
        assert context is not None
        assert decision.handoff is not None

        try:
            workspace = workspace_manager.status(context, request.workspace_id)
        except (PermissionError, ValueError) as exc:
            return self._reject(
                request,
                FailureCode.WORKSPACE_BINDING_FAILURE,
                f"Workspace authorization failed: {type(exc).__name__}",
            )

        if workspace is None:
            return self._reject(
                request,
                FailureCode.WORKSPACE_BINDING_FAILURE,
                "ExecutionContext workspace does not exist",
            )
        if workspace.state not in {WorkspaceState.READY, WorkspaceState.ACTIVE, WorkspaceState.IDLE}:
            return self._reject(
                request,
                FailureCode.WORKSPACE_BINDING_FAILURE,
                f"Workspace is not executable: {workspace.state.name}",
            )
        if request.source_snapshot != workspace.source_revision:
            return self._reject(
                request,
                FailureCode.STALE_SOURCE_SNAPSHOT,
                "Source snapshot does not match the bound workspace revision",
            )

        repository_input = dict(request.input)
        raw_path = repository_input.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return self._reject(request, FailureCode.INVALID_INPUT, "Repository path is required")
        candidate = (workspace.local_path + "/" + raw_path).replace("\\\\", "/")

        from pathlib import Path
        workspace_root = Path(workspace.local_path).resolve()
        bound_path = Path(candidate).resolve()
        try:
            bound_path.relative_to(workspace_root)
        except ValueError:
            return self._reject(
                request,
                FailureCode.WORKSPACE_BINDING_FAILURE,
                "Repository path escapes the bound workspace",
            )

        repository_input["path"] = str(bound_path)
        task = Task(
            task_id=request.request_id,
            capability_id=request.capability_id,
            account_id=request.account_id,
            project_id=request.project_id,
            input=repository_input,
            constraints=dict(request.constraints),
            deadline=request.deadline,
            workspace_policy=request.workspace_policy,
            evidence_policy=request.evidence_policy,
            requested_by=context.actor_id,
            created_at=datetime.now(timezone.utc),
        )

        try:
            execution_context = execution_manager.submit_task(task)
            execution_manager.execute_sync(execution_context.execution_id)
        except Exception as exc:
            return HarnessResultEnvelope(
                request_id=request.request_id,
                execution_id=None,
                capability_id=request.capability_id,
                dispatch_status=DispatchStatus.BLOCKED,
                execution_status=None,
                result=None,
                validation_status=None,
                evidence_ref=None,
                evidence_hash=None,
                failure_reason=f"EXECUTION_DISPATCH_ERROR:{type(exc).__name__}",
                created_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        validation_status = "STRUCTURAL_VALID" if (
            request.capability_id == "repository.inspect"
            and isinstance(execution_context.result, dict)
            and isinstance(execution_context.result.get("is_git_repository"), bool)
        ) else "UNVERIFIED"
        execution_result = ExecutionResult(
            execution_id=execution_context.execution_id,
            task_id=execution_context.task_id,
            status=execution_context.status,
            result_data=execution_context.result,
            result_hash=execution_context.result_hash,
            error_message=execution_context.error_message,
            failure_reason=execution_context.failure_reason,
            duration_ms=execution_context.duration_ms,
            completed_at=execution_context.completed_at,
            evidence_ref=execution_context.evidence_ref,
        )
        return HarnessResultEnvelope.from_execution(
            request_id=request.request_id,
            capability_id=request.capability_id,
            execution=execution_result,
            validation_status=validation_status,
        )

    @staticmethod
    def _valid_input(capability_id: str, input_data: Dict[str, Any]) -> bool:
        if capability_id == "repository.inspect":
            return isinstance(input_data.get("path"), str) and bool(input_data["path"].strip())
        return True

    @staticmethod
    def _reject(
        request: Optional[HarnessDispatchRequest],
        reason: FailureCode,
        message: str,
    ) -> HarnessDispatchDecision:
        request_id = request.request_id if request is not None else "UNKNOWN"
        capability_id = request.capability_id if request is not None else "UNKNOWN"
        status = (
            DispatchStatus.REJECTED
            if reason in _REJECT_CODES
            else DispatchStatus.BLOCKED
        )
        return HarnessDispatchDecision(
            status=status,
            request_id=request_id,
            capability_id=capability_id,
            reason_code=reason,
            message=message,
        )
