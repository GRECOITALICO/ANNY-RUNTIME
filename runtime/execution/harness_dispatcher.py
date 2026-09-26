"""Governed ANNY Harness dispatcher using canonical Runtime execution primitives.

This is the executable bridge from a validated Harness request to
ExecutionManager. It performs workspace/source binding before invoking the
existing Runtime executor and verifies required local evidence before returning
success.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from runtime.core.config import get_data_dir
from runtime.execution.harness_contract import (
    DispatchDecision,
    DispatchReason,
    HarnessDispatchContract,
    HarnessDispatchOutcome,
    HarnessDispatchRequest,
    HarnessResultEnvelope,
)
from runtime.security.execution_context import ExecutionContext
from runtime.workspace.manager import WorkspaceManager, WorkspaceState


class HarnessDispatcher:
    """Single governed entrypoint for ANNY-native Runtime execution."""

    def __init__(self, contract: Optional[HarnessDispatchContract] = None) -> None:
        self.contract = contract or HarnessDispatchContract()

    def dispatch_and_execute(
        self,
        request: HarnessDispatchRequest,
        execution_context: Optional[ExecutionContext],
        *,
        execution_manager: Any,
        workspace_manager: WorkspaceManager,
        replay_keys: frozenset[str] = frozenset(),
    ) -> HarnessResultEnvelope | HarnessDispatchOutcome:
        """Validate the request and execute through canonical Runtime managers.

        The dispatcher never calls an executor directly. ExecutionManager and
        WorkerManager remain the execution authorities after validation.
        """
        outcome = self.contract.evaluate(
            request,
            execution_context,
            replay_keys=replay_keys,
            executor_available=True,
            source_snapshot_current=True,
        )
        if outcome.decision is not DispatchDecision.ACCEPTED:
            return outcome

        if execution_context is None:
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.MISSING_EXECUTION_CONTEXT,
                request.request_id,
            )

        try:
            workspace = workspace_manager.status(execution_context, request.workspace_id)
        except (PermissionError, ValueError):
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.WORKSPACE_BINDING_FAILURE,
                request.request_id,
            )

        if workspace is None or workspace.state not in {
            WorkspaceState.READY,
            WorkspaceState.ACTIVE,
            WorkspaceState.IDLE,
        }:
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.WORKSPACE_BINDING_FAILURE,
                request.request_id,
            )

        if workspace.source_revision != request.source_snapshot_id:
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.STALE_SOURCE_SNAPSHOT,
                request.request_id,
            )

        raw_path = request.task.input.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return HarnessDispatchOutcome(
                DispatchDecision.REJECTED,
                DispatchReason.INVALID_INPUT,
                request.request_id,
            )

        workspace_root = Path(workspace.local_path).resolve()
        target = (workspace_root / raw_path).resolve()
        try:
            target.relative_to(workspace_root)
        except ValueError:
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.WORKSPACE_BINDING_FAILURE,
                request.request_id,
            )

        deadline = min(
            request.task.deadline,
            datetime.now(timezone.utc) + timedelta(seconds=request.timeout_seconds),
        )
        bound_task = replace(
            request.task,
            input={**request.task.input, "path": str(target)},
            deadline=deadline,
        )

        try:
            runtime_context = execution_manager.submit_task(bound_task, execution_context=execution_context)
        except Exception:
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.EXECUTOR_UNAVAILABLE,
                request.request_id,
            )

        worker = next(
            (
                item
                for item in execution_manager.worker_manager.list_workers()
                if item.execution_id == runtime_context.execution_id
            ),
            None,
        )
        if worker is None:
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.EXECUTOR_UNAVAILABLE,
                request.request_id,
            )

        try:
            execution_manager.execute_sync(runtime_context.execution_id)
        except Exception:
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.EXECUTOR_UNAVAILABLE,
                request.request_id,
            )

        if request.task.capability_id == "repository.inspect":
            valid_result = (
                isinstance(runtime_context.result, dict)
                and isinstance(runtime_context.result.get("is_git_repository"), bool)
            )
            runtime_context.validation_status = (
                "STRUCTURAL_VALID" if valid_result else "INVALID_RESULT"
            )
            if not valid_result:
                return HarnessDispatchOutcome(
                    DispatchDecision.BLOCKED,
                    DispatchReason.EVIDENCE_POLICY_UNSATISFIED,
                    request.request_id,
                )

        if request.task.evidence_policy == "required":
            evidence_dir = Path(get_data_dir()) / "evidence" / runtime_context.execution_id
            required_files = (
                evidence_dir / "evidence.json",
                evidence_dir / "reproducibility.json",
            )
            if not all(path.is_file() for path in required_files):
                return HarnessDispatchOutcome(
                    DispatchDecision.BLOCKED,
                    DispatchReason.EVIDENCE_POLICY_UNSATISFIED,
                    request.request_id,
                )

        result = HarnessResultEnvelope.from_runtime(runtime_context)
        if result.execution_status != "SUCCEEDED":
            return HarnessDispatchOutcome(
                DispatchDecision.BLOCKED,
                DispatchReason.EXECUTOR_UNAVAILABLE,
                request.request_id,
            )
        return result
