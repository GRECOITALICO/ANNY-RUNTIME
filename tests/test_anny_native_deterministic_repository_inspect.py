"""Local Runtime integration coverage for the smallest ANNY-native read capability.

This test intentionally exercises the Runtime execution path only.  It is not
evidence of a deployed Runtime, Harness dispatch, ANNY first use, or
certification.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

from runtime.execution.manager import ExecutionManager
from runtime.execution.models import ExecutionStatus, Task
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


def test_repository_inspect_runs_through_runtime_worker_and_emits_local_evidence(tmp_path):
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)

    manager = ExecutionManager(EphemeralWorkspaceManager(str(tmp_path / "workspaces")))
    task = Task(
        task_id="batch022-repository-inspect",
        capability_id="repository.inspect",
        account_id="local-test-account",
        project_id="batch022-local-project",
        input={"path": str(repository)},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        workspace_policy="retain",
        evidence_policy="required",
        requested_by="local-runtime-test",
        created_at=datetime.now(timezone.utc),
    )

    context = manager.submit_task(task)
    manager.execute_sync(context.execution_id)

    assert context.status is ExecutionStatus.SUCCEEDED
    assert context.capability_id == "repository.inspect"
    assert context.result["is_git_repository"] is True
    assert Path(context.workspace_path, "evidence", "evidence.json").is_file()
