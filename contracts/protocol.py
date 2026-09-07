import dataclasses
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = '0.1'

@dataclasses.dataclass
class RuntimeHello:
    runtime_id: str
    protocol_version: str
    capabilities: List[str]

@dataclasses.dataclass
class RuntimeManifest:
    runtime_id: str
    tools: List[str]
    platform: str
    version: str

@dataclasses.dataclass
class SessionAttach:
    session_id: str
    principal: str
    tenant_id: str
    anny_instance_id: str
    scope: str

@dataclasses.dataclass
class SessionDetach:
    session_id: str
    reason: str

@dataclasses.dataclass
class CapabilityRequest:
    session_id: str
    actor_id: str
    capability: str
    resource: str

@dataclasses.dataclass
class ToolInvocation:
    operation_id: str
    execution_id: str
    session_id: str
    actor_id: str
    workspace_id: str
    tool_name: str
    parameters: Dict[str, Any]
    trace_id: str

@dataclasses.dataclass
class ToolResult:
    execution_id: str
    status: str
    output: str
    error: Optional[str]
    exit_code: int
    duration_ms: int

@dataclasses.dataclass
class ExecutionStarted:
    execution_id: str
    operation_id: str
    tool_name: str
    workspace_id: str
    started_at: str

@dataclasses.dataclass
class ExecutionStatus:
    execution_id: str
    state: str
    progress: float

@dataclasses.dataclass
class ExecutionFinished:
    execution_id: str
    status: str
    finished_at: str
    receipt: Dict[str, Any]

@dataclasses.dataclass
class WorkspaceRequest:
    workspace_id: str
    tenant_id: str
    action: str
    parameters: Dict[str, Any]

@dataclasses.dataclass
class WorkspaceResult:
    workspace_id: str
    status: str
    path: str
    error: Optional[str]

@dataclasses.dataclass
class RuntimeEvent:
    event_type: str
    timestamp: str
    payload: Dict[str, Any]

@dataclasses.dataclass
class RuntimeReceipt:
    operation_id: str
    execution_id: str
    runtime_id: str
    workspace_id: str
    actor_id: str
    tool: str
    status: str
    exit_code: int
    started_at: str
    finished_at: str
    runtime_generation: int

@dataclasses.dataclass
class RuntimeErrorMsg:
    code: str
    message: str
    details: Dict[str, Any]
    trace_id: str

# Alias to map to requested name while avoiding built-in shadowing
RuntimeError = RuntimeErrorMsg
