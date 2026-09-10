"""
MCP Gateway Domain Models for ANNY Runtime.

Defines: ToolDefinition, ToolRequest, ToolResult, ToolPolicy.
These are the minimal domain types needed for governed tool invocation.
"""
import enum
import uuid
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


class ToolState(str, enum.Enum):
    REGISTERED = "REGISTERED"
    AVAILABLE = "AVAILABLE"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class ToolInvocationStatus(str, enum.Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DENIED = "DENIED"
    TIMED_OUT = "TIMED_OUT"


@dataclass
class ToolDefinition:
    """Canonical definition of a tool available through the MCP Gateway."""
    tool_id: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_capability: str
    network_requirement: str  # "none", "local", "external"
    timeout: int  # seconds
    version: str
    state: ToolState = ToolState.REGISTERED
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolPolicy:
    """Policy governing a tool invocation."""
    policy_id: str
    tool_id: str
    max_invocations_per_execution: int
    max_input_size: int  # bytes
    max_output_size: int  # bytes
    require_evidence: bool
    allowed_callers: List[str]  # capability_ids that may invoke this tool
    network_policy: str  # "disabled", "local_only", "external_allowed"
    filesystem_policy: str  # "none", "read_only", "read_write"
    audit_level: str  # "none", "summary", "full"


@dataclass
class ToolRequest:
    """A request to invoke a tool through the MCP Gateway."""
    request_id: str
    tool_id: str
    capability_id: str
    worker_id: str
    execution_id: str
    input_data: Dict[str, Any]
    requested_at: datetime
    deadline: datetime
    caller_context: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def create(tool_id: str, capability_id: str, worker_id: str,
               execution_id: str, input_data: Dict[str, Any],
               deadline: datetime) -> 'ToolRequest':
        return ToolRequest(
            request_id=f"treq-{uuid.uuid4().hex[:12]}",
            tool_id=tool_id,
            capability_id=capability_id,
            worker_id=worker_id,
            execution_id=execution_id,
            input_data=input_data,
            requested_at=datetime.now(timezone.utc),
            deadline=deadline,
        )


@dataclass
class ToolResult:
    """Result of a tool invocation through the MCP Gateway."""
    request_id: str
    tool_id: str
    status: ToolInvocationStatus
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == ToolInvocationStatus.SUCCEEDED

    def compute_evidence_hash(self) -> str:
        """Compute a SHA-256 hash of the result for provenance."""
        import json
        payload = json.dumps({
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "status": self.status.value,
            "output_data": self.output_data,
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()
