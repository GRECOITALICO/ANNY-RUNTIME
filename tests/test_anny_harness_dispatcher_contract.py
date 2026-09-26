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
