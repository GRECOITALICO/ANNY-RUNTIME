import os
import json
import time
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any
from pathlib import Path

from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus, FailureReason
from runtime.security.path_containment import (
    AuthorizedResourceScope,
    ContainmentError,
    require_contained_path,
    require_resource_scope,
)
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


class ExecutorLimitsExceeded(Exception):
    pass


class ExecutorSecurityError(Exception):
    pass


class DeterministicExecutor:
    """Execute local deterministic capabilities with bounded, auditable behavior."""

    def __init__(self, workspace_manager: EphemeralWorkspaceManager):
        self.workspace_manager = workspace_manager
        self.runtime_version = "1.1.0"
        self.tool_version = "1.1.0"

    def execute(self, task: Task, context: TaskExecutionContext) -> None:
        if context.status != ExecutionStatus.QUEUED:
            context.failure_reason = FailureReason.INVALID_TASK
            context.status = ExecutionStatus.FAILED
            context.error_message = "Execution context is not QUEUED"
            return

        context.status = ExecutionStatus.RUNNING
        context.started_at = datetime.now(timezone.utc)
        supported = {
            "filesystem.inspect": self._execute_filesystem_inspect,
            "filesystem.list": self._execute_filesystem_list,
            "filesystem.hash": self._execute_filesystem_hash,
            "repository.inspect": self._execute_repository_inspect,
            "repository.search": self._execute_repository_search,
            "repository.read": self._execute_repository_read,
            "repository.diff": self._execute_repository_diff,
            "artifact.metadata": self._execute_artifact_metadata,
        }
        handler = supported.get(task.capability_id)
        if handler is None:
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.INVALID_TASK
            context.error_message = f"Unsupported deterministic capability: {task.capability_id}"
            return

        try:
            handler(task, context)
            if context.status == ExecutionStatus.RUNNING:
                context.status = ExecutionStatus.SUCCEEDED
        except ExecutorLimitsExceeded as exc:
            context.status = ExecutionStatus.LIMIT_EXCEEDED
            context.failure_reason = FailureReason.LIMIT_EXCEEDED
            context.error_message = str(exc)
        except ExecutorSecurityError as exc:
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.AUTHORIZATION_DENIED
            context.error_message = str(exc)
        except TimeoutError as exc:
            context.status = ExecutionStatus.TIMED_OUT
            context.failure_reason = FailureReason.TIMEOUT
            context.error_message = str(exc)
        except Exception as exc:
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.EXECUTION_ERROR
            context.error_message = str(exc)
        finally:
            context.completed_at = datetime.now(timezone.utc)
            context.duration_ms = int((context.completed_at - context.started_at).total_seconds() * 1000)
            self._finalize_workspace(task, context)

    def _deadline(self, context: TaskExecutionContext) -> None:
        if datetime.now(timezone.utc) > context.deadline:
            raise TimeoutError("Deadline exceeded")

    def _resource_scope(self, task: Task, context: TaskExecutionContext) -> AuthorizedResourceScope:
        """Resolve the authorized identity scope; path containment is separate."""
        # Once an explicit resource identity is supplied, its root is required
        # too.  Do not silently fall back to the workspace for a malformed
        # repository/resource binding.
        explicit_scope = context.authorized_resource_id is not None
        root = context.authorized_resource_root if explicit_scope else context.workspace_path
        resource_id = context.authorized_resource_id or f"workspace:{context.execution_id}"
        scope = AuthorizedResourceScope(
            resource_id=resource_id,
            project_id=context.authorized_resource_project_id or context.project_id,
            tenant_id=context.authorized_resource_tenant_id or context.tenant_id,
            authorized_root=root,
            access_mode=context.resource_access_mode,
            resource_kind=context.resource_kind,
        )
        try:
            return require_resource_scope(
                scope,
                resource_id=task.input.get("resource_id"),
                project_id=task.input.get("project_id", context.project_id),
                tenant_id=task.input.get("tenant_id", context.tenant_id),
                operation=task.input.get("operation", "READ"),
            )
        except ContainmentError as exc:
            raise ExecutorSecurityError(str(exc)) from exc

    def _enforce_path(self, path: str, task: Task, context: TaskExecutionContext) -> str:
        """Require both resource authorization and physical path containment."""
        scope = self._resource_scope(task, context)
        try:
            target = Path(require_contained_path(scope.authorized_root, path).resolved_path)
        except ContainmentError as exc:
            raise ExecutorSecurityError(str(exc)) from exc
        forbidden_paths = [Path.home() / ".ssh"]
        data_dir = os.environ.get("ANNY_DATA_DIR")
        if data_dir:
            forbidden_paths.append(Path(data_dir).expanduser().resolve(strict=False) / "secrets")
        for forbidden_path in forbidden_paths:
            forbidden_path = forbidden_path.resolve(strict=False)
            if target == forbidden_path or forbidden_path in target.parents:
                raise ExecutorSecurityError(
                    f"Access to {forbidden_path} is explicitly denied"
                )
        return str(target)

    def _limit_output(self, context: TaskExecutionContext, result: Dict[str, Any]) -> None:
        encoded = json.dumps(result, sort_keys=True, default=str).encode("utf-8")
        max_out = context.resource_limits.get("max_output_size", 1024 * 1024)
        if len(encoded) > max_out:
            raise ExecutorLimitsExceeded("Output size exceeded maximum limit")
        context.result = result

    def _execute_filesystem_inspect(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        target_path = task.input.get("path")
        if not isinstance(target_path, str) or not target_path:
            raise ValueError("Missing 'path' in input")
        abs_target = self._enforce_path(target_path, task, context)
        if not os.path.exists(abs_target):
            result = {"error": "Path does not exist", "path": target_path}
        else:
            stat = os.stat(abs_target)
            result = {
                "path": target_path,
                "is_dir": os.path.isdir(abs_target),
                "is_file": os.path.isfile(abs_target),
                "size_bytes": stat.st_size,
                "mode": oct(stat.st_mode),
                "mtime": stat.st_mtime,
            }
        self._limit_output(context, result)
        self._deadline(context)

    def _execute_filesystem_list(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        target_path = task.input.get("path")
        if not isinstance(target_path, str) or not target_path:
            raise ValueError("Missing 'path' in input")
        abs_target = self._enforce_path(target_path, task, context)
        if not os.path.isdir(abs_target):
            result = {"error": "Directory does not exist", "path": target_path, "entries": []}
        else:
            entries = []
            for name in sorted(os.listdir(abs_target)):
                full = os.path.join(abs_target, name)
                entries.append({
                    "name": name,
                    "is_dir": os.path.isdir(full),
                    "is_file": os.path.isfile(full),
                    "size_bytes": os.path.getsize(full) if os.path.isfile(full) else None,
                })
            result = {"path": target_path, "entries": entries}
        self._limit_output(context, result)

    def _execute_filesystem_hash(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        target_path = task.input.get("path")
        if not isinstance(target_path, str) or not target_path:
            raise ValueError("Missing 'path' in input")
        abs_target = self._enforce_path(target_path, task, context)
        if not os.path.exists(abs_target):
            result = {"error": "Path does not exist", "path": target_path}
        elif os.path.isdir(abs_target):
            result = {"error": "Cannot hash a directory", "path": target_path}
        else:
            digest = hashlib.sha256()
            with open(abs_target, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    self._deadline(context)
            result = {"path": target_path, "algorithm": "sha256", "sha256": digest.hexdigest()}
        self._limit_output(context, result)

    def _git(self, repo_path: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", repo_path, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _repository_path(self, task: Task, context: TaskExecutionContext) -> str:
        repo_path = task.input.get("path")
        if not isinstance(repo_path, str) or not repo_path:
            raise ValueError("Missing repository 'path' in input")
        abs_target = self._enforce_path(repo_path, task, context)
        if not os.path.exists(os.path.join(abs_target, ".git")):
            raise ValueError("Path is not a Git repository")
        return abs_target

    def _execute_repository_inspect(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        repo_path = task.input.get("path")
        if not isinstance(repo_path, str) or not repo_path:
            raise ValueError("Missing 'path' in input")
        abs_target = self._enforce_path(repo_path, task, context)
        if not os.path.exists(abs_target):
            result = {"error": "Repository path does not exist", "path": repo_path}
        else:
            is_git = os.path.exists(os.path.join(abs_target, ".git"))
            head = self._git(abs_target, ["rev-parse", "HEAD"]).stdout.strip() if is_git else None
            result = {"path": repo_path, "is_git_repository": is_git, "head": head}
        self._limit_output(context, result)

    def _execute_repository_search(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        repo_path = self._repository_path(task, context)
        pattern = task.input.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("Missing search 'pattern'")
        result = self._git(repo_path, ["grep", "-n", "-I", "--", pattern])
        lines = sorted([line for line in result.stdout.splitlines() if line])
        self._limit_output(context, {"repository": repo_path, "pattern": pattern, "matches": lines, "exit_code": result.returncode})

    def _execute_repository_read(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        repo_path = self._repository_path(task, context)
        head = self._git(repo_path, ["rev-parse", "HEAD"]).stdout.strip()
        branch = self._git(repo_path, ["branch", "--show-current"]).stdout.strip()
        status = self._git(repo_path, ["status", "--porcelain=v1"]).stdout.splitlines()
        result = {
            "repository": repo_path,
            "head": head,
            "branch": branch,
            "dirty": bool(status),
            "status_entries": sorted(status),
        }
        self._limit_output(context, result)

    def _execute_repository_diff(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        repo_path = self._repository_path(task, context)
        base = task.input.get("base")
        head = task.input.get("head")
        if not isinstance(base, str) or not base:
            raise ValueError("Missing diff 'base'")
        args = ["diff", "--no-ext-diff", "--unified=3", base]
        if head:
            args.append(head)
        result = self._git(repo_path, args)
        diff_text = result.stdout
        self._limit_output(context, {
            "repository": repo_path,
            "base": base,
            "head": head or "",
            "exit_code": result.returncode,
            "diff": diff_text,
        })

    def _execute_artifact_metadata(self, task: Task, context: TaskExecutionContext) -> None:
        self._deadline(context)
        target_path = task.input.get("path")
        if not isinstance(target_path, str) or not target_path:
            raise ValueError("Missing artifact 'path' in input")
        abs_target = self._enforce_path(target_path, task, context)
        if not os.path.exists(abs_target):
            result = {"error": "Artifact does not exist", "path": target_path}
        else:
            stat = os.stat(abs_target)
            result = {
                "path": target_path,
                "is_file": os.path.isfile(abs_target),
                "is_dir": os.path.isdir(abs_target),
                "size_bytes": stat.st_size,
                "mtime": stat.st_mtime,
                "sha256": self._sha256_path(abs_target) if os.path.isfile(abs_target) else None,
            }
        self._limit_output(context, result)

    def _sha256_path(self, path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _hash_dict(self, value: dict) -> str:
        encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _finalize_workspace(self, task: Task, context: TaskExecutionContext) -> None:
        ws_path = context.workspace_path
        if not os.path.exists(ws_path):
            return

        os.makedirs(os.path.join(ws_path, "logs"), exist_ok=True)
        os.makedirs(os.path.join(ws_path, "evidence"), exist_ok=True)
        os.makedirs(os.path.join(ws_path, "result"), exist_ok=True)
        os.makedirs(os.path.join(ws_path, "metadata"), exist_ok=True)

        result_file = os.path.join(ws_path, "result", "result.json")
        result_data = {
            "status": context.status.value,
            "failure_reason": context.failure_reason.value if context.failure_reason else None,
            "error_message": context.error_message,
            "data": context.result,
        }
        with open(result_file, "w", encoding="utf-8") as handle:
            json.dump(result_data, handle, indent=2, sort_keys=True, default=str)

        observability = {
            "execution_started": context.started_at.isoformat() if context.started_at else None,
            "execution_completed": context.completed_at.isoformat() if context.completed_at else None,
            "duration_ms": context.duration_ms,
            "exit_code": 0 if context.status == ExecutionStatus.SUCCEEDED else 1,
            "workspace_size": self.workspace_manager.get_workspace_size(ws_path),
            "result_size": os.path.getsize(result_file),
            "capability_id": task.capability_id,
            "events": [
                "execution_started",
                f"capability_invoked: {task.capability_id}",
                "execution_completed",
            ],
        }
        with open(os.path.join(ws_path, "logs", "observability.json"), "w", encoding="utf-8") as handle:
            json.dump(observability, handle, indent=2, sort_keys=True)

        input_hash = self._hash_dict(task.input)
        output_hash = self._hash_dict(result_data)
        evidence_hash = self._hash_dict(observability)
        context.input_hash = input_hash
        context.result_hash = output_hash
        context.evidence_ref = os.path.join(ws_path, "evidence", "evidence.json")

        reproducibility = {
            "task_id": task.task_id,
            "execution_id": context.execution_id,
            "runtime_version": self.runtime_version,
            "tool_version": self.tool_version,
            "capability_id": task.capability_id,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "evidence_hash": evidence_hash,
        }
        with open(os.path.join(ws_path, "metadata", "reproducibility.json"), "w", encoding="utf-8") as handle:
            json.dump(reproducibility, handle, indent=2, sort_keys=True)
        with open(context.evidence_ref, "w", encoding="utf-8") as handle:
            json.dump({"observability": observability, "reproducibility": reproducibility}, handle, indent=2, sort_keys=True)

        max_ws = context.resource_limits.get("max_workspace_size", 10 * 1024 * 1024)
        if observability["workspace_size"] > max_ws:
            context.status = ExecutionStatus.LIMIT_EXCEEDED
            context.failure_reason = FailureReason.LIMIT_EXCEEDED
            context.error_message = "Workspace size limit exceeded"
