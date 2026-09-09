import os
import json
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any

from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus, FailureReason
from runtime.workspace.ephemeral import EphemeralWorkspaceManager

class ExecutorLimitsExceeded(Exception):
    pass

class ExecutorSecurityError(Exception):
    pass

class DeterministicExecutor:
    def __init__(self, workspace_manager: EphemeralWorkspaceManager):
        self.workspace_manager = workspace_manager
        # Hardcoded version for reproducibility
        self.runtime_version = "1.0.0"
        self.tool_version = "1.0.0"

    def execute(self, task: Task, context: TaskExecutionContext) -> None:
        """
        Executes a deterministic capability with strict lifecycle management.
        """
        if context.status != ExecutionStatus.QUEUED:
            context.failure_reason = FailureReason.INVALID_TASK
            context.status = ExecutionStatus.FAILED
            context.error_message = "Execution context is not QUEUED"
            return
            
        context.status = ExecutionStatus.RUNNING
        context.started_at = datetime.now(timezone.utc)
        
        # Determine actual capability
        if task.capability_id not in ("filesystem.inspect", "filesystem.hash", "repository.inspect"):
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.INVALID_TASK
            context.error_message = f"Unsupported capability: {task.capability_id}"
            return
            
        try:
            if task.capability_id == "filesystem.inspect":
                self._execute_filesystem_inspect(task, context)
            elif task.capability_id == "filesystem.hash":
                self._execute_filesystem_hash(task, context)
            elif task.capability_id == "repository.inspect":
                self._execute_repository_inspect(task, context)
                
            if context.status == ExecutionStatus.RUNNING:
                context.status = ExecutionStatus.SUCCEEDED
        except ExecutorLimitsExceeded as e:
            context.status = ExecutionStatus.LIMIT_EXCEEDED
            context.failure_reason = FailureReason.LIMIT_EXCEEDED
            context.error_message = str(e)
        except ExecutorSecurityError as e:
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.AUTHORIZATION_DENIED
            context.error_message = str(e)
        except TimeoutError as e:
            context.status = ExecutionStatus.TIMED_OUT
            context.failure_reason = FailureReason.TIMEOUT
            context.error_message = str(e)
        except Exception as e:
            context.status = ExecutionStatus.FAILED
            context.failure_reason = FailureReason.EXECUTION_ERROR
            context.error_message = str(e)
        finally:
            context.completed_at = datetime.now(timezone.utc)
            context.duration_ms = int((context.completed_at - context.started_at).total_seconds() * 1000)
            self._finalize_workspace(task, context)

    def _hash_dict(self, d: dict) -> str:
        s = json.dumps(d, sort_keys=True).encode('utf-8')
        return hashlib.sha256(s).hexdigest()

    def _execute_filesystem_inspect(self, task: Task, context: TaskExecutionContext):
        # 1. Enforce Timeout / Deadline
        if datetime.now(timezone.utc) > context.deadline:
            raise TimeoutError("Deadline exceeded before execution started")
            
        target_path = task.input.get("path")
        if not target_path:
            raise ValueError("Missing 'path' in input")
            
        # 2. Security Check (Forbidden paths)
        forbidden_paths = [
            "/var/lib/anny-runtime/secrets",
            "/home/anny/.ssh",
            "/root"
        ]
        abs_target = os.path.abspath(target_path)
        for fp in forbidden_paths:
            if abs_target.startswith(os.path.abspath(fp)):
                raise ExecutorSecurityError(f"Access to {fp} is explicitly denied")
                
        # 3. Simulate tool invocation
        start_time = time.time()
        
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
                "mtime": stat.st_mtime
            }
            
        # 4. Check limits
        max_out = context.resource_limits.get("max_output_size", 1024 * 1024)
        result_json = json.dumps(result)
        if len(result_json.encode('utf-8')) > max_out:
            raise ExecutorLimitsExceeded("Output size exceeded maximum limit")
            
        if datetime.now(timezone.utc) > context.deadline:
            raise TimeoutError("Deadline exceeded during execution")
            
        context.result = result

    def _execute_filesystem_hash(self, task: Task, context: TaskExecutionContext):
        if datetime.now(timezone.utc) > context.deadline:
            raise TimeoutError("Deadline exceeded before execution started")
            
        target_path = task.input.get("path")
        if not target_path:
            raise ValueError("Missing 'path' in input")
            
        abs_target = os.path.abspath(target_path)
        if not os.path.exists(abs_target):
            result = {"error": "Path does not exist", "path": target_path}
        elif os.path.isdir(abs_target):
            result = {"error": "Cannot hash a directory", "path": target_path}
        else:
            with open(abs_target, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            result = {"path": target_path, "sha256": file_hash}
            
        max_out = context.resource_limits.get("max_output_size", 1024 * 1024)
        if len(json.dumps(result).encode('utf-8')) > max_out:
            raise ExecutorLimitsExceeded("Output size exceeded maximum limit")
            
        context.result = result

    def _execute_repository_inspect(self, task: Task, context: TaskExecutionContext):
        if datetime.now(timezone.utc) > context.deadline:
            raise TimeoutError("Deadline exceeded before execution started")
            
        repo_path = task.input.get("path")
        if not repo_path:
            raise ValueError("Missing 'path' in input")
            
        abs_target = os.path.abspath(repo_path)
        if not os.path.exists(abs_target):
            result = {"error": "Repository path does not exist", "path": repo_path}
        else:
            is_git = os.path.exists(os.path.join(abs_target, ".git"))
            result = {
                "path": repo_path,
                "is_git_repository": is_git,
                "status": "clean" if is_git else "unknown"
            }
            
        max_out = context.resource_limits.get("max_output_size", 1024 * 1024)
        if len(json.dumps(result).encode('utf-8')) > max_out:
            raise ExecutorLimitsExceeded("Output size exceeded maximum limit")
            
        context.result = result

    def _finalize_workspace(self, task: Task, context: TaskExecutionContext):
        """
        Write Observability, Reproducibility, Evidence, and Result to the workspace.
        """
        ws_path = context.workspace_path
        if not os.path.exists(ws_path):
            return
            
        # result.json
        res_file = os.path.join(ws_path, "result", "result.json")
        res_data = {
            "status": context.status.value,
            "failure_reason": context.failure_reason.value if context.failure_reason else None,
            "error_message": context.error_message,
            "data": context.result
        }
        with open(res_file, "w") as f:
            json.dump(res_data, f, indent=2)
            
        # observability.json
        obs_file = os.path.join(ws_path, "logs", "observability.json")
        obs_data = {
            "execution_started": context.started_at.isoformat() if context.started_at else None,
            "execution_completed": context.completed_at.isoformat() if context.completed_at else None,
            "duration_ms": context.duration_ms,
            "exit_code": 0 if context.status == ExecutionStatus.SUCCEEDED else 1,
            "workspace_size": self.workspace_manager.get_workspace_size(ws_path),
            "result_size": os.path.getsize(res_file) if os.path.exists(res_file) else 0,
            "events": [
                "execution_started",
                "tool_invoked: filesystem.inspect",
                "tool_completed: filesystem.inspect",
                "execution_completed"
            ]
        }
        with open(obs_file, "w") as f:
            json.dump(obs_data, f, indent=2)
            
        # reproducibility.json
        input_hash = self._hash_dict(task.input)
        output_hash = self._hash_dict(res_data)
        evidence_hash = self._hash_dict(obs_data) # Simplified: evidence is obs data for now
        
        rep_file = os.path.join(ws_path, "metadata", "reproducibility.json")
        rep_data = {
            "task_id": task.task_id,
            "execution_id": context.execution_id,
            "runtime_version": self.runtime_version,
            "tool_version": self.tool_version,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "evidence_hash": evidence_hash
        }
        with open(rep_file, "w") as f:
            json.dump(rep_data, f, indent=2)
            
        # evidence.json
        ev_file = os.path.join(ws_path, "evidence", "evidence.json")
        with open(ev_file, "w") as f:
            json.dump({"observability": obs_data, "reproducibility": rep_data}, f, indent=2)
            
        # Workspace size limit check during finalize
        max_ws = context.resource_limits.get("max_workspace_size", 10 * 1024 * 1024)
        if obs_data["workspace_size"] > max_ws:
            context.status = ExecutionStatus.LIMIT_EXCEEDED
            context.failure_reason = FailureReason.LIMIT_EXCEEDED
            context.error_message = "Workspace size limit exceeded"
            
        # Depending on policy, cleanup could happen here, but we leave it to the caller to extract results first.
