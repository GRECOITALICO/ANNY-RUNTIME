from datetime import datetime, timedelta, timezone

import pytest

from runtime.security.execution_context import ExecutionContext
from runtime.shell.executor import (
    ShellEffectClass,
    ShellExecutor,
    classify_command,
)


def make_context(capabilities):
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


def test_git_read_classification_is_distinct():
    assert classify_command("git status --porcelain") is ShellEffectClass.READONLY


def test_git_write_classification_is_distinct():
    assert classify_command("git commit -m message") is ShellEffectClass.WORKSPACE_MUTATING


def test_git_remote_mutation_is_distinct():
    assert classify_command("git push origin main") is ShellEffectClass.REMOTE_MUTATION


def test_unknown_command_fails_closed():
    assert classify_command("curl https://example.invalid") is ShellEffectClass.UNKNOWN


def test_shell_requires_canonical_execution_context():
    executor = ShellExecutor(process_manager=type("P", (), {"generation": 1})(), workspace_manager=None)
    with pytest.raises(TypeError):
        executor.execute(object(), "ls")


def test_remote_mutation_requires_network_and_remote_mutation_capabilities():
    required = ShellExecutor._required_capabilities(
        "git push origin main",
        ShellEffectClass.REMOTE_MUTATION,
    )
    assert "REMOTE_REPOSITORY_MUTATION" in required
    assert "NETWORK_ACCESS" in required
    assert "PROCESS_EXECUTION" in required
