"""Regression coverage for the bounded L0 audit fixture matrix."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import ExecutionStatus, Task, TaskExecutionContext
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


def _task(capability_id, task_input):
    return Task(
        task_id=f"l0-audit-{capability_id}",
        capability_id=capability_id,
        account_id="l0-audit",
        project_id="l0-audit",
        input=task_input,
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        workspace_policy="retain",
        evidence_policy="required",
        requested_by="l0-audit",
        created_at=datetime.now(timezone.utc),
    )


def _execute(executor, manager, task):
    workspace = manager.create_workspace(f"l0-{task.capability_id}", task.project_id)
    context = TaskExecutionContext(
        execution_id=f"l0-{task.capability_id}",
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
    executor.execute(task, context)
    assert context.status == ExecutionStatus.SUCCEEDED
    return context


def test_l0_deterministic_fixture_matrix_executes_without_a_model(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    document = target / "example.txt"
    document.write_text("L0 fixture text\n", encoding="utf-8")

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    repo_document = repository / "fixture.txt"
    repo_document.write_text("stable value\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "fixture.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "-c", "user.name=L0 Audit", "-c", "user.email=l0@example.invalid", "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )
    repo_document.write_text("changed value\n", encoding="utf-8")

    workspace_manager = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    executor = DeterministicExecutor(workspace_manager)
    cases = [
        ("filesystem.inspect", {"path": str(document)}),
        ("filesystem.list", {"path": str(target)}),
        ("filesystem.hash", {"path": str(document)}),
        ("repository.inspect", {"path": str(repository)}),
        ("repository.search", {"path": str(repository), "pattern": "changed value"}),
        ("repository.read", {"path": str(repository)}),
        ("repository.diff", {"path": str(repository), "base": "HEAD"}),
        ("artifact.metadata", {"path": str(document)}),
    ]

    for capability_id, task_input in cases:
        context = _execute(executor, workspace_manager, _task(capability_id, task_input))
        assert context.result_hash
        assert (Path(context.workspace_path) / "evidence" / "evidence.json").exists()


def test_l0_governed_deterministic_route_never_selects_a_model(tmp_path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("governed L0 fixture", encoding="utf-8")
    manager = ExecutionManager(EphemeralWorkspaceManager(str(tmp_path / "workspaces")))

    context = manager.submit_task(_task("filesystem.hash", {"path": str(artifact)}))

    assert context.executor_type == "DETERMINISTIC"
    assert context.executor_id == "deterministic-v1"
    assert context.model_id is None
    assert context.network_policy == "disabled"
    manager.execute_sync(context.execution_id)
    assert context.status == ExecutionStatus.SUCCEEDED
    assert context.result["algorithm"] == "sha256"
