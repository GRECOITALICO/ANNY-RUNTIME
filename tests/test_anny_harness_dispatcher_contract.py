"""Deterministic contract tests only; these never invoke Runtime execution."""

from datetime import datetime, timedelta, timezone

from runtime.execution.harness_contract import (
    DispatchDecision,
    DispatchReason,
    HarnessDispatchContract,
    HarnessDispatchRequest,
    ReceiptContractSlot,
)
from runtime.execution.models import Task
from runtime.security.execution_context import ExecutionContext


def _task(capability_id="repository.inspect", evidence_policy="required"):
    return Task(
        task_id="harness-contract-task",
        capability_id=capability_id,
        account_id="contract-account",
        project_id="contract-project",
        input={"path": "/contract/repository"},
        constraints={"read_only": True},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        workspace_policy="retain",
        evidence_policy=evidence_policy,
        requested_by="contract-caller",
        created_at=datetime.now(timezone.utc),
    )


def _context(capabilities=frozenset({"repository.inspect"}), workspace_id="contract-workspace"):
    now = datetime.now(timezone.utc)
    return ExecutionContext(
        tenant_id="contract-tenant",
        account_id="contract-account",
        project_id="contract-project",
        anny_instance_id="contract-anny",
        runtime_id="contract-runtime",
        session_id="contract-session",
        actor_id="ANNY",
        operation_id="contract-operation",
        execution_id="contract-context",
        generation=1,
        issued_at=now,
        expires_at=now + timedelta(minutes=1),
        workspace_id=workspace_id,
        capabilities=set(capabilities),
    )


def _request(**overrides):
    values = {
        "request_id": "dispatch-request-001",
        "task": _task(),
        "actor_id": "ANNY",
        "actor_level": "L0",
        "execution_context_id": "contract-context",
        "workspace_id": "contract-workspace",
        "source_snapshot_id": "sha256:contract-source-snapshot",
        "timeout_seconds": 30,
        "authorization_scope": frozenset({"repository.inspect"}),
        "idempotency_key": "repository.inspect:contract-request-001",
        "receipt_contract": ReceiptContractSlot("harness-receipt-v1", True, True),
    }
    values.update(overrides)
    return HarnessDispatchRequest(**values)


def test_valid_repository_inspect_request_has_a_contract_representation_only():
    outcome = HarnessDispatchContract().evaluate(_request(), _context())
    assert outcome.decision is DispatchDecision.ACCEPTED
    assert outcome.reason is DispatchReason.ACCEPTED_FOR_FUTURE_HANDOFF
    assert outcome.is_success is True


def test_unknown_capability_is_rejected_without_executor_fallback():
    outcome = HarnessDispatchContract().evaluate(_request(task=_task("unknown.capability")), _context())
    assert outcome.decision is DispatchDecision.REJECTED
    assert outcome.reason is DispatchReason.UNKNOWN_CAPABILITY


def test_known_but_not_contract_supported_capability_is_not_fallback_dispatched():
    outcome = HarnessDispatchContract().evaluate(_request(task=_task("filesystem.inspect")), _context())
    assert outcome.decision is DispatchDecision.UNSUPPORTED
    assert outcome.reason is DispatchReason.UNSUPPORTED_CAPABILITY


def test_missing_authorization_is_rejected():
    outcome = HarnessDispatchContract().evaluate(_request(authorization_scope=frozenset()), _context())
    assert outcome.decision is DispatchDecision.REJECTED
    assert outcome.reason is DispatchReason.MISSING_AUTHORIZATION


def test_missing_execution_context_is_rejected():
    outcome = HarnessDispatchContract().evaluate(_request(), None)
    assert outcome.decision is DispatchDecision.REJECTED
    assert outcome.reason is DispatchReason.MISSING_EXECUTION_CONTEXT


def test_context_capability_mismatch_is_rejected():
    outcome = HarnessDispatchContract().evaluate(_request(), _context(capabilities=frozenset()))
    assert outcome.decision is DispatchDecision.REJECTED
    assert outcome.reason is DispatchReason.CONTEXT_CAPABILITY_MISMATCH


def test_required_evidence_cannot_complete_without_receipt_contract_slot():
    outcome = HarnessDispatchContract().evaluate(_request(receipt_contract=None), _context())
    assert outcome.decision is DispatchDecision.BLOCKED
    assert outcome.reason is DispatchReason.EVIDENCE_POLICY_UNSATISFIED
    assert outcome.is_success is False


def test_replay_conflict_is_not_a_successful_dispatch():
    request = _request()
    outcome = HarnessDispatchContract().evaluate(request, _context(), replay_keys={request.idempotency_key})
    assert outcome.decision is DispatchDecision.REJECTED
    assert outcome.reason is DispatchReason.REPLAY_CONFLICT
    assert outcome.is_success is False


def test_executable_harness_dispatcher_uses_workspace_and_execution_manager_without_bypass(tmp_path, monkeypatch):
    from runtime.execution.harness_dispatcher import HarnessDispatcher
    from runtime.execution.models import ExecutionStatus, TaskExecutionContext
    from runtime.workspace.manager import Workspace, WorkspaceState

    class FakeWorkspaceManager:
        def status(self, context, workspace_id):
            return Workspace(
                workspace_id=workspace_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                actor_scope=[context.actor_id],
                repository="repository",
                source_revision="sha:current",
                state=WorkspaceState.READY,
                generation=context.generation,
                local_path="/tmp/governed-workspace",
                created_at="now",
            )

    class FakeExecutionManager:
        def __init__(self):
            self.submitted = None
            self.worker_manager = type("Workers", (), {})()
            self.worker = type(
                "Worker",
                (),
                {"execution_id": "runtime-execution-001", "worker_id": "wrk-test", "executor_id": "deterministic"},
            )()
            self.worker_manager.list_workers = lambda: [self.worker]
            self.context = TaskExecutionContext(
                execution_id="runtime-execution-001",
                task_id="dispatch-request-001",
                account_id="contract-account",
                project_id="contract-project",
                capability_id="repository.inspect",
                workspace_path="/tmp/ephemeral/runtime-execution-001",
                environment={},
                allowed_tools=[],
                deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
                resource_limits={},
                network_policy="disabled",
                write_policy="read_only",
                status=ExecutionStatus.SUCCEEDED,
                result={
                    "path": "/tmp/governed-workspace/repository",
                    "is_git_repository": True,
                    "head": "sha:current",
                },
                result_hash="result-hash",
            )

        def submit_task(self, task):
            self.submitted = task
            return self.context

        def execute_sync(self, execution_id):
            assert execution_id == self.context.execution_id
            return self.context

    from dataclasses import replace
    from runtime.execution import harness_dispatcher as dispatcher_module
    evidence_dir = tmp_path / "evidence" / "runtime-execution-001"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "evidence.json").write_text("{}", encoding="utf-8")
    (evidence_dir / "reproducibility.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(dispatcher_module, "get_data_dir", lambda: tmp_path)
    dispatcher = HarnessDispatcher()
    request = _request(
        task=replace(_task(), input={"path": "contract/repository"}),
        source_snapshot_id="sha:current",
    )
    manager = FakeExecutionManager()

    result = dispatcher.dispatch_and_execute(
        request,
        _context(),
        execution_manager=manager,
        workspace_manager=FakeWorkspaceManager(),
    )

    assert result.execution_status == "SUCCEEDED"
    assert result.evidence_hash == "result-hash"
    assert manager.submitted.input["path"] == "/tmp/governed-workspace/contract/repository"


def test_executable_dispatcher_blocks_stale_source_before_manager_execution():
    from runtime.execution.harness_dispatcher import HarnessDispatcher
    from runtime.workspace.manager import Workspace, WorkspaceState

    class FakeWorkspaceManager:
        def status(self, context, workspace_id):
            return Workspace(
                workspace_id=workspace_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                actor_scope=[context.actor_id],
                repository="repository",
                source_revision="sha:new",
                state=WorkspaceState.READY,
                generation=context.generation,
                local_path="/tmp/governed-workspace",
                created_at="now",
            )

    class ForbiddenExecutionManager:
        worker_manager = None

        def submit_task(self, task):
            raise AssertionError("stale source must block before execution")

    result = HarnessDispatcher().dispatch_and_execute(
        _request(source_snapshot_id="sha:old"),
        _context(),
        execution_manager=ForbiddenExecutionManager(),
        workspace_manager=FakeWorkspaceManager(),
    )

    assert result.decision is DispatchDecision.BLOCKED
    assert result.reason is DispatchReason.STALE_SOURCE_SNAPSHOT
