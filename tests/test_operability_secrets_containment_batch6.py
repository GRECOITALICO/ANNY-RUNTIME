"""Focused non-production evidence tests for Batch 6.

Fixtures named AUTHORIZED_TEST_CONTEXT model an external authority adapter only;
they do not establish that a live external issuer or secret authority exists.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runtime.core.config import RuntimeConfig
from runtime.core.engine import RuntimeEngine, RuntimeState
from runtime.intelligence.evidence_builder import EvidenceBuilder
from runtime.sandbox.policy import SandboxPolicy
from runtime.secrets.backend import FileSecretBackend
from runtime.secrets.broker import AuthoritativeSecretBroker, SecretAccessGrant
from runtime.security.execution_context import ExecutionContext
from runtime.security.path_containment import ContainmentError
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


def _AUTHORIZED_TEST_CONTEXT(**changes):
    now = datetime.now(timezone.utc)
    values = dict(
        tenant_id="tenant-a", account_id="account-a", project_id="project-a",
        anny_instance_id="anny-a", runtime_id="runtime-a", session_id="session-a",
        actor_id="actor-a", operation_id="operation-a", execution_id="execution-a",
        generation=7, issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=2), workspace_id="workspace-a",
        capabilities={"SECRET_USE"},
    )
    values.update(changes)
    return ExecutionContext(**values)


def _grant(context, **changes):
    values = dict(
        secret_reference="github-token", tenant_id=context.tenant_id,
        account_id=context.account_id, project_id=context.project_id,
        runtime_id=context.runtime_id, execution_id=context.execution_id,
        operation_id=context.operation_id, generation=context.generation,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        authorization_reference="AUTHZ-TEST-ONLY", policy_reference="POLICY-TEST-ONLY",
    )
    values.update(changes)
    return SecretAccessGrant(**values)


def test_ephemeral_workspace_rejects_direct_intermediate_and_sibling_symlink_escapes(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "project").symlink_to(outside, target_is_directory=True)
    manager = EphemeralWorkspaceManager(str(root))

    with pytest.raises(ContainmentError):
        manager.create_workspace("execution", "project")
    with pytest.raises(ContainmentError):
        manager.get_workspace_paths(str(tmp_path / "root-sibling"))


def test_file_secret_storage_rejects_symlink_and_arbitrary_reference(tmp_path):
    backend = FileSecretBackend(str(tmp_path), b"k" * 32)
    outside = tmp_path / "outside"
    outside.mkdir()
    (backend.secrets_dir / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ContainmentError):
        backend.retrieve("escape")
    with pytest.raises(ValueError, match="UNSAFE_REFERENCE"):
        backend.retrieve("../arbitrary")


def test_evidence_output_uses_canonical_containment_for_output_files(tmp_path):
    builder = EvidenceBuilder(str(tmp_path / "evidence"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (Path(builder.output_dir) / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ContainmentError):
        builder._output_path("escape/record.json")
    with pytest.raises(ContainmentError):
        builder._output_path("../record.json")


def test_sandbox_policy_rejects_sibling_and_symlink_scope_escapes(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    sibling = tmp_path / "allowed-sibling"
    sibling.mkdir()
    policy = SandboxPolicy("sandbox", "tenant", "actor", "workspace", filesystem_scope=[str(allowed)])
    assert policy.allows_path(str(allowed / "file.txt"))
    assert not policy.allows_path(str(sibling / "file.txt"))

    outside = tmp_path / "outside"
    outside.mkdir()
    (allowed / "escape").symlink_to(outside, target_is_directory=True)
    assert not policy.allows_path(str(allowed / "escape" / "file.txt"))


def test_browser_profile_uses_canonical_containment(monkeypatch, tmp_path):
    import runtime.browser.broker_server as browser

    profile_root = tmp_path / "profiles"
    monkeypatch.setattr(browser, "PROFILE_BASE", profile_root)
    assert browser._validate_profile("session-a") == profile_root / "session-a"
    outside = tmp_path / "outside"
    outside.mkdir()
    (profile_root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ContainmentError):
        browser._validate_profile("escape")


def test_secret_broker_is_blocked_without_external_authority_and_never_leaks_marker(tmp_path, capsys, caplog):
    marker = b"TEST_SECRET_BATCH6_MARKER_DO_NOT_LOG"
    backend = FileSecretBackend(str(tmp_path), b"k" * 32)
    backend.store("github-token", marker)
    context = _AUTHORIZED_TEST_CONTEXT()
    grant = _grant(context)
    broker = AuthoritativeSecretBroker(backend)

    with pytest.raises(PermissionError, match="SECRET_AUTHORITY_UNAVAILABLE_BLOCKED"):
        broker.use("github-token", context, grant, current_generation=7)

    captured = capsys.readouterr()
    assert marker.decode() not in captured.out + captured.err + caplog.text


def test_secret_broker_accepts_only_explicit_authorized_test_authority(tmp_path, capsys, caplog):
    marker = b"TEST_SECRET_BATCH6_MARKER_DO_NOT_LOG"
    backend = FileSecretBackend(str(tmp_path), b"k" * 32)
    backend.store("github-token", marker)
    context = _AUTHORIZED_TEST_CONTEXT()
    grant = _grant(context)
    broker = AuthoritativeSecretBroker(backend, authority_verifier=lambda received, ctx: received == grant and ctx == context)

    handle = broker.use("github-token", context, grant, current_generation=7)
    assert handle is not None
    assert handle.value == marker
    handle.release()
    with pytest.raises(RuntimeError, match="released"):
        _ = handle.value

    captured = capsys.readouterr()
    assert marker.decode() not in captured.out + captured.err + caplog.text


@pytest.mark.parametrize("grant_changes,context_changes", [
    ({"tenant_id": "tenant-b"}, {}),
    ({"project_id": "project-b"}, {}),
    ({"secret_reference": "other-secret"}, {}),
    ({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}, {}),
    ({}, {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}),
])
def test_secret_broker_rejects_wrong_or_expired_scope(tmp_path, grant_changes, context_changes):
    backend = FileSecretBackend(str(tmp_path), b"k" * 32)
    backend.store("github-token", b"value")
    context = _AUTHORIZED_TEST_CONTEXT(**context_changes)
    broker = AuthoritativeSecretBroker(backend, authority_verifier=lambda _grant, _context: True)
    with pytest.raises(PermissionError):
        broker.use("github-token", context, _grant(context, **grant_changes), current_generation=7)


class _ExecutionRegistry:
    def __init__(self, states):
        self._states = states

    def get_all_executions(self):
        return [type("Execution", (), {"status": type("Status", (), {"value": state})()})() for state in self._states]


def test_shutdown_distinguishes_idle_active_timeout_duplicate_and_unavailable_registry(tmp_path):
    idle = RuntimeEngine(RuntimeConfig(data_dir=str(tmp_path / "idle")))
    idle._state = RuntimeState.READY
    idle.execution_manager = _ExecutionRegistry([])
    assert idle.shutdown()["shutdown_state"] == "ENGINE_STOPPED"
    assert idle.shutdown()["shutdown_state"] == "ALREADY_STOPPED"

    active = RuntimeEngine(RuntimeConfig(data_dir=str(tmp_path / "active")))
    active._state = RuntimeState.READY
    active.execution_manager = _ExecutionRegistry(["QUEUED", "RUNNING"])
    result = active.shutdown(drain_timeout_seconds=0)
    assert result["shutdown_state"] == "TIMEOUT_ACTIVE_EXECUTIONS"
    assert active.state == RuntimeState.DRAINING

    unavailable = RuntimeEngine(RuntimeConfig(data_dir=str(tmp_path / "unavailable")))
    unavailable._state = RuntimeState.READY
    result = unavailable.shutdown()
    assert result["shutdown_state"] == "ENGINE_STOPPED_UNVERIFIED_DRAIN"
    assert result["process_state"] == "NOT_IMPLEMENTED"


def test_admin_restart_is_explicitly_blocked_not_a_physical_restart():
    from runtime.admin.routes import AdminRouter

    router = AdminRouter({})
    assert router.handle_admin_restart({}) == "/"
