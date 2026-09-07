from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set
from datetime import datetime
import time

@dataclass(frozen=True)
class ExecutionContext:
    tenant_id: str
    anny_instance_id: str
    runtime_id: str
    session_id: str
    actor_id: str
    operation_id: str
    execution_id: str
    generation: int
    issued_at: datetime
    expires_at: datetime
    workspace_id: Optional[str] = None
    capabilities: Set[str] = field(default_factory=set)
    
    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

@dataclass
class ShellResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int

class ShellEffectClass:
    READONLY = "READONLY"
    WORKSPACE_MUTATING = "WORKSPACE_MUTATING"
    PROCESS_CONTROL = "PROCESS_CONTROL"
    REMOTE_MUTATION = "REMOTE_MUTATION"
    UNKNOWN = "UNKNOWN"

def classify_command(command: str) -> str:
    cmd_base = command.split()[0] if command.split() else ""
    
    readonly_cmds = {"ls", "cat", "grep", "find", "head", "tail", "wc", "diff"}
    mutating_cmds = {"mkdir", "cp", "mv", "rm", "touch", "chmod", "sed"}
    process_cmds = {"kill", "pkill", "killall"}
    
    if cmd_base in readonly_cmds:
        return ShellEffectClass.READONLY
    if cmd_base in mutating_cmds:
        return ShellEffectClass.WORKSPACE_MUTATING
    if cmd_base in process_cmds:
        return ShellEffectClass.PROCESS_CONTROL
    
    if cmd_base == "git":
        if len(command.split()) > 1:
            sub = command.split()[1]
            if sub in {"status", "log", "diff"}:
                return ShellEffectClass.READONLY
            if sub in {"push", "remote"}:
                return ShellEffectClass.REMOTE_MUTATION
    
    if cmd_base == "echo" and ">" in command:
        return ShellEffectClass.WORKSPACE_MUTATING
        
    if "curl -X POST" in command or "wget --post" in command:
        return ShellEffectClass.REMOTE_MUTATION
        
    return ShellEffectClass.UNKNOWN

class ShellExecutor:
    def __init__(self, process_manager, workspace_manager) -> None:
        self.process_manager = process_manager
        self.workspace_manager = workspace_manager

    def execute(
        self,
        context: ExecutionContext,
        command: str,
        timeout: int = 300,
        env: Optional[Dict[str, str]] = None
    ) -> ShellResult:
        start_time = time.time()
        
        effect = classify_command(command)
        
        req_cap = None
        if effect == ShellEffectClass.READONLY:
            req_cap = "FILE_READ"
        elif effect == ShellEffectClass.WORKSPACE_MUTATING:
            req_cap = "FILE_WRITE"
        elif effect == ShellEffectClass.PROCESS_CONTROL:
            req_cap = "PROCESS_CONTROL"
        elif effect == ShellEffectClass.REMOTE_MUTATION:
            req_cap = "REMOTE_REPOSITORY_MUTATION"
        else:
            raise PermissionError("Effect UNKNOWN: Action denied by default")
            
        if not context.has_capability(req_cap):
            raise PermissionError(f"Action requires capability {req_cap}")
            
        if not context.workspace_id:
            raise ValueError("Context must have a workspace_id")
            
        ws = self.workspace_manager.status(context.workspace_id)
        if not ws:
            raise ValueError("Workspace not found")
            
        record = self.process_manager.start(
            context,
            command=['bash', '-c', command],
            workspace_path=ws.local_path,
            timeout=timeout,
            env=env
        )
        
        if record:
            record = self.process_manager.wait(context, record.process_id, timeout)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return ShellResult(
            exit_code=record.exit_code if record and record.exit_code is not None else -1,
            stdout=record.stdout if record else "",
            stderr=record.stderr if record else "",
            duration_ms=duration_ms
        )
