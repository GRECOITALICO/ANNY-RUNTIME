"""Governed local Git service for ANNY Runtime.

Git operations are executed only through the canonical ExecutionContext and
ShellExecutor. Repository mutations remain continuity-gated.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from runtime.continuity.mutation import RepositoryMutationContract
from runtime.security.execution_context import ExecutionContext
from runtime.shell.executor import ShellExecutor


class GitService:
    def __init__(self, shell_executor: ShellExecutor, mutation_contract: RepositoryMutationContract) -> None:
        self.shell_executor = shell_executor
        self.mutation_contract = mutation_contract

    @staticmethod
    def _require(context: ExecutionContext, capability: str) -> None:
        if not context.has_capability(capability):
            raise PermissionError(f"Git operation requires capability {capability}")

    def status(self, context: ExecutionContext) -> Dict[str, object]:
        self._require(context, "GIT_READ")
        result = self.shell_executor.execute(context, "git status --porcelain=v1")
        return {
            "status": result.stdout.strip(),
            "exit_code": result.exit_code,
            "effect_class": result.effect_class,
        }

    def diff(self, context: ExecutionContext, ref: Optional[str] = None) -> str:
        self._require(context, "GIT_READ")
        command = "git diff" if not ref else f"git diff -- {ref}"
        result = self.shell_executor.execute(context, command)
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or "git diff failed")
        return result.stdout

    def log(self, context: ExecutionContext, limit: int = 20) -> str:
        self._require(context, "GIT_READ")
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        result = self.shell_executor.execute(
            context,
            f"git log -{int(limit)} --format='%H%n%an%n%s'",
        )
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or "git log failed")
        return result.stdout

    def branch(self, context: ExecutionContext) -> str:
        self._require(context, "GIT_READ")
        result = self.shell_executor.execute(context, "git branch --show-current")
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or "git branch failed")
        return result.stdout.strip()

    def create_branch(
        self,
        context: ExecutionContext,
        branch: str,
        mission_id: str,
        task_id: str,
        step_id: str,
        actor_level: str,
        repository: str,
        reason: str,
        next_action: str,
        execution_id: Optional[str] = None,
    ) -> Dict[str, str]:
        self._require(context, "GIT_WRITE")
        self._validate_branch_name(branch)

        before = self.shell_executor.execute(context, "git rev-parse HEAD")
        if before.exit_code != 0:
            raise RuntimeError(before.stderr.strip() or "cannot resolve HEAD")

        prepare_event = self.mutation_contract.prepare_mutation(
            mission_id=mission_id,
            task_id=task_id,
            step_id=step_id,
            actor_id=context.actor_id,
            actor_level=actor_level,
            repository=repository,
            branch=branch,
            commit_before=before.stdout.strip(),
            reason=reason,
            action="git branch creation",
            next_action=next_action,
            execution_id=execution_id,
        )

        result = self.shell_executor.execute(
            context,
            f"git switch -c {self._quote(branch)}",
        )
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or "git branch creation failed")

        after = self.shell_executor.execute(context, "git rev-parse HEAD")
        commit_after = after.stdout.strip()
        self.mutation_contract.finalize_mutation(
            prepare_event=prepare_event,
            commit_after=commit_after,
            files_changed=[],
            tests=[],
            evidence_refs=[],
        )
        return {"branch": branch, "commit_sha": commit_after}

    def commit(
        self,
        context: ExecutionContext,
        message: str,
        *,
        mission_id: str,
        task_id: str,
        step_id: str,
        actor_level: str,
        repository: str,
        branch: str,
        reason: str,
        tests: List[str],
        evidence_refs: List[str],
        next_action: str,
        execution_id: Optional[str] = None,
        author: Optional[str] = None,
    ) -> Dict[str, str]:
        self._require(context, "GIT_WRITE")
        if not message.strip():
            raise ValueError("Commit message cannot be empty")
        self._validate_branch_name(branch)

        before = self.shell_executor.execute(context, "git rev-parse HEAD")
        if before.exit_code != 0:
            raise RuntimeError(before.stderr.strip() or "cannot resolve HEAD")
        commit_before = before.stdout.strip()

        status = self.shell_executor.execute(context, "git status --porcelain=v1")
        files_changed = [line[:3].strip() if len(line) >= 3 else line for line in status.stdout.splitlines() if line]

        prepare_event = self.mutation_contract.prepare_mutation(
            mission_id=mission_id,
            task_id=task_id,
            step_id=step_id,
            actor_id=context.actor_id,
            actor_level=actor_level,
            repository=repository,
            branch=branch,
            commit_before=commit_before,
            reason=reason,
            action="git commit",
            next_action=next_action,
            execution_id=execution_id,
        )

        add = self.shell_executor.execute(context, "git add -A")
        if add.exit_code != 0:
            raise RuntimeError(add.stderr.strip() or "git add failed")

        commit_command = f"git commit -m {self._quote(message)}"
        if author:
            commit_command += f" --author={self._quote(author)}"
        result = self.shell_executor.execute(context, commit_command)
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or "git commit failed")

        after = self.shell_executor.execute(context, "git log -1 --format='%H%n%an%n%s'")
        if after.exit_code != 0:
            raise RuntimeError(after.stderr.strip() or "cannot resolve committed HEAD")
        lines = after.stdout.strip().splitlines()
        commit_after = lines[0] if lines else ""

        self.mutation_contract.finalize_mutation(
            prepare_event=prepare_event,
            commit_after=commit_after,
            files_changed=files_changed,
            tests=tests,
            evidence_refs=evidence_refs,
        )
        return {
            "commit_sha": commit_after,
            "author": lines[1] if len(lines) > 1 else "",
            "message": lines[2] if len(lines) > 2 else "",
        }

    @staticmethod
    def _validate_branch_name(branch: str) -> None:
        if not branch or branch.strip() != branch or branch.startswith("-"):
            raise ValueError("Invalid Git branch name")
        if any(ch in branch for ch in (" ", "~", "^", ":", "?", "*", "[", "\\")):
            raise ValueError("Invalid Git branch name")

    @staticmethod
    def _quote(value: str) -> str:
        import shlex
        return shlex.quote(value)
