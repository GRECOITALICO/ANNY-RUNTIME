import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.execution.capability import CapabilityRegistry
from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


def _task(capability_id, task_input, project_id="deterministic-test"):
    return Task(
        task_id=f"task-{capability_id}",
        capability_id=capability_id,
        account_id="account-test",
        project_id=project_id,
        input=task_input,
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        workspace_policy="retain",
        evidence_policy="required",
        requested_by="test",
        created_at=datetime.now(timezone.utc),
    )


def _execute(tmp_path, task):
    manager = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    execution_id = "execution-test"
    workspace = manager.create_workspace(execution_id, task.project_id)
    context = TaskExecutionContext(
        execution_id=execution_id,
        task_id=task.task_id,
        account_id=task.account_id,
        project_id=task.project_id,
        capability_id=task.capability_id,
        workspace_path=workspace,
        environment={},
        allowed_tools=[task.capability_id],
        deadline=task.deadline,
        resource_limits={"max_output_size": 1024 * 1024, "max_workspace_size": 10 * 1024 * 1024},
        network_policy="disabled",
        write_policy="workspace_only",
    )
    DeterministicExecutor(manager).execute(task, context)
    return context, Path(workspace)


def test_registry_marks_local_families_and_blocks_fabric_write():
    registry = CapabilityRegistry()
    fs = registry.get("filesystem.inspect")
    fabric_register = registry.get("fabric.register")
    assert fs.family == "filesystem"
    assert fs.hermetic is True
    assert fabric_register.enabled is False
    assert fabric_register.side_effect == "write"


def test_filesystem_list_is_deterministic_and_sorted(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "b.txt").write_text("b", encoding="utf-8")
    (target / "a.txt").write_text("a", encoding="utf-8")
    task = _task("filesystem.list", {"path": str(target)})
    context, workspace = _execute(tmp_path / "runtime", task)
    assert context.status == ExecutionStatus.SUCCEEDED
    assert [item["name"] for item in context.result["entries"]] == ["a.txt", "b.txt"]
    assert (workspace / "evidence" / "evidence.json").exists()


def test_repository_read_and_diff(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    import subprocess
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    (repo / "file.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"], check=True, capture_output=True)
    (repo / "file.txt").write_text("two\n", encoding="utf-8")

    read_task = _task("repository.read", {"path": str(repo)})
    read_context, _ = _execute(tmp_path / "runtime-read", read_task)
    assert read_context.status == ExecutionStatus.SUCCEEDED
    assert read_context.result["dirty"] is True

    diff_task = _task("repository.diff", {"path": str(repo), "base": "HEAD"})
    diff_context, _ = _execute(tmp_path / "runtime-diff", diff_task)
    assert diff_context.status == ExecutionStatus.SUCCEEDED
    assert "file.txt" in diff_context.result["diff"]


def test_artifact_metadata_contains_sha256(tmp_path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"deterministic")
    task = _task("artifact.metadata", {"path": str(artifact)})
    context, workspace = _execute(tmp_path / "runtime-artifact", task)
    assert context.status == ExecutionStatus.SUCCEEDED
    assert len(context.result["sha256"]) == 64
    evidence = json.loads((workspace / "evidence" / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["reproducibility"]["task_id"] == task.task_id
    assert len(evidence["reproducibility"]["input_hash"]) == 64
