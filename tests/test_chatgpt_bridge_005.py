"""Current Bridge contract tests.

The ``TEST_ONLY`` fixtures below model a local test boundary. They do not
claim an external issuer, external secret authority, or physical execution.
Bridge capability eligibility is resolved only through the Runtime registry.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from runtime.api.bridge import BridgeRouter
from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import ExecutionStatus, Task, TaskExecutionContext
from runtime.journal.journal import JournalEntry, OperationJournal
from runtime.security.execution_context import ExecutionContext
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


class MockHandler:
    def __init__(self, command="POST", headers=None):
        self.command = command
        self.headers = headers or {}
        self.status = None
        self.body = b""
        self.wfile = self

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def write(self, data):
        self.body += data

    def flush(self):
        pass


class TestOnlySecretBackend:
    """Fixture boundary only; it is not a live secret authority."""

    def retrieve(self, reference):
        return b"test-bridge-token" if reference == "bridge_token" else None


class _Generation:
    def __init__(self, current):
        self.current = current


class _Runtime:
    def __init__(self, generation):
        self.generation = _Generation(generation)


def _test_context(**changes):
    now = datetime.now(timezone.utc)
    values = dict(
        tenant_id="TEST_ONLY_tenant", account_id="TEST_ONLY_account",
        project_id="TEST_ONLY_project", anny_instance_id="TEST_ONLY_anny",
        runtime_id="TEST_ONLY_runtime", session_id="TEST_ONLY_session",
        actor_id="TEST_ONLY_actor", operation_id="TEST_ONLY_operation",
        execution_id="TEST_ONLY_execution", generation=7,
        issued_at=now - timedelta(seconds=1), expires_at=now + timedelta(minutes=1),
        workspace_id="TEST_ONLY_workspace", capabilities={"filesystem.inspect"},
    )
    values.update(changes)
    return ExecutionContext(**values)


@pytest.fixture
def bridge_runtime(tmp_path):
    """Real ExecutionManager admission with a TEST_ONLY authenticated context."""
    manager = ExecutionManager(EphemeralWorkspaceManager(str(tmp_path / "workspaces")))
    context = _test_context()
    router = BridgeRouter({
        "secret_backend": TestOnlySecretBackend(),
        "execution_manager": manager,
        "execution_context": context,
        "runtime_engine": _Runtime(context.generation),
    })
    return router, manager, context


def _request(router, tmp_path, payload, *, token="test-bridge-token"):
    handler = MockHandler(headers={"X-Bridge-Token": token})
    with patch("runtime.api.bridge.get_data_dir", return_value=tmp_path):
        router.dispatch(type("Parsed", (), {"path": "/api/v1/bridge/tasks"})(), handler, json.dumps(payload).encode())
    return handler, json.loads(handler.body)


def test_bridge_auth_missing(bridge_runtime):
    router, _, _ = bridge_runtime
    handler = MockHandler(headers={})
    router.dispatch(type("Parsed", (), {"path": "/api/v1/bridge/tasks"})(), handler)
    assert handler.status == 401
    assert json.loads(handler.body)["error"] == "BRIDGE_AUTH_ERROR"


def test_bridge_auth_invalid(bridge_runtime, tmp_path):
    router, _, _ = bridge_runtime
    handler, response = _request(router, tmp_path, {"intent": "x", "requested_capability": "filesystem.inspect"}, token="invalid")
    assert handler.status == 401
    assert response["error"] == "BRIDGE_AUTH_ERROR"


def test_bridge_rejects_missing_execution_context(bridge_runtime, tmp_path):
    router, _, _ = bridge_runtime
    router.context.pop("execution_context")
    handler, response = _request(router, tmp_path, {"intent": "inspect", "requested_capability": "filesystem.inspect"})
    assert handler.status == 403
    assert response["error"] == "POLICY_DENIED"


@pytest.mark.parametrize("context_changes,runtime_generation", [
    ({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}, 7),
    ({}, 8),
])
def test_bridge_rejects_expired_or_stale_execution_context(bridge_runtime, tmp_path, context_changes, runtime_generation):
    router, _, _ = bridge_runtime
    invalid = _test_context(**context_changes)
    router.context["execution_context"] = invalid
    router.context["runtime_engine"] = _Runtime(runtime_generation)
    handler, response = _request(router, tmp_path, {"intent": "inspect", "requested_capability": "filesystem.inspect"})
    assert handler.status == 403
    assert response["error"] == "POLICY_DENIED"


def test_bridge_rejects_unknown_and_disabled_registry_capabilities(bridge_runtime, tmp_path):
    router, _, _ = bridge_runtime
    for capability in ("unknown.capability", "fabric.register"):
        handler, response = _request(router, tmp_path, {"intent": "deny", "requested_capability": capability})
        assert handler.status == 404
        assert response["error"] == "CAPABILITY_NOT_FOUND"


def test_bridge_rejects_prohibited_fields_and_constraint_override(bridge_runtime, tmp_path):
    router, _, _ = bridge_runtime
    handler, response = _request(router, tmp_path, {
        "intent": "inspect", "requested_capability": "filesystem.inspect", "worker_id": "forged",
    })
    assert handler.status == 400
    assert response["error"] == "BRIDGE_INVALID_REQUEST"

    handler, response = _request(router, tmp_path, {
        "intent": "inspect", "requested_capability": "filesystem.inspect", "constraints": {"network": "allow_all"},
    })
    assert handler.status == 403
    assert response["error"] == "POLICY_DENIED"


def test_bridge_uses_real_manager_admission_and_reports_actual_terminal_state(bridge_runtime, tmp_path):
    router, manager, context = bridge_runtime
    handler, response = _request(router, tmp_path, {
        "intent": "inspect a missing workspace file",
        "requested_capability": "filesystem.inspect",
        "input": {"path": "missing.txt"},
    })

    assert handler.status == 201
    execution = manager._executions[response["execution_id"]]
    assert execution.admission_state == "AUTHORIZED"
    assert execution.admitted_capability_id == "filesystem.inspect"
    assert execution.account_id == context.account_id
    assert execution.project_id == context.project_id
    assert response["status"] == execution.status.name
    assert response["status"] in {status.name for status in ExecutionStatus}


def test_direct_executor_bypass_remains_denied(tmp_path):
    """A capability name alone cannot replace canonical manager admission."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.txt").write_text("ok")
    now = datetime.now(timezone.utc)
    task = Task("bridge-direct", "filesystem.inspect", "account", "project", {"path": "fixture.txt"}, {}, now + timedelta(minutes=1), "keep", "required", "TEST_ONLY", now)
    context = TaskExecutionContext("direct", task.task_id, task.account_id, task.project_id, task.capability_id, str(workspace), {}, [], task.deadline, {}, "disabled", "read_only")
    DeterministicExecutor(EphemeralWorkspaceManager(str(tmp_path / "unused"))).execute(task, context)
    assert context.status == ExecutionStatus.FAILED
    assert context.error_message == "CANONICAL_ADMISSION_REQUIRED"


def test_bridge_status_reads_durable_journal_with_authenticated_request(bridge_runtime, tmp_path):
    router, _, context = bridge_runtime
    journal = OperationJournal(tmp_path)
    journal.record(JournalEntry(
        entry_id="TEST_ONLY-entry", operation_id="TEST_ONLY-task", tenant_id=context.tenant_id,
        account_id=context.account_id, project_id=context.project_id, execution_id="TEST_ONLY-execution",
        session_id=context.session_id, actor_id=context.actor_id, workspace_id="", tool="filesystem.inspect",
        state="FAILED", started_at=datetime.now(timezone.utc).isoformat(), runtime_generation=context.generation,
        metadata={"intent": "test", "source": "bridge"},
    ))
    handler = MockHandler(command="GET", headers={"X-Bridge-Token": "test-bridge-token"})
    with patch("runtime.api.bridge.get_data_dir", return_value=tmp_path):
        router.dispatch(type("Parsed", (), {"path": "/api/v1/bridge/tasks/TEST_ONLY-task"})(), handler)
    assert handler.status == 200
    assert json.loads(handler.body)["state"] == "FAILED"
