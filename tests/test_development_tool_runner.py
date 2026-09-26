from datetime import datetime, timedelta, timezone

import pytest

from runtime.security.execution_context import ExecutionContext
from runtime.shell.executor import ShellEffectClass
from runtime.toolchain.runner import DevelopmentToolRunner


class FakeShell:
    def __init__(self, exit_code=0):
        self.calls = []
        self.exit_code = exit_code

    def execute(self, context, command, timeout=300, env=None):
        self.calls.append((context, command, timeout))
        return type(
            "Result",
            (),
            {
                "exit_code": self.exit_code,
                "stdout": "ok",
                "stderr": "",
                "duration_ms": 3,
                "effect_class": ShellEffectClass.WORKSPACE_MUTATING,
                "process_id": "process-1",
            },
        )()


def context():
    now = datetime.now(timezone.utc)
    return ExecutionContext(
        tenant_id="t",
        account_id="a",
        project_id="p",
        anny_instance_id="anny",
        runtime_id="runtime",
        session_id="session",
        actor_id="ANNY",
        operation_id="op",
        execution_id="exec",
        generation=1,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=5),
        workspace_id="ws",
        capabilities={"PROCESS_EXECUTION", "FILE_WRITE"},
    )


def test_supported_tool_names_are_explicit():
    assert set(DevelopmentToolRunner.COMMANDS) == {
        "test", "lint", "format_check", "type_check", "compile"
    }


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("test", "pytest"),
        ("lint", "ruff check ."),
        ("format_check", "ruff format --check ."),
        ("type_check", "mypy ."),
        ("compile", "python3 -m compileall -q ."),
    ],
)
def test_runner_uses_one_governed_shell_path(method, expected):
    shell = FakeShell()
    runner = DevelopmentToolRunner(shell)

    result = getattr(runner, method)(context())

    assert result.succeeded
    assert shell.calls[0][1] == expected
