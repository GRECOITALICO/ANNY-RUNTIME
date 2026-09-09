import enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

class ExecutionStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"

class FailureReason(str, enum.Enum):
    TOOL_ERROR = "TOOL_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    TIMEOUT = "TIMEOUT"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    INVALID_TASK = "INVALID_TASK"

class WorkerState(str, enum.Enum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    TERMINATED = "TERMINATED"

@dataclass
class WorkerDefinition:
    worker_id: str
    execution_id: str
    task_id: str
    capability_id: str
    executor_type: str
    executor_id: str
    model_id: Optional[str]
    workspace_id: str
    created_at: datetime
    deadline: datetime
    resource_limits: Dict[str, Any]
    network_policy: str
    filesystem_policy: str
    state: WorkerState = WorkerState.CREATED
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

@dataclass
class Task:
    task_id: str
    capability_id: str
    input: Dict[str, Any]
    constraints: Dict[str, Any]
    deadline: datetime
    workspace_policy: str
    evidence_policy: str
    requested_by: str
    created_at: datetime

@dataclass
class TaskExecutionContext:
    execution_id: str
    task_id: str
    capability_id: str
    workspace_path: str
    environment: Dict[str, str]
    allowed_tools: List[str]
    deadline: datetime
    resource_limits: Dict[str, Any]
    network_policy: str
    write_policy: str
    
    # Internal tracking
    status: ExecutionStatus = ExecutionStatus.QUEUED
    result: Optional[Dict[str, Any]] = None
    failure_reason: Optional[FailureReason] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    
    # Execution Record (Phase 11)
    executor_type: Optional[str] = None
    executor_id: Optional[str] = None
    model_id: Optional[str] = None
    policy_version: Optional[str] = None
    input_hash: Optional[str] = None
    result_hash: Optional[str] = None
    evidence_ref: Optional[str] = None
    
    # Evaluation (Phase 12)
    execution_score: Optional[int] = None
    validation_status: Optional[str] = None
    review_status: Optional[str] = None
