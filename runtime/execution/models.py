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
    executor_version: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    policy_version: Optional[str] = None
    input_hash: Optional[str] = None
    result_hash: Optional[str] = None
    evidence_ref: Optional[str] = None
    
    # Evaluation (Phase 12)
    execution_score: Optional[int] = None
    validation_status: Optional[str] = None
    review_status: Optional[str] = None

class ModelState(str, enum.Enum):
    REGISTERED = "REGISTERED"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INSTALL_REQUIRED = "INSTALL_REQUIRED"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"
    QUARANTINED = "QUARANTINED"

@dataclass
class ModelDefinition:
    model_id: str
    display_name: str
    provider: str
    executor_type: str
    version: str
    status: ModelState
    capabilities_supported: List[str]
    capabilities_forbidden: List[str]
    hardware_requirements: Dict[str, Any]
    memory_requirements: Dict[str, Any]
    context_window: int
    quantization: str
    artifact_uri: str
    artifact_sha256: str
    runtime_interface: str
    max_concurrency: int
    max_runtime: int
    max_input_size: int
    max_output_size: int
    network_policy: str
    evidence_policy: str

@dataclass
class ModelCapabilityBinding:
    model_id: str
    capability_id: str
    authorization: str
    quality_profile: str
    risk_limit: str
    preferred: bool
    fallback: bool
    reason: str

@dataclass
class HardwareProfile:
    cpu: str
    cores: Any
    ram: Any
    gpu_present: Any
    gpu_vendor: str
    gpu_memory: Any
    storage_available: Any
    os: str
    python_version: str

@dataclass
class ModelPerformanceProfile:
    model_id: str
    capability_id: str
    executions: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    average_latency: float = 0.0
    p95_latency: float = 0.0
    average_output_size: float = 0.0
    evaluation_score: float = 0.0
    last_evaluated_at: Optional[datetime] = None

@dataclass
class EvaluationRecord:
    evaluation_id: str
    model_id: str
    capability_id: str
    execution_id: str
    score: float
    validation_method: str
    validator: str
    created_at: datetime
    evidence_ref: str
