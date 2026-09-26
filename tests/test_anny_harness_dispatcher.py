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


def test_dispatch_and_execute_binds_repository_path_to_governed_workspace():
    from pathlib import Path
    from runtime.execution.models import ExecutionStatus, TaskExecutionContext
    from runtime.workspace.manager import Workspace, WorkspaceState

    class FakeWorkspaceManager:
        def __init__(self):
            self.workspace = Workspace(
                workspace_id="workspace-local",
                tenant_id="tenant-local",
                project_id="project-local",
                actor_scope=["ANNY"],
                repository="GRECOITALICO/ANNY-RUNTIME",
                source_revision="abc123",
                state=WorkspaceState.READY,
                generation=1,
                local_path="/tmp/anny-governed-workspace",
                created_at="now",
            )

        def status(self, context, workspace_id):
            assert workspace_id == self.workspace.workspace_id
            return self.workspace

    class FakeExecutionManager:
        def __init__(self):
            self.submitted = None
            self.context = TaskExecutionContext(
                execution_id="runtime-exec-001",
                task_id="req-001",
                account_id="acct-local",
                project_id="project-local",
                capability_id="repository.inspect",
                workspace_path="/tmp/ephemeral/runtime-exec-001",
                environment={},
                allowed_tools=[],
                deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
                resource_limits={},
                network_policy="disabled",
                write_policy="read_only",
                status=ExecutionStatus.SUCCEEDED,
                result={"path": "/tmp/anny-governed-workspace/repository", "is_git_repository": True, "head": "abc123"},
                result_hash="result-hash",
            )

        def submit_task(self, task):
            self.submitted = task
            return self.context

        def execute_sync(self, execution_id):
            assert execution_id == self.context.execution_id
            return self.context

    dispatcher = HarnessDispatcher()
    request = make_request(source_snapshot="abc123", input={"path": "repository"})
    context = make_context()
    manager = FakeExecutionManager()

    result = dispatcher.dispatch_and_execute(
        request,
        context,
        execution_manager=manager,
        workspace_manager=FakeWorkspaceManager(),
    )

    assert result.dispatch_status is DispatchStatus.ACCEPTED
    assert result.execution_id == "runtime-exec-001"
    assert result.validation_status == "STRUCTURAL_VALID"
    assert result.evidence_hash == "result-hash"
    assert manager.submitted is not None
    assert Path(manager.submitted.input["path"]).as_posix() == "/tmp/anny-governed-workspace/repository"


def test_dispatch_blocks_stale_source_snapshot_before_execution():
    from runtime.workspace.manager import Workspace, WorkspaceState

    class FakeWorkspaceManager:
        def status(self, context, workspace_id):
            return Workspace(
                workspace_id=workspace_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                actor_scope=[context.actor_id],
                repository="repo",
                source_revision="current-revision",
                state=WorkspaceState.READY,
                generation=context.generation,
                local_path="/tmp/workspace",
                created_at="now",
            )

    class ForbiddenExecutionManager:
        def submit_task(self, task):
            raise AssertionError("execution must not start on stale snapshot")

    request = make_request(source_snapshot="old-revision")
    result = HarnessDispatcher().dispatch_and_execute(
        request,
        make_context(),
        execution_manager=ForbiddenExecutionManager(),
        workspace_manager=FakeWorkspaceManager(),
    )

    assert result.status is DispatchStatus.BLOCKED
    assert result.reason_code is FailureCode.STALE_SOURCE_SNAPSHOT


def test_dispatch_blocks_path_escape_before_execution():
    from runtime.workspace.manager import Workspace, WorkspaceState

    class FakeWorkspaceManager:
        def status(self, context, workspace_id):
            return Workspace(
                workspace_id=workspace_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                actor_scope=[context.actor_id],
                repository="repo",
                source_revision="git-head:UNVERIFIED",
                state=WorkspaceState.READY,
                generation=context.generation,
                local_path="/tmp/workspace",
                created_at="now",
            )

    class ForbiddenExecutionManager:
        def submit_task(self, task):
            raise AssertionError("execution must not start on path escape")

    request = make_request(input={"path": "../outside"})
    result = HarnessDispatcher().dispatch_and_execute(
        request,
        make_context(),
        execution_manager=ForbiddenExecutionManager(),
        workspace_manager=FakeWorkspaceManager(),
    )

    assert result.status is DispatchStatus.BLOCKED
    assert result.reason_code is FailureCode.WORKSPACE_BINDING_FAILURE
