import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from runtime.execution.capability import CapabilityDefinition, ExecutorType
from runtime.execution.deterministic_executor import ExecutorSecurityError
from runtime.execution.models import Task, TaskExecutionContext
from runtime.execution.qwen_executor import QwenModelExecutor
from runtime.execution.selector import ExecutorSelection
from runtime.execution.worker import WorkerManager
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
