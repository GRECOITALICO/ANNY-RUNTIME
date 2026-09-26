from datetime import datetime, timedelta, timezone
import json

import pytest

from runtime.github.engineering import (
    GitHubEngineeringAuthorizationError,
    GitHubEngineeringClient,
)
from runtime.security.execution_context import ExecutionContext


def context(*capabilities):
    now = datetime.now(timezone.utc)
    return ExecutionContext(
        tenant_id="tenant",
        account_id="account",
        project_id="project",
        anny_instance_id="anny",
        runtime_id="runtime",
        session_id="session",
        actor_id="ANNY",
        operation_id="operation",
        execution_id="execution",
        generation=1,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=5),
        workspace_id="workspace",
        capabilities=set(capabilities),
    )


class FakeGitHub:
    timeout_seconds = 5

    def _get_token(self):
        return "test-token"


def test_read_requires_explicit_github_read_capability():
    client = GitHubEngineeringClient(FakeGitHub())
    with pytest.raises(GitHubEngineeringAuthorizationError):
        client._authorize(context(), "GITHUB_READ")


def test_pull_request_write_requires_dedicated_capability():
    client = GitHubEngineeringClient(FakeGitHub())
    with pytest.raises(GitHubEngineeringAuthorizationError):
        client._authorize(context("GITHUB_WRITE"), "GITHUB_PR_WRITE")


def test_actions_dispatch_has_dedicated_capability():
    client = GitHubEngineeringClient(FakeGitHub())
    with pytest.raises(GitHubEngineeringAuthorizationError):
        client._authorize(context("GITHUB_WRITE"), "GITHUB_ACTIONS_DISPATCH")


def test_write_content_requires_github_write():
    client = GitHubEngineeringClient(FakeGitHub())
    with pytest.raises(GitHubEngineeringAuthorizationError):
        client.write_content(
            context("GITHUB_READ"),
            "OWNER",
            "repo",
            "file.txt",
            "hello",
            message="test",
            branch="feature/test",
        )


def test_workflow_dispatch_limits_inputs():
    client = GitHubEngineeringClient(FakeGitHub())
    with pytest.raises(ValueError, match="25"):
        client.dispatch_workflow(
            context("GITHUB_ACTIONS_DISPATCH"),
            "OWNER",
            "repo",
            "ci.yml",
            ref="feature/test",
            inputs={str(i): str(i) for i in range(26)},
        )


def test_create_ref_rejects_non_branch_ref():
    client = GitHubEngineeringClient(FakeGitHub())
    with pytest.raises(ValueError, match="refs/heads"):
        client.create_ref(
            context("GITHUB_WRITE"),
            "OWNER",
            "repo",
            "refs/tags/v1",
            "a" * 40,
        )
