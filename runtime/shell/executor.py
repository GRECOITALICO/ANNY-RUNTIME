"""Governed shell execution for ANNY Runtime.

All commands execute inside a Runtime-owned workspace through ProcessManager.
Unknown effects fail closed.
"""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from runtime.security.execution_context import ExecutionContext


@dataclass(frozen=True)
class ShellResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    effect_class: str
    process_id: Optional[str] = None


class ShellEffectClass:
    READONLY = "READONLY"
    WORKSPACE_MUTATING = "WORKSPACE_MUTATING"
    PROCESS_CONTROL = "PROCESS_CONTROL"
    REMOTE_MUTATION = "REMOTE_MUTATION"
    UNKNOWN = "UNKNOWN"


def classify_command(command: str) -> str:
    """Conservative classification of the first command segment."""
    tokens = shlex.split(command, posix=True)
    if not tokens:
        return ShellEffectClass.UNKNOWN

    base = tokens[0]
    if base in {"ls", "cat", "grep", "rg", "find", "head", "tail", "wc", "diff", "pwd", "which", "python", "python3", "pytest", "ruff", "mypy", "git"}:
        if base == "git" and len(tokens) > 1:
            sub = tokens[1]
            if sub in {"status", "log", "diff", "show", "rev-parse", "branch", "ls-files", "cat-file"}:
                return ShellEffectClass.READONLY
            if sub in {"add", "commit", "checkout", "switch", "reset", "restore", "merge", "rebase", "tag"}:
                return ShellEffectClass.WORKSPACE_MUTATING
            if sub in {"push", "fetch", "pull", "remote", "clone"}:
                return ShellEffectClass.REMOTE_MUTATION
            return ShellEffectClass.UNKNOWN
        return ShellEffectClass.READONLY

    if base in {"mkdir", "cp", "mv", "rm", "touch", "chmod", "sed", "python", "python3"}:
        return ShellEffectClass.WORKSPACE_MUTATING

    if base in {"kill", "pkill", "killall"}:
        return ShellEffectClass.PROCESS_CONTROL

    return ShellEffectClass.UNKNOWN


class ShellExecutor:
    def __init__(self, process_manager, workspace_manager) -> None:
        self.process_manager = process_manager
        self.workspace_manager = workspace_manager

    @staticmethod
    def _required_capabilities(effect: str) -> set[str]:
        required = {"PROCESS_EXECUTION"}
        if effect == ShellEffectClass.READONLY:
            required.add("FILE_READ")
        elif effect == ShellEffectClass.WORKSPACE_MUTATING:
            required.add("FILE_WRITE")
        elif effect == ShellEffectClass.PROCESS_CONTROL:
            required.add("PROCESS_CONTROL")
        elif effect == ShellEffectClass.REMOTE_MUTATION:
            required.add("REMOTE_REPOSITORY_MUTATION")
        else:
            raise PermissionError("Effect UNKNOWN: action denied by default")
        return required

    def execute(
        self,
        context: ExecutionContext,
        command: str,
        timeout: int = 300,
        env: Optional[Dict[str, str]] = None,
    ) -> ShellResult:
        if not isinstance(context, ExecutionContext):
            raise TypeError("Canonical ExecutionContext required")
        if not context.workspace_id:
            raise ValueError("Context must have a workspace_id")

        effect = classify_command(command)
        for capability in self._required_capabilities(effect):
            if not context.has_capability(capability):
                raise PermissionError(f"Action requires capability {capability}")

        now = datetime.now(timezone.utc)
        if not context.is_valid(now, self.process_manager.generation):
            raise PermissionError("ExecutionContext expired or generation-stale")

        workspace = self.workspace_manager.status(context, context.workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")
        if workspace.local_path is None:
            raise ValueError("Workspace has no local path")

        start = time.time()
        record = self.process_manager.start(
            context,
            command=["bash", "-lc", command],
            workspace_path=workspace.local_path,
            timeout=timeout,
            env=env,
        )
        record = self.process_manager.wait(context, record.process_id, timeout)
        return ShellResult(
            exit_code=record.exit_code if record and record.exit_code is not None else -1,
            stdout=record.stdout if record else "",
            stderr=record.stderr if record else "",
            duration_ms=int((time.time() - start) * 1000),
            effect_class=effect,
            process_id=record.process_id if record else None,
        )
