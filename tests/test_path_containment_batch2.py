"""Batch 2 negative matrix for real-path workspace/resource containment."""
from datetime import datetime, timedelta, timezone

import pytest

from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.execution.models import ExecutionStatus, Task, TaskExecutionContext
from runtime.mcp.tools import ToolImplementationError, filesystem_inspect
from runtime.security.path_containment import (
    ContainmentError,
    ContainmentResult,
    require_contained_path,
)


def _task(path, **extra):
    return Task(
        task_id="containment-task",
        capability_id="filesystem.inspect",
        account_id="account-a",
        project_id="project-a",
        input={"path": path, **extra},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        workspace_policy="workspace_only",
        evidence_policy="required",
        requested_by="test",
        created_at=datetime.now(timezone.utc),
    )


class _Workspace:
    def get_workspace_size(self, _path):
        return 0


def _context(root, **extra):
    values = dict(
        execution_id="exec-a",
        task_id="containment-task",
        account_id="account-a",
        project_id="project-a",
        capability_id="filesystem.inspect",
        workspace_path=str(root),
        environment={},
        allowed_tools=["filesystem.inspect"],
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        resource_limits={},
        network_policy="disabled",
        write_policy="workspace_only",
        authorized_resource_id="workspace:exec-a",
        authorized_resource_project_id="project-a",
        authorized_resource_root=str(root),
    )
    values.update(extra)
    return TaskExecutionContext(**values)


def test_real_path_allows_root_relative_normalized_and_missing_target(tmp_path, monkeypatch):
    root = tmp_path / "project"
    nested = root / "allowed" / "nested"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("ok")
    monkeypatch.chdir(tmp_path)

    assert require_contained_path(str(root), ".").result == ContainmentResult.AUTHORIZED
    assert require_contained_path(str(root), "allowed/../allowed/nested/file.txt").resolved_path == str(nested / "file.txt")
    # The maximum existing physical ancestor is resolved; a missing target is
    # not automatically outside or automatically trusted.
    assert require_contained_path(str(root), "allowed/new/deep/file.txt").resolved_path == str(root / "allowed" / "new" / "deep" / "file.txt")


@pytest.mark.parametrize("requested", ["../outside/secret", "../../outside/secret"])
def test_real_path_blocks_traversal(tmp_path, requested):
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(ContainmentError) as error:
        require_contained_path(str(root), requested)
    assert error.value.result == ContainmentResult.OUTSIDE_AUTHORIZED_ROOT


def test_real_path_blocks_sibling_prefix_and_absolute_outside(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    sibling = tmp_path / "project-evil"
    sibling.mkdir()
    for requested in (str(sibling / "secret"),):
        with pytest.raises(ContainmentError) as error:
            require_contained_path(str(root), requested)
        assert error.value.result == ContainmentResult.OUTSIDE_AUTHORIZED_ROOT


@pytest.mark.parametrize("kind", ["direct", "intermediate", "chained", "sibling"])
def test_real_path_blocks_symlink_escapes(tmp_path, kind):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("secret")
    if kind == "direct":
        (root / "link").symlink_to(outside)
        requested = "link/secret"
    elif kind == "intermediate":
        (root / "allowed").mkdir()
        (root / "allowed" / "link").symlink_to(outside)
        requested = "allowed/link/secret"
    elif kind == "chained":
        relay = tmp_path / "relay"
        relay.symlink_to(outside)
        (root / "link").symlink_to(relay)
        requested = "link/secret"
    else:
        sibling = tmp_path / "project-sibling"
        sibling.mkdir()
        (sibling / "secret").write_text("secret")
        (root / "link").symlink_to(sibling)
        requested = "link/secret"
    with pytest.raises(ContainmentError) as error:
        require_contained_path(str(root), requested)
    assert error.value.result == ContainmentResult.SYMLINK_ESCAPE


def test_real_path_fails_closed_for_missing_workspace_and_mcp_unset(tmp_path):
    with pytest.raises(ContainmentError) as error:
        require_contained_path(str(tmp_path / "missing"), "file")
    assert error.value.result == ContainmentResult.MISSING_WORKSPACE
    with pytest.raises(ToolImplementationError, match="Workspace boundary is required"):
        filesystem_inspect({"path": "file"}, {})


@pytest.mark.parametrize(
    ("task_extra", "context_extra", "expected"),
    [
        ({"resource_id": "repository:other"}, {}, "DENIED"),
        ({"project_id": "project-b"}, {}, "CROSS_PROJECT"),
        ({"tenant_id": "tenant-b"}, {"tenant_id": "tenant-a", "authorized_resource_tenant_id": "tenant-a"}, "CROSS_TENANT"),
        ({"operation": "WRITE"}, {}, "UNAUTHORIZED_WRITE"),
    ],
)
def test_deterministic_executor_enforces_resource_identity_scope(tmp_path, task_extra, context_extra, expected):
    root = tmp_path / "project-a"
    root.mkdir()
    (root / "file").write_text("ok")
    context = _context(root, **context_extra)
    DeterministicExecutor(_Workspace()).execute(_task("file", **task_extra), context)
    assert context.status == ExecutionStatus.FAILED
    assert expected in context.error_message


def test_deterministic_executor_allows_only_authorized_ephemeral_resource(tmp_path):
    root = tmp_path / "project-a"
    root.mkdir()
    (root / "file").write_text("ok")
    context = _context(root)
    DeterministicExecutor(_Workspace()).execute(_task("file", resource_id="workspace:exec-a"), context)
    assert context.status == ExecutionStatus.SUCCEEDED


def test_deterministic_executor_allows_explicit_authorized_repository_resource(tmp_path):
    root = tmp_path / "repository-a"
    root.mkdir()
    (root / "README.md").write_text("ok")
    context = _context(
        root,
        authorized_resource_id="repository:project-a",
        resource_kind="AUTHORIZED_REPOSITORY_RESOURCE",
    )
    DeterministicExecutor(_Workspace()).execute(
        _task("README.md", resource_id="repository:project-a"), context
    )
    assert context.status == ExecutionStatus.SUCCEEDED


def test_deterministic_executor_blocks_cross_project_symlink_and_missing_resource(tmp_path):
    root = tmp_path / "project-a"
    root.mkdir()
    project_b = tmp_path / "project-b"
    project_b.mkdir()
    (project_b / "secret").write_text("secret")
    (root / "project-b").symlink_to(project_b)

    linked = _context(root)
    DeterministicExecutor(_Workspace()).execute(_task("project-b/secret"), linked)
    assert linked.status == ExecutionStatus.FAILED
    assert "SYMLINK_ESCAPE" in linked.error_message

    missing = _context(root, authorized_resource_root="")
    DeterministicExecutor(_Workspace()).execute(_task("file"), missing)
    assert missing.status == ExecutionStatus.FAILED
    assert "MISSING_RESOURCE" in missing.error_message
