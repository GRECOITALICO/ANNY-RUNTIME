from datetime import datetime, timedelta, timezone

from runtime.harness.dispatcher import (
    DispatchStatus,
    FailureCode,
    HarnessDispatchRequest,
    HarnessDispatcher,
)
from runtime.security.execution_context import ExecutionContext


def make_context(**overrides):
    values = {
        "tenant_id": "tenant-local",
        "account_id": "acct-local",
        "project_id": "project-local",
        "anny_instance_id": "anny-local",
        "runtime_id": "runtime-local",
        "session_id": "session-local",
        "actor_id": "ANNY",
        "operation_id": "op-local",
        "execution_id": "exec-local",
        "generation": 1,
        "issued_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        "workspace_id": "workspace-local",
        "capabilities": {"repository.inspect"},
    }
    values.update(overrides)
    return ExecutionContext(**values)


def make_request(**overrides):
    values = {
        "request_id": "req-001",
        "capability_id": "repository.inspect",
        "requested_by": "ANNY",
        "actor_id": "ANNY",
        "actor_level": "L0",
        "execution_context_id": "exec-local",
        "account_id": "acct-local",
        "project_id": "project-local",
        "workspace_id": "workspace-local",
        "source_snapshot": "git-head:UNVERIFIED",
        "input": {"path": "/tmp/repository"},
        "constraints": {},
        "deadline": datetime.now(timezone.utc) + timedelta(seconds=30),
        "workspace_policy": "retain",
        "evidence_policy": "required",
        "authorization_scope": "repository.inspect:read",
        "idempotency_key": "idem-001",
    }
    values.update(overrides)
    return HarnessDispatchRequest(**values)


def test_valid_repository_inspect_request_is_accepted():
    decision = HarnessDispatcher().validate(make_request(), make_context())

    assert decision.status is DispatchStatus.ACCEPTED
    assert decision.handoff is not None
    assert decision.handoff.capability_id == "repository.inspect"
    assert decision.handoff.executor_type == "DETERMINISTIC"
    assert decision.handoff.authorization_state == "AUTHORIZED_BY_EXECUTION_CONTEXT"


def test_unknown_capability_is_rejected():
    request = make_request(capability_id="repository.unknown")
    decision = HarnessDispatcher().validate(request, make_context(capabilities={"repository.unknown"}))

    assert decision.status is DispatchStatus.REJECTED
    assert decision.reason_code is FailureCode.UNKNOWN_CAPABILITY


def test_missing_authorization_is_rejected():
    decision = HarnessDispatcher().validate(make_request(), make_context(capabilities=set()))

    assert decision.status is DispatchStatus.REJECTED
    assert decision.reason_code is FailureCode.MISSING_AUTHORIZATION


def test_missing_execution_context_is_blocked():
    decision = HarnessDispatcher().validate(make_request(), None)

    assert decision.status is DispatchStatus.BLOCKED
    assert decision.reason_code is FailureCode.MISSING_EXECUTION_CONTEXT


def test_context_capability_mismatch_is_rejected():
    decision = HarnessDispatcher().validate(
        make_request(project_id="different-project"),
        make_context(),
    )

    assert decision.status is DispatchStatus.REJECTED
    assert decision.reason_code is FailureCode.CONTEXT_CAPABILITY_MISMATCH


def test_workspace_binding_failure_is_blocked():
    decision = HarnessDispatcher().validate(
        make_request(workspace_id="other-workspace"),
        make_context(),
    )

    assert decision.status is DispatchStatus.BLOCKED
    assert decision.reason_code is FailureCode.WORKSPACE_BINDING_FAILURE


def test_evidence_requirement_cannot_be_downgraded():
    decision = HarnessDispatcher().validate(
        make_request(evidence_policy="optional"),
        make_context(),
    )

    assert decision.status is DispatchStatus.BLOCKED
    assert decision.reason_code is FailureCode.EVIDENCE_REQUIREMENT_UNSATISFIED


def test_replay_conflict_is_rejected():
    dispatcher = HarnessDispatcher()
    request = make_request()
    first = dispatcher.validate(request, make_context())
    second = dispatcher.validate(request, make_context())

    assert first.status is DispatchStatus.ACCEPTED
    assert second.status is DispatchStatus.REJECTED
    assert second.reason_code is FailureCode.DUPLICATE_REPLAY_CONFLICT


def test_actor_identity_cannot_be_supplied_as_authority():
    decision = HarnessDispatcher().validate(
        make_request(actor_id="OTHER_ACTOR", requested_by="OTHER_ACTOR"),
        make_context(),
    )

    assert decision.status is DispatchStatus.REJECTED
    assert decision.reason_code is FailureCode.MISSING_AUTHORIZATION


def test_expired_execution_context_is_rejected():
    expired = make_context(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    decision = HarnessDispatcher().validate(make_request(), expired)

    assert decision.status is DispatchStatus.REJECTED
    assert decision.reason_code is FailureCode.MISSING_AUTHORIZATION


def test_invalid_repository_inspect_input_is_rejected():
    decision = HarnessDispatcher().validate(
        make_request(input={"path": ""}),
        make_context(),
    )

    assert decision.status is DispatchStatus.REJECTED
    assert decision.reason_code is FailureCode.INVALID_INPUT
