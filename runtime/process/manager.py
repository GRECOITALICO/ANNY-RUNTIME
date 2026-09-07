from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional, Dict
import subprocess
import time
import uuid

class ProcessState(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    TIMED_OUT = auto()
    KILLED = auto()

@dataclass
class ProcessRecord:
    process_id: str
    execution_id: str
    operation_id: str
    actor_id: str
    session_id: str
    tenant_id: str
    workspace_id: str
    command: List[str]
    state: ProcessState
    pid: Optional[int]
    exit_code: Optional[int]
    stdout: str
    stderr: str
    started_at: Optional[str]
    finished_at: Optional[str]
    timeout_seconds: int
    runtime_generation: int

class ProcessManager:
    def __init__(self, config: dict, generation: int) -> None:
        self.config = config
        self.generation = generation
        self._processes: Dict[str, ProcessRecord] = {}
        self._handles: Dict[str, subprocess.Popen] = {}
        self.max_concurrent = config.get('max_concurrent_executions', 10)

    def _enforce_limits(self) -> None:
        active = len(self.active_processes())
        if active >= self.max_concurrent:
            raise RuntimeError("Max concurrent executions reached")

    def _validate_ownership(self, context, process_id: str) -> Optional[ProcessRecord]:
        record = self._processes.get(process_id)
        if not record:
            return None
            
        if record.tenant_id != context.tenant_id:
            raise PermissionError("Access denied: tenant mismatch")
        if record.actor_id != context.actor_id:
            raise PermissionError("Access denied: actor mismatch")
        if record.workspace_id != context.workspace_id:
            raise PermissionError("Access denied: workspace mismatch")
        if record.runtime_generation != context.generation:
            raise PermissionError("Access denied: generation stale")
            
        return record

    def start(
        self,
        context,
        command: List[str],
        workspace_path: str,
        timeout: int,
        env: Optional[Dict[str, str]] = None
    ) -> ProcessRecord:
        if not context.has_capability("PROCESS_EXECUTION"):
            raise PermissionError("Access denied: missing PROCESS_EXECUTION capability")
            
        self._enforce_limits()
        
        process_id = str(uuid.uuid4())
        record = ProcessRecord(
            process_id=process_id,
            execution_id=context.execution_id,
            operation_id=context.operation_id,
            actor_id=context.actor_id,
            session_id=context.session_id,
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            command=command,
            state=ProcessState.PENDING,
            pid=None,
            exit_code=None,
            stdout="",
            stderr="",
            started_at=str(time.time()),
            finished_at=None,
            timeout_seconds=timeout,
            runtime_generation=context.generation
        )
        
        try:
            handle = subprocess.Popen(
                command,
                cwd=workspace_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            record.pid = handle.pid
            record.state = ProcessState.RUNNING
            self._processes[process_id] = record
            self._handles[process_id] = handle
        except Exception as e:
            record.state = ProcessState.FAILED
            record.stderr = str(e)
            record.finished_at = str(time.time())
            self._processes[process_id] = record
            
        return record

    def status(self, context, process_id: str) -> Optional[ProcessRecord]:
        return self._validate_ownership(context, process_id)

    def stop(self, context, process_id: str, signal: int = 15) -> Optional[ProcessRecord]:
        if not context.has_capability("PROCESS_CONTROL"):
            raise PermissionError("Access denied: missing PROCESS_CONTROL capability")
            
        record = self._validate_ownership(context, process_id)
        if not record:
            return None
            
        handle = self._handles.get(process_id)
        if handle and record.state == ProcessState.RUNNING:
            handle.send_signal(signal)
            record.state = ProcessState.KILLED
            record.finished_at = str(time.time())
        return record

    def wait(self, context, process_id: str, timeout: int) -> Optional[ProcessRecord]:
        record = self._validate_ownership(context, process_id)
        if not record:
            return None
            
        handle = self._handles.get(process_id)
        if not handle or record.state != ProcessState.RUNNING:
            return record
            
        try:
            stdout, stderr = handle.communicate(timeout=timeout)
            record.stdout = stdout
            record.stderr = stderr
            record.exit_code = handle.returncode
            record.state = ProcessState.COMPLETED if handle.returncode == 0 else ProcessState.FAILED
        except subprocess.TimeoutExpired:
            handle.kill()
            record.state = ProcessState.TIMED_OUT
            stdout, stderr = handle.communicate()
            record.stdout = stdout
            record.stderr = stderr
            
        record.finished_at = str(time.time())
        return record

    def active_processes(self) -> List[ProcessRecord]:
        return [p for p in self._processes.values() if p.state == ProcessState.RUNNING]

    def mark_stale(self, current_generation: int) -> None:
        for record in self._processes.values():
            if record.runtime_generation < current_generation and record.state == ProcessState.RUNNING:
                handle = self._handles.get(record.process_id)
                if handle:
                    handle.kill()
                record.state = ProcessState.KILLED
