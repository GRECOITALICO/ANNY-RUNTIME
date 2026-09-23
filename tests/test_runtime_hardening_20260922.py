import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from runtime.execution.capability import CapabilityDefinition, ExecutorType
from runtime.execution.deterministic_executor import ExecutorSecurityError
from runtime.execution.models import Task, TaskExecutionContext
from runtime.execution.qwen_executor import QwenModelExecutor
from runtime.execution.selector import ExecutorSelection
from runtime.execution.worker import WorkerManager
from runtime.execution.registry import ModelRegistry
from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.mcp.tools import ToolImplementationError, filesystem_inspect
from runtime.sync.models import SyncState
from runtime.sync.service import SyncService
from runtime.updater.manager import UpdateManager, UpdateNotImplementedError, UpdateState


def test_filesystem_boundary_rejects_sibling_prefix_and_missing_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sibling = tmp_path / "workspace-escape"
    sibling.mkdir()
    escaped = sibling / "secret.txt"
    escaped.write_text("secret")

    with pytest.raises(ToolImplementationError, match="outside workspace"):
        filesystem_inspect({"path": str(escaped)}, {"workspace_path": str(workspace)})
    with pytest.raises(ToolImplementationError, match="Workspace boundary is required"):
        filesystem_inspect({"path": str(escaped)}, {})


def test_filesystem_boundary_rejects_symlink_escape(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (workspace / "escape").symlink_to(outside)

    with pytest.raises(ToolImplementationError, match="outside workspace"):
        filesystem_inspect({"path": str(workspace / "escape")}, {"workspace_path": str(workspace)})


def test_model_registry_rejects_placeholder_artifact_provenance():
    from dataclasses import replace

    registry = ModelRegistry()
    model = registry.get("qwen3-8b")
    assert model is not None
    assert model.status.value == "INSTALL_REQUIRED"
    assert model.artifact_sha256 == ""

    invalid = replace(model, model_id="invalid-qwen", artifact_sha256="dummy_hash_for_now")
    with pytest.raises(ValueError, match="placeholder artifact provenance"):
        registry.register_model(invalid)


def test_qwen_requires_non_placeholder_digest(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"model")
    with pytest.raises(ExecutorSecurityError, match="ARTIFACT_PROVENANCE_UNVERIFIED"):
        QwenModelExecutor(str(artifact))._verify_artifact()
    with pytest.raises(ExecutorSecurityError, match="ARTIFACT_PROVENANCE_UNVERIFIED"):
        QwenModelExecutor(str(artifact), "dummy_hash_for_now")._verify_artifact()
    QwenModelExecutor(str(artifact), hashlib.sha256(b"model").hexdigest())._verify_artifact()


class _Workspace:
    def get_workspace_size(self, path):
        return 0


def test_remote_worker_fails_closed_without_injected_frontier_executor():
    manager = WorkerManager(_Workspace())
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    task = Task("task", "remote", "account", "project", {}, {}, deadline, "keep", "required", "test", datetime.now(timezone.utc))
    context = TaskExecutionContext("exec", "task", "account", "project", "remote", "/tmp", {}, [], deadline, {}, "disabled", "read_only")
    selection = ExecutorSelection(
        executor_type=ExecutorType.REMOTE_MODEL,
        executor_id="frontier", executor_version="1", model_id="model", model_version="1",
        reason="test", policy_version="v1", risk_class="low",
    )
    worker = manager.create_worker(context, selection, task)
    cap = CapabilityDefinition("remote", "remote", "", "1", "low", True, False, "disabled", "none", [], 1, 1, True, ExecutorType.REMOTE_MODEL, None, True)
    manager.start_worker(worker.worker_id, context, task, cap)
    assert context.status.value == "FAILED"
    assert context.failure_reason.value == "AUTHORIZATION_DENIED"
    assert "Authorized FrontierExecutor" in context.error_message


def test_update_manager_is_explicitly_quarantined():
    manager = UpdateManager({}, "v0.4.0")
    with pytest.raises(UpdateNotImplementedError, match="UPDATE_CHECK_NOT_IMPLEMENTED"):
        manager.check()
    assert manager.state is UpdateState.FAILED


def test_verified_sync_never_claims_stage_or_rollback_without_receipt(tmp_path):
    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {"source": "test", "candidate_version": "v0.4.0", "authorized": True},
    )
    service.start()
    service.wait()
    assert service.status()["sync_state"] == SyncState.VERIFIED.value
    assert service.stage()["error"] == "STAGING_NOT_IMPLEMENTED"
    assert service.rollback()["error"] == "ROLLBACK_NOT_IMPLEMENTED"


def test_deterministic_executor_rejects_cross_workspace_path(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sibling = tmp_path / "workspace-other"
    sibling.mkdir()
    target = sibling / "outside.txt"
    target.write_text("no")
    context = TaskExecutionContext(
        "exec", "task", "account", "project", "filesystem.inspect", str(workspace), {}, [],
        datetime.now(timezone.utc) + timedelta(minutes=1), {}, "disabled", "read_only",
    )
    task = Task("task", "filesystem.inspect", "account", "project", {"path": str(target)}, {}, context.deadline, "keep", "required", "test", datetime.now(timezone.utc))
    DeterministicExecutor(_Workspace()).execute(task, context)
    assert context.status.value == "FAILED"
    assert context.failure_reason.value == "AUTHORIZATION_DENIED"


def test_local_model_invalid_result_cannot_be_promoted_to_success():
    from types import SimpleNamespace
    from unittest.mock import patch
    manager = WorkerManager(_Workspace())
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    task = Task("task", "document.classify", "account", "project", {}, {}, deadline, "keep", "required", "test", datetime.now(timezone.utc))
    context = TaskExecutionContext("exec", "task", "account", "project", "document.classify", "/tmp", {}, [], deadline, {}, "disabled", "read_only")
    selection = ExecutorSelection(
        executor_type=ExecutorType.LOCAL_MODEL,
        executor_id="qwen", executor_version="1", model_id="qwen3-8b", model_version="1",
        reason="test", policy_version="v1", risk_class="low",
    )
    cap = CapabilityDefinition("document.classify", "document.classify", "", "1", "low", True, False, "disabled", "read_only", [], 1, 1, True, ExecutorType.LOCAL_MODEL, None, True)
    worker = manager.create_worker(context, selection, task)
    fake_result = SimpleNamespace(status="FAILED", result_data={"error": "invalid"}, evidence={"telemetry": {"result_hash": "deadbeef"}})
    with patch.dict("os.environ", {"QWEN_MODEL_PATH": "/tmp/model.gguf"}), patch("os.path.exists", return_value=True), patch("runtime.execution.qwen_executor.QwenModelExecutor.execute", return_value=fake_result):
        manager.start_worker(worker.worker_id, context, task, cap)
    assert context.status.value == "FAILED"
    assert worker.state.value == "FAILED"
    assert "did not succeed" in context.error_message


def test_legacy_execution_paths_are_quarantined():
    from runtime.security.execution_context import ExecutionContext
    from runtime.security.pipeline import AuthorizedExecutionPipeline, SecurityViolationError
    from runtime.security.tool_registry import SecureToolRegistry
    from runtime.execution.executor import ExecutionOrchestrator, ToolInvocation
    now = datetime.now(timezone.utc)
    ctx = ExecutionContext("tenant", "account", "project", "anny", "runtime", "session", "actor", "op", "exec", 1, now, now + timedelta(minutes=1), "workspace", {"x"})
    with pytest.raises(SecurityViolationError, match="LEGACY_AUTH_PIPELINE_QUARANTINED"):
        AuthorizedExecutionPipeline(None, None, SecureToolRegistry()).execute(ctx, "tool", {})
    with pytest.raises(SecurityViolationError, match="LEGACY_TOOL_REGISTRY_QUARANTINED"):
        SecureToolRegistry().execute(ctx, "tool", {})
    orch = ExecutionOrchestrator(None, None, None, None, None, 1)
    with pytest.raises(RuntimeError, match="LEGACY_EXECUTION_ORCHESTRATOR_QUARANTINED"):
        orch.execute(ToolInvocation("tool", {}, "session", "actor", "tenant", "workspace"))


def test_legacy_secret_broker_is_quarantined():
    from runtime.secrets.broker import SecretBroker
    class Backend:
        def retrieve(self, reference):
            return b"secret"
        def store(self, reference, value):
            return True
        def exists(self, reference):
            return True
        def delete(self, reference):
            return True
    broker = SecretBroker(Backend())
    with pytest.raises(PermissionError, match="LEGACY_SECRET_BROKER_QUARANTINED"):
        broker.use("ref", "op", "actor", "tenant")
    with pytest.raises(PermissionError, match="LEGACY_SECRET_BROKER_QUARANTINED"):
        broker.store("ref", b"x")
    with pytest.raises(PermissionError, match="LEGACY_SECRET_BROKER_QUARANTINED"):
        broker.exists("ref")
    with pytest.raises(PermissionError, match="LEGACY_SECRET_BROKER_QUARANTINED"):
        broker.revoke("ref")


def test_release_identity_uses_canonical_runtime_version():
    from runtime.core.version import __version__
    import cli.main as cli_main
    assert cli_main.VERSION == __version__
    helper_text = open("scripts/physical-cert-helper.sh", encoding="utf-8").read()
    assert "v0.2.0-CANDIDATE" not in helper_text
    assert "RUNTIME_VERSION" in helper_text


def test_bridge_requires_real_execution_context():
    from runtime.api.bridge import BridgeRouter, BridgeAuthError
    router = BridgeRouter({"execution_manager": object()})
    with pytest.raises(BridgeAuthError):
        router._get_execution_context()

def test_bridge_rejects_stale_generation():
    from runtime.api.bridge import BridgeRouter, BridgeAuthError
    from runtime.security.execution_context import ExecutionContext
    now = datetime.now(timezone.utc)
    ctx = ExecutionContext(
        "tenant", "account", "project", "anny", "runtime", "session", "actor", "op", "exec",
        1, now, now + timedelta(minutes=1), "workspace", {"repository.read"},
    )
    class Gen:
        current = 2
    class Runtime:
        generation = Gen()
    router = BridgeRouter({"execution_context": ctx, "runtime_engine": Runtime()})
    with pytest.raises(BridgeAuthError):
        router._get_execution_context()

def test_bridge_capability_resolution_uses_canonical_registry():
    from runtime.api.bridge import BridgeRouter
    from runtime.execution.capability import CapabilityDefinition, ExecutorType
    class Registry:
        def __init__(self):
            self.enabled = CapabilityDefinition("enabled", "enabled", "", "1", "low", False, True, "disabled", "read_only", [], 1, 1, True, ExecutorType.DETERMINISTIC, None, True)
            self.disabled = CapabilityDefinition("disabled", "disabled", "", "1", "low", False, True, "disabled", "read_only", [], 1, 1, True, ExecutorType.DETERMINISTIC, None, False)
        def get(self, name):
            return {"enabled": self.enabled, "disabled": self.disabled}.get(name)
    class Manager:
        registry = Registry()
    assert BridgeRouter({})._resolve_capability(Manager(), "enabled").capability_id == "enabled"
    assert BridgeRouter({})._resolve_capability(Manager(), "disabled") is None
    assert BridgeRouter({})._resolve_capability(Manager(), "fabric.register") is None


def test_cli_has_no_identity_fallback_and_no_shell_string_uninstall():
    import inspect
    import cli.main as cli_main
    source = inspect.getsource(cli_main.cmd_identity_bootstrap)
    uninstall_source = inspect.getsource(cli_main.cmd_uninstall)
    assert "Ed25519PrivateKey.generate" not in source
    assert "os.system" not in uninstall_source

def test_cli_server_default_uses_canonical_port():
    import cli.main as cli_main
    assert "default=get_admin_port()" in open("cli/main.py", encoding="utf-8").read()

def test_engine_health_is_not_unconditionally_green():
    from runtime.core.config import RuntimeConfig
    from runtime.core.engine import RuntimeEngine
    engine = RuntimeEngine(RuntimeConfig(data_dir="/tmp/anny-test-health"))
    result = engine.health_check()
    assert result["status"] != "ok"
    assert result["subsystems"]["identity"] != "ok"

def test_admin_controls_report_blocked_or_not_implemented():
    from runtime.admin.routes import AdminRouter
    router = AdminRouter({})
    assert router.handle_admin_restart({}) == "/"
    assert router.handle_admin_diagnostics({}) == "/doctor"


def test_runtime_server_links_canonical_execution_manager_to_engine():
    import inspect
    from runtime.admin.server import start_admin_server
    source = inspect.getsource(start_admin_server)
    assert "engine.execution_manager = execution_manager" in source

def test_fabric_register_is_denied_when_canonical_capability_is_disabled(tmp_path):
    from runtime.mcp import ToolRequest
    from runtime.mcp.gateway import MCPGateway
    from runtime.mcp.registry import ToolRegistry
    from datetime import datetime, timezone, timedelta

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    gateway = MCPGateway(
        tool_registry=ToolRegistry(),
        capability_registry=__import__("runtime.execution.capability", fromlist=["CapabilityRegistry"]).CapabilityRegistry(),
        workspace_path=str(workspace),
    )
    request = ToolRequest.create(
        tool_id="fabric.register",
        capability_id="fabric.register",
        worker_id="worker",
        execution_id="execution",
        input_data={"resource_id": "x", "resource_type": "test"},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    result = gateway.invoke(request)
    assert result.status.value == "DENIED"
    assert "disabled" in result.error_message.lower()


def test_fabric_register_is_disabled_by_default():
    from runtime.execution.capability import CapabilityRegistry
    cap = CapabilityRegistry().get("fabric.register")
    assert cap is not None
    assert cap.enabled is False

def test_worker_propagates_registry_model_digest_to_qwen_executor():
    from unittest.mock import patch
    from types import SimpleNamespace
    manager = WorkerManager(
        _Workspace(),
        model_registry=SimpleNamespace(
            get=lambda model_id: SimpleNamespace(
                artifact_sha256="registry-sha256",
            )
        ),
    )
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    task = Task("task", "document.classify", "account", "project", {}, {}, deadline, "keep", "required", "test", datetime.now(timezone.utc))
    context = TaskExecutionContext("exec", "task", "account", "project", "document.classify", "/tmp", {}, [], deadline, {}, "disabled", "read_only")
    selection = ExecutorSelection(
        executor_type=ExecutorType.LOCAL_MODEL,
        executor_id="qwen", executor_version="1", model_id="qwen3-8b", model_version="1",
        reason="test", policy_version="v1", risk_class="low",
    )
    cap = CapabilityDefinition("document.classify", "document.classify", "", "1", "low", True, False, "disabled", "read_only", [], 1, 1, True, ExecutorType.LOCAL_MODEL, None, True)
    worker = manager.create_worker(context, selection, task)
    captured = {}
    class FakeExecutor:
        def __init__(self, artifact_path, expected_sha256):
            captured["expected_sha256"] = expected_sha256
        def execute(self, _ctx):
            return SimpleNamespace(status="FAILED", result_data={}, evidence={"telemetry": {}})
    with patch.dict("os.environ", {"QWEN_MODEL_PATH": "/tmp/model.gguf"}), patch("os.path.exists", return_value=True), patch("runtime.execution.qwen_executor.QwenModelExecutor", FakeExecutor):
        manager.start_worker(worker.worker_id, context, task, cap)
    assert captured["expected_sha256"] == "registry-sha256"


def test_active_release_checksums_resolve_to_real_commits():
    from pathlib import Path
    import re
    import subprocess
    from runtime.core.version import __version__
    root = Path(__file__).resolve().parents[1]
    for checksum in root.glob("ANNY-RUNTIME-*.tar.gz.sha256"):
        match = re.fullmatch(r"ANNY-RUNTIME-v([0-9]+(?:\\.[0-9]+)*)-([0-9a-f]{7,40})\\.tar\\.gz\\.sha256", checksum.name)
        assert match, f"Invalid active release checksum name: {checksum.name}"
        assert match.group(1) == __version__, f"Checksum version drift: {checksum.name} != v{__version__}"
        sha = subprocess.run(
            ["git", "rev-parse", "--verify", f"{match.group(2)}^{{commit}}"],
            cwd=root, capture_output=True, text=True,
        )
        assert sha.returncode == 0, f"Unresolvable release source identity: {match.group(2)}"
