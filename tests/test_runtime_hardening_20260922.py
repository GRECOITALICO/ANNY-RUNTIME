import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from runtime.execution.capability import CapabilityDefinition, ExecutorType
from runtime.execution.deterministic_executor import ExecutorSecurityError
from runtime.execution.models import Task, TaskExecutionContext
from runtime.execution.qwen_executor import QwenModelExecutor
from runtime.execution.selector import ExecutorSelection
from runtime.execution.worker import WorkerManager
from runtime.execution.registry import ModelRegistry
from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.orchestration.frontier import FrontierExecutor, FrontierExecutionReceipt
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
    model = registry.get_model("qwen3-8b")
    assert model is not None
    assert model.status.value == "INSTALL_REQUIRED"
    assert model.artifact_sha256 == ""

    invalid = replace(model, model_id="invalid-qwen", artifact_sha256="dummy_hash_for_now")
    with pytest.raises(ValueError, match="placeholder artifact provenance"):
        registry.register_model(invalid)


def test_qwen_requires_non_placeholder_digest(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"model")
    with pytest.raises(ExecutorSecurityError, match="ARTIFACT_SHA256_REQUIRED"):
        QwenModelExecutor(str(artifact))._verify_artifact()
    with pytest.raises(ExecutorSecurityError, match="ARTIFACT_SHA256_PLACEHOLDER_REJECTED"):
        QwenModelExecutor(str(artifact), "dummy_hash_for_now")._verify_artifact()
    QwenModelExecutor(str(artifact), hashlib.sha256(b"model").hexdigest())._verify_artifact()


def test_qwen_rejects_invalid_and_mismatched_artifact_sha(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"model")
    with pytest.raises(ExecutorSecurityError, match="ARTIFACT_SHA256_INVALID"):
        QwenModelExecutor(str(artifact), "not-a-sha")._verify_artifact()
    with pytest.raises(ExecutorSecurityError, match="ARTIFACT_SHA256_MISMATCH"):
        QwenModelExecutor(str(artifact), "0" * 64)._verify_artifact()


class _Workspace:
    def get_workspace_size(self, path):
        return 0


def _admit_worker_for_internal_test(manager, context, task, capability, selection):
    """Explicit test-only admission for isolated WorkerManager contract tests."""
    from runtime.execution.capability import CapabilityRegistry
    registry = CapabilityRegistry()
    registry.register(capability)
    manager.capability_registry = registry
    manager._admit_execution(context, task, capability, selection)


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
    _admit_worker_for_internal_test(manager, context, task, cap, selection)
    manager.start_worker(worker.worker_id, context, task, cap)
    assert context.status.value == "FAILED"
    assert context.failure_reason.value == "AUTHORIZATION_DENIED"
    assert "Authorized FrontierExecutor" in context.error_message


def _remote_worker_fixture(frontier_executor):
    manager = WorkerManager(_Workspace(), frontier_executor=frontier_executor)
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    task = Task("task", "remote", "account", "project", {"input": "x"}, {}, deadline, "keep", "required", "test", datetime.now(timezone.utc))
    context = TaskExecutionContext("exec", "task", "account", "project", "remote", "/tmp", {}, [], deadline, {}, "disabled", "read_only")
    selection = ExecutorSelection(
        executor_type=ExecutorType.REMOTE_MODEL,
        executor_id="physical-frontier", executor_version="1", model_id="model", model_version="1",
        reason="test", policy_version="v1", risk_class="low",
    )
    worker = manager.create_worker(context, selection, task)
    cap = CapabilityDefinition("remote", "remote", "", "1", "low", True, False, "disabled", "none", [], 1, 1, True, ExecutorType.REMOTE_MODEL, None, True)
    _admit_worker_for_internal_test(manager, context, task, cap, selection)
    return manager, worker, context, task, cap


class _ReceiptFrontier(FrontierExecutor):
    def identity(self):
        return "physical-frontier"

    def is_authorized(self):
        return True

    def is_available(self, model_id=None):
        return model_id == "model"

    def execute_plan(self, task, plan):
        result_data = {"classification": "internal"}
        return FrontierExecutionReceipt(
            execution_id="exec",
            task_id=task.task_id,
            executor_id=self.identity(),
            model_id=plan.model_id,
            result_data=result_data,
            result_hash=hashlib.sha256(__import__("json").dumps(result_data, sort_keys=True).encode()).hexdigest(),
            evidence_ref="evidence://nonprod/physical-frontier/exec",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


def test_remote_worker_requires_correlated_receipt_for_success():
    manager, worker, context, task, cap = _remote_worker_fixture(_ReceiptFrontier())
    manager.start_worker(worker.worker_id, context, task, cap)
    assert context.status.value == "SUCCEEDED"
    assert context.result_hash
    assert context.evidence_ref == "evidence://nonprod/physical-frontier/exec"
    assert worker.state.value == "SUCCEEDED"


def test_remote_worker_rejects_raw_synthetic_result():
    class RawResultFrontier(_ReceiptFrontier):
        def execute_plan(self, task, plan):
            return {"status": "COMPLETED", "result": "synthetic"}

    manager, worker, context, task, cap = _remote_worker_fixture(RawResultFrontier())
    manager.start_worker(worker.worker_id, context, task, cap)
    assert context.status.value == "FAILED"
    assert context.failure_reason.value == "AUTHORIZATION_DENIED"
    assert "FrontierExecutionReceipt" in context.error_message


def test_remote_worker_rejects_mismatched_receipt_provenance():
    class MismatchedReceiptFrontier(_ReceiptFrontier):
        def execute_plan(self, task, plan):
            receipt = super().execute_plan(task, plan)
            return FrontierExecutionReceipt(
                execution_id=receipt.execution_id,
                task_id=receipt.task_id,
                executor_id=receipt.executor_id,
                model_id=receipt.model_id,
                result_data=receipt.result_data,
                result_hash="0" * 64,
                evidence_ref=receipt.evidence_ref,
                completed_at=receipt.completed_at,
            )

    manager, worker, context, task, cap = _remote_worker_fixture(MismatchedReceiptFrontier())
    manager.start_worker(worker.worker_id, context, task, cap)
    assert context.status.value == "FAILED"
    assert "result hash mismatch" in context.error_message


def test_update_manager_is_explicitly_quarantined():
    manager = UpdateManager({}, "v0.4.0")
    with pytest.raises(UpdateNotImplementedError, match="UPDATE_CHECK_NOT_IMPLEMENTED"):
        manager.check()
    assert manager.state is UpdateState.NOT_IMPLEMENTED


def test_verified_sync_never_claims_stage_or_rollback_without_receipt(tmp_path):
    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {"source": "test", "candidate_version": "v0.4.0", "authorized": True},
    )
    service.start()
    service.wait()
    assert service.status()["sync_state"] == SyncState.VERIFIED.value
    assert service.stage()["error"] == "STAGING_REQUIRES_VERIFIED_ARTIFACT"
    assert service.rollback()["error"] == "ROLLBACK_REQUIRES_PHYSICAL_APPLY"


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
    manager = WorkerManager(
        _Workspace(),
        model_registry=SimpleNamespace(
            get=lambda _model_id: SimpleNamespace(artifact_sha256="e" * 64)
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
    _admit_worker_for_internal_test(manager, context, task, cap, selection)
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
    assert "grep '__version__'" not in open("scripts/build_release.sh", encoding="utf-8").read()
    assert "grep '__version__'" not in open("scripts/install.sh", encoding="utf-8").read()


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
    assert "remove_path(DATA_DIR, expected_data_dir, recursive=True)" in uninstall_source
    assert "outside the managed Runtime scope" in uninstall_source

def test_cli_server_default_uses_canonical_port():
    import cli.main as cli_main
    source = open("cli/main.py", encoding="utf-8").read()
    assert "RuntimeConfig.load()" in source
    assert "config.admin_port" in source
    assert "default=None" in source
    assert "RUNTIME_HEALTH=UNVERIFIED" in source

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
        execution_authorizer=lambda _request: (True, "TEST_ONLY"),
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
    from types import SimpleNamespace
    manager = WorkerManager(
        _Workspace(),
        model_registry=SimpleNamespace(
            get=lambda model_id: SimpleNamespace(
                artifact_sha256="c" * 64,
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
    _admit_worker_for_internal_test(manager, context, task, cap, selection)
    captured = {}
    class FakeExecutor:
        def __init__(self, artifact_path, expected_sha256):
            captured["expected_sha256"] = expected_sha256
        def execute(self, _ctx):
            return SimpleNamespace(status="FAILED", result_data={}, evidence={"telemetry": {}})
    with patch.dict("os.environ", {"QWEN_MODEL_PATH": "/tmp/model.gguf"}), patch("os.path.exists", return_value=True), patch("runtime.execution.qwen_executor.QwenModelExecutor", FakeExecutor):
        manager.start_worker(worker.worker_id, context, task, cap)
    assert captured["expected_sha256"] == "c" * 64


def test_worker_rejects_missing_or_invalid_registry_model_digest():
    from types import SimpleNamespace
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    task = Task("task", "document.classify", "account", "project", {}, {}, deadline, "keep", "required", "test", datetime.now(timezone.utc))
    cap = CapabilityDefinition("document.classify", "document.classify", "", "1", "low", True, False, "disabled", "read_only", [], 1, 1, True, ExecutorType.LOCAL_MODEL, None, True)
    selection = ExecutorSelection(
        executor_type=ExecutorType.LOCAL_MODEL,
        executor_id="qwen", executor_version="1", model_id="qwen3-8b", model_version="1",
        reason="test", policy_version="v1", risk_class="low",
    )
    for digest, expected in [(None, "required"), ("placeholder", "invalid")]:
        manager = WorkerManager(
            _Workspace(),
            model_registry=SimpleNamespace(get=lambda model_id, d=digest: SimpleNamespace(artifact_sha256=d)),
        )
        context = TaskExecutionContext("exec", "task", "account", "project", "document.classify", "/tmp", {}, [], deadline, {}, "disabled", "read_only")
        worker = manager.create_worker(context, selection, task)
        _admit_worker_for_internal_test(manager, context, task, cap, selection)
        with patch.dict("os.environ", {"QWEN_MODEL_PATH": "/tmp/model.gguf"}), patch("os.path.exists", return_value=True):
            manager.start_worker(worker.worker_id, context, task, cap)
        assert context.status.value == "FAILED"
        assert context.failure_reason.value == "AUTHORIZATION_DENIED"
        assert expected in context.error_message.lower()


def test_worker_rejects_synthetic_local_success_without_provenance():
    from unittest.mock import patch
    from types import SimpleNamespace
    digest = "d" * 64
    manager = WorkerManager(_Workspace(), model_registry=SimpleNamespace(get=lambda _: SimpleNamespace(artifact_sha256=digest)))
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    task = Task("task", "document.classify", "account", "project", {}, {}, deadline, "keep", "required", "test", datetime.now(timezone.utc))
    context = TaskExecutionContext("exec", "task", "account", "project", "document.classify", "/tmp", {}, [], deadline, {}, "disabled", "read_only")
    selection = ExecutorSelection(ExecutorType.LOCAL_MODEL, "qwen", "1", "qwen3-8b", "1", "test", "v1", "low")
    cap = CapabilityDefinition("document.classify", "document.classify", "", "1", "low", True, False, "disabled", "read_only", [], 1, 1, True, ExecutorType.LOCAL_MODEL, None, True)
    worker = manager.create_worker(context, selection, task)
    _admit_worker_for_internal_test(manager, context, task, cap, selection)
    class SyntheticSuccess:
        def __init__(self, **kwargs):
            pass
        def execute(self, _ctx):
            return SimpleNamespace(status="SUCCEEDED", result_data={"class": "internal"}, evidence={"telemetry": {"result_hash": "0" * 64}})
    with patch.dict("os.environ", {"QWEN_MODEL_PATH": "/tmp/model.gguf"}), patch("os.path.exists", return_value=True), patch("runtime.execution.qwen_executor.QwenModelExecutor", SyntheticSuccess):
        manager.start_worker(worker.worker_id, context, task, cap)
    assert context.status.value == "FAILED"
    assert context.failure_reason.value == "AUTHORIZATION_DENIED"
    assert "provenance" in context.error_message.lower()


def test_distributable_runtime_has_no_host_specific_home_paths():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    production_roots = [root / "runtime", root / "cli"]
    violations = []
    for base in production_roots:
        for source in base.rglob("*.py"):
            text = source.read_text(encoding="utf-8", errors="replace")
            if "/home/anny" in text or ".gemini/antigravity" in text:
                violations.append(str(source.relative_to(root)))
    assert violations == []


def test_browser_binary_resolution_is_environment_portable(monkeypatch):
    from runtime.browser import broker_server

    monkeypatch.setenv("ANNY_CHROME_BINARY", "/tmp/fake-chrome")
    original_isfile = broker_server.os.path.isfile
    monkeypatch.setattr(broker_server.os.path, "isfile", lambda p: p == "/tmp/fake-chrome" or original_isfile(p))
    monkeypatch.setattr(broker_server.os, "access", lambda p, mode: p == "/tmp/fake-chrome" or original_isfile(p))
    assert broker_server._resolve_chrome_binary() == "/tmp/fake-chrome"


def test_evidence_builder_default_is_not_host_specific():
    import os
    import inspect
    from runtime.intelligence.evidence_builder import EvidenceBuilder

    old = os.environ.pop("ANNY_EVIDENCE_DIR", None)
    try:
        builder = EvidenceBuilder()
        # The checkout itself may live below a user's home directory.  Assert
        # portability of the implementation, not the incidental cwd.
        source = inspect.getsource(EvidenceBuilder.__init__)
        assert '"/home/anny' not in source
        assert "ANNY_EVIDENCE_DIR" in source
        assert builder.output_dir
    finally:
        if old is not None:
            os.environ["ANNY_EVIDENCE_DIR"] = old


def test_local_release_sidecars_have_resolvable_source_identity_and_matching_payload():
    from pathlib import Path
    import re
    import subprocess
    from runtime.core.version import __version__
    root = Path(__file__).resolve().parents[1]
    for checksum in root.glob("ANNY-RUNTIME-*.tar.gz.sha256"):
        match = re.fullmatch(r"ANNY-RUNTIME-v([0-9]+(?:\.[0-9]+)*)-([0-9a-f]{7,40})\.tar\.gz\.sha256", checksum.name)
        assert match, f"Invalid active release checksum name: {checksum.name}"
        assert match.group(1) == __version__, f"Checksum version drift: {checksum.name} != v{__version__}"
        sha = subprocess.run(
            ["git", "rev-parse", "--verify", f"{match.group(2)}^{{commit}}"],
            cwd=root, capture_output=True, text=True,
        )
        assert sha.returncode == 0, f"Unresolvable release source identity: {match.group(2)}"
        verify = subprocess.run(
            ["sha256sum", "--check", checksum.name],
            cwd=root, capture_output=True, text=True,
        )
        assert verify.returncode == 0, verify.stdout + verify.stderr

def test_control_center_renders_authoritative_conrrad_live_truth_matrix():
    from runtime.admin.templates_cc import control_center_page

    html = control_center_page("TEST_ONLY_CSRF")
    assert "CONRRAD Mandatory Services" in html
    assert "CONRRAD Mandatory Services — Live Truth" in html
    assert 'id="conrrad-deps-tbody"' in html
    assert "ONLINE_VERIFIED" in html
    assert "CERTIFIED_BY_LIVE_EVIDENCE" in html
    assert "ONLINE_UNVERIFIED" in html
    assert "UNKNOWN" in html


def test_control_center_status_api_exposes_strict_conrrad_gate():
    from runtime.admin.routes import AdminRouter

    class Engine:
        state = type("State", (), {"name": "ADMIN_MODE"})()
        config = type("Config", (), {})()
        bootstrap_report = None

    router = AdminRouter({"runtime_engine": Engine()})
    router.handle_api_status(type("Parsed", (), {"query": ""})())
    data = router.context["direct_json_response"]

    assert data["conrrad_gate_status"] == "BLOCKED"
    assert data["conrrad_required_service_count"] == 8
    assert data["conrrad_observed_service_count"] == 8
    assert data["conrrad_online_verified_count"] == 0
    assert data["conrrad_trust_verified_count"] == 0
    assert len(data["conrrad_dependencies"]) == 8
