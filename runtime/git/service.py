from typing import Dict, Optional
import time
from runtime.shell.executor import ShellExecutor
from runtime.capability.gate import Capability

class GitService:
    def __init__(self, shell_executor: ShellExecutor) -> None:
        self.shell_executor = shell_executor

    def status(self, workspace_id: str, session_id: str, actor_id: str, tenant_id: str) -> Dict[str, str]:
        decision = self.shell_executor.capability_gate.check(
            session_id=session_id,
            actor_id=actor_id,
            capability=Capability.GIT_READ,
            workspace_id=workspace_id,
            runtime_generation=self.shell_executor.process_manager.generation,
            current_generation=self.shell_executor.process_manager.generation
        )
        if not decision.allowed:
            raise PermissionError(f"GIT_READ denied: {decision.reason}")

        res = self.shell_executor.execute(
            command="git status --porcelain",
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            tenant_id=tenant_id
        )
        return {"status": res.stdout.strip()}

    def diff(self, workspace_id: str, session_id: str, actor_id: str, tenant_id: str, ref: Optional[str] = None) -> str:
        decision = self.shell_executor.capability_gate.check(
            session_id=session_id,
            actor_id=actor_id,
            capability=Capability.GIT_READ,
            workspace_id=workspace_id,
            runtime_generation=self.shell_executor.process_manager.generation,
            current_generation=self.shell_executor.process_manager.generation
        )
        if not decision.allowed:
            raise PermissionError(f"GIT_READ denied: {decision.reason}")

        cmd = f"git diff {ref}" if ref else "git diff"
        res = self.shell_executor.execute(
            command=cmd,
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            tenant_id=tenant_id
        )
        return res.stdout

    def commit(self, workspace_id: str, session_id: str, actor_id: str, tenant_id: str, message: str, author: Optional[str] = None) -> Dict[str, str]:
        decision = self.shell_executor.capability_gate.check(
            session_id=session_id,
            actor_id=actor_id,
            capability=Capability.GIT_WRITE,
            workspace_id=workspace_id,
            runtime_generation=self.shell_executor.process_manager.generation,
            current_generation=self.shell_executor.process_manager.generation
        )
        if not decision.allowed:
            raise PermissionError(f"GIT_WRITE denied: {decision.reason}")

        cmd = f"git add -A && git commit -m {repr(message)}"
        if author:
            cmd += f" --author={repr(author)}"

        res = self.shell_executor.execute(
            command=cmd,
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            tenant_id=tenant_id
        )

        log_res = self.shell_executor.execute(
            command="git log -1 --format='%H%n%an%n%s'",
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            tenant_id=tenant_id
        )
        lines = log_res.stdout.strip().split('\n')
        
        return {
            "commit_sha": lines[0] if len(lines) > 0 else "",
            "author": lines[1] if len(lines) > 1 else "",
            "message": lines[2] if len(lines) > 2 else "",
            "timestamp": str(time.time())
        }
