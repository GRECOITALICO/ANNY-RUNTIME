from typing import Dict, Optional, List
import time
from runtime.shell.executor import ShellExecutor
from runtime.capability.gate import Capability
from runtime.continuity.mutation import RepositoryMutationContract

class GitService:
    def __init__(self, shell_executor: ShellExecutor, mutation_contract: RepositoryMutationContract) -> None:
        self.shell_executor = shell_executor
        self.mutation_contract = mutation_contract

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

    def commit(
        self,
        workspace_id: str,
        session_id: str,
        actor_id: str,
        tenant_id: str,
        message: str,
        author: Optional[str],
        # CONTINUITY METADATA (Required to NOT fail closed)
        mission_id: str,
        task_id: str,
        step_id: str,
        actor_level: str,
        repository: str,
        branch: str,
        reason: str,
        action: str,
        tests: List[str],
        evidence_refs: List[str],
        next_action: str
    ) -> Dict[str, str]:
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

        # 1. Capture commit_before
        log_before = self.shell_executor.execute(
            command="git rev-parse HEAD || echo ''",
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            tenant_id=tenant_id
        )
        commit_before = log_before.stdout.strip()

        # 2. PHASE 1: Prepare Mutation
        prepare_event = self.mutation_contract.prepare_mutation(
            mission_id=mission_id,
            task_id=task_id,
            step_id=step_id,
            actor_id=actor_id,
            actor_level=actor_level,
            repository=repository,
            branch=branch,
            commit_before=commit_before,
            reason=reason,
            action=action,
            next_action=next_action
        )

        # 3. Find files changed
        status_res = self.shell_executor.execute(
            command="git diff --name-only --cached || git diff --name-only",
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            tenant_id=tenant_id
        )
        files_changed = [f for f in status_res.stdout.splitlines() if f]

        # 4. Perform the Git Mutation
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

        # 5. Capture commit_after
        log_res = self.shell_executor.execute(
            command="git log -1 --format='%H%n%an%n%s'",
            workspace_id=workspace_id,
            session_id=session_id,
            actor_id=actor_id,
            tenant_id=tenant_id
        )
        lines = log_res.stdout.strip().split('\n')
        commit_after = lines[0] if len(lines) > 0 else ""
        
        # 6. PHASE 2: Finalize Mutation
        self.mutation_contract.finalize_mutation(
            prepare_event=prepare_event,
            commit_after=commit_after,
            files_changed=files_changed,
            tests=tests,
            evidence_refs=evidence_refs
        )

        return {
            "commit_sha": commit_after,
            "author": lines[1] if len(lines) > 1 else "",
            "message": lines[2] if len(lines) > 2 else "",
            "timestamp": str(time.time())
        }
