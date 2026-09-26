"""Governed development-tool execution for ANNY Runtime.

Provides deterministic wrappers around the verification commands most commonly
used by engineering agents. The wrappers reuse ShellExecutor and therefore
inherit ExecutionContext, workspace, process and fail-closed policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from runtime.security.execution_context import ExecutionContext
from runtime.shell.executor import ShellExecutor


@dataclass(frozen=True)
class ToolchainResult:
    tool: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    process_id: Optional[str]

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


class DevelopmentToolRunner:
    """Run bounded, explicit verification tools through the governed shell."""

    COMMANDS: Dict[str, str] = {
        "test": "pytest",
        "lint": "ruff check .",
        "format_check": "ruff format --check .",
        "type_check": "mypy .",
        "compile": "python3 -m compileall -q .",
    }

    def __init__(self, shell_executor: ShellExecutor) -> None:
        self.shell_executor = shell_executor

    def run(
        self,
        context: ExecutionContext,
        tool: str,
        *,
        extra_args: str = "",
        timeout: int = 900,
    ) -> ToolchainResult:
        if tool not in self.COMMANDS:
            raise ValueError(f"Unsupported development tool: {tool}")
        command = self.COMMANDS[tool]
        if extra_args:
            command = f"{command} {extra_args}".strip()
        result = self.shell_executor.execute(context, command, timeout=timeout)
        return ToolchainResult(
            tool=tool,
            command=command,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
            process_id=result.process_id,
        )

    def test(self, context: ExecutionContext, *, args: str = "", timeout: int = 900) -> ToolchainResult:
        return self.run(context, "test", extra_args=args, timeout=timeout)

    def lint(self, context: ExecutionContext, *, args: str = "", timeout: int = 900) -> ToolchainResult:
        return self.run(context, "lint", extra_args=args, timeout=timeout)

    def format_check(self, context: ExecutionContext, *, args: str = "", timeout: int = 900) -> ToolchainResult:
        return self.run(context, "format_check", extra_args=args, timeout=timeout)

    def type_check(self, context: ExecutionContext, *, args: str = "", timeout: int = 900) -> ToolchainResult:
        return self.run(context, "type_check", extra_args=args, timeout=timeout)

    def compile(self, context: ExecutionContext, *, args: str = "", timeout: int = 900) -> ToolchainResult:
        return self.run(context, "compile", extra_args=args, timeout=timeout)
