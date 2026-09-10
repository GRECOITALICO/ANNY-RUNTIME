"""
MCP Gateway for ANNY Runtime.

Phase 4: Tool Router with governed pipeline:
  validate → authorize → resolve tool → execute → validate result → emit evidence → return

Phase 5: Capability boundary enforcement.
Phase 6: Worker boundary enforcement (invocations only from WorkerManager).
"""
import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from runtime.mcp import (
    ToolDefinition, ToolRequest, ToolResult, ToolPolicy,
    ToolState, ToolInvocationStatus,
)
from runtime.mcp.registry import ToolRegistry
from runtime.mcp.tools import TOOL_IMPLEMENTATIONS, ToolImplementationError
from runtime.execution.capability import CapabilityRegistry

logger = logging.getLogger(__name__)


class MCPGatewayError(Exception):
    """Base error for MCP Gateway."""
    pass


class ToolNotFoundError(MCPGatewayError):
    pass


class AuthorizationDeniedError(MCPGatewayError):
    pass


class PolicyViolationError(MCPGatewayError):
    pass


class MCPGateway:
    """
    Minimal MCP Gateway that enforces:
    - Capability-based authorization (Phase 5)
    - Worker-only invocation boundary (Phase 6)
    - Policy enforcement per tool
    - Evidence emission per invocation
    """

    def __init__(self, tool_registry: ToolRegistry, capability_registry: CapabilityRegistry,
                 audit_manager=None, workspace_path: str = "", fabric_data_dir: str = ""):
        self.tool_registry = tool_registry
        self.capability_registry = capability_registry
        self.audit_manager = audit_manager
        self.workspace_path = workspace_path
        self.fabric_data_dir = fabric_data_dir

        # Track invocation counts per execution_id per tool_id
        self._invocation_counts: Dict[str, Dict[str, int]] = {}

        logger.info(f"MCPGateway initialized with {len(tool_registry.list_tools())} tools")

    def invoke(self, request: ToolRequest) -> ToolResult:
        """
        Main entry point. Full pipeline:
        validate → authorize → resolve → execute → validate result → emit evidence → return
        """
        started_at = datetime.now(timezone.utc)

        # Step 1: Validate request
        try:
            self._validate_request(request)
        except MCPGatewayError as e:
            return self._make_error_result(request, str(e), ToolInvocationStatus.FAILED, started_at)

        # Step 2: Authorize (capability boundary - Phase 5)
        try:
            self._authorize(request)
        except AuthorizationDeniedError as e:
            self._emit_audit("TOOL_AUTHORIZATION_DENIED", request, str(e))
            return self._make_error_result(request, str(e), ToolInvocationStatus.DENIED, started_at)
        except MCPGatewayError as e:
            return self._make_error_result(request, str(e), ToolInvocationStatus.FAILED, started_at)

        # Step 3: Resolve tool
        tool = self.tool_registry.get_tool(request.tool_id)
        if not tool or tool.state != ToolState.AVAILABLE:
            msg = f"Tool {request.tool_id} not available"
            return self._make_error_result(request, msg, ToolInvocationStatus.FAILED, started_at)

        # Step 4: Check policy
        try:
            self._enforce_policy(request, tool)
        except PolicyViolationError as e:
            self._emit_audit("TOOL_POLICY_VIOLATION", request, str(e))
            return self._make_error_result(request, str(e), ToolInvocationStatus.DENIED, started_at)

        # Step 5: Check deadline
        if datetime.now(timezone.utc) > request.deadline:
            return self._make_error_result(request, "Deadline exceeded before execution",
                                           ToolInvocationStatus.TIMED_OUT, started_at)

        # Step 6: Execute
        try:
            impl = TOOL_IMPLEMENTATIONS.get(request.tool_id)
            if not impl:
                raise ToolNotFoundError(f"No implementation for tool {request.tool_id}")

            context = {
                "workspace_path": self.workspace_path,
                "fabric_data_dir": self.fabric_data_dir,
                "max_output_size": 10 * 1024 * 1024,
                "caller_id": request.capability_id,
            }
            context.update(request.caller_context)

            output_data = impl(request.input_data, context)

        except ToolImplementationError as e:
            self._emit_audit("TOOL_EXECUTION_ERROR", request, str(e))
            return self._make_error_result(request, str(e), ToolInvocationStatus.FAILED, started_at)
        except Exception as e:
            logger.error(f"Tool {request.tool_id} crashed: {e}", exc_info=True)
            self._emit_audit("TOOL_CRASH", request, str(e))
            return self._make_error_result(request, f"Tool crash: {type(e).__name__}",
                                           ToolInvocationStatus.FAILED, started_at)

        # Step 7: Build result
        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        result = ToolResult(
            request_id=request.request_id,
            tool_id=request.tool_id,
            status=ToolInvocationStatus.SUCCEEDED,
            output_data=output_data,
            error_message=None,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

        # Step 8: Compute evidence
        result.evidence = {
            "request_id": request.request_id,
            "tool_id": request.tool_id,
            "capability_id": request.capability_id,
            "worker_id": request.worker_id,
            "execution_id": request.execution_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_ms": duration_ms,
            "result_hash": result.compute_evidence_hash(),
            "input_hash": hashlib.sha256(
                json.dumps(request.input_data, sort_keys=True, default=str).encode()
            ).hexdigest(),
        }

        # Step 9: Track invocation count
        exec_counts = self._invocation_counts.setdefault(request.execution_id, {})
        exec_counts[request.tool_id] = exec_counts.get(request.tool_id, 0) + 1

        # Step 10: Emit audit
        self._emit_audit("TOOL_INVOCATION_SUCCESS", request, json.dumps({
            "duration_ms": duration_ms,
            "result_hash": result.evidence["result_hash"],
        }))

        return result

    def _validate_request(self, request: ToolRequest):
        """Validate the request has all required fields."""
        if not request.tool_id:
            raise MCPGatewayError("Missing tool_id")
        if not request.capability_id:
            raise MCPGatewayError("Missing capability_id")
        if not request.worker_id:
            raise MCPGatewayError("Missing worker_id (Phase 6: worker boundary)")
        if not request.execution_id:
            raise MCPGatewayError("Missing execution_id")

    def _authorize(self, request: ToolRequest):
        """Phase 5: Capability boundary. Each tool requires an explicit capability."""
        tool = self.tool_registry.get_tool(request.tool_id)
        if not tool:
            raise ToolNotFoundError(f"Tool {request.tool_id} not registered")

        # The request's capability_id must match the tool's required_capability
        # or the policy must list the caller's capability as allowed
        policy = self.tool_registry.get_policy(request.tool_id)
        if policy:
            if request.capability_id not in policy.allowed_callers:
                raise AuthorizationDeniedError(
                    f"Capability {request.capability_id} is not authorized to invoke tool {request.tool_id}. "
                    f"Allowed: {policy.allowed_callers}"
                )
        else:
            # No policy = strict match to required_capability
            if request.capability_id != tool.required_capability:
                raise AuthorizationDeniedError(
                    f"Capability {request.capability_id} does not match required {tool.required_capability}"
                )

        # Verify capability exists in registry
        cap = self.capability_registry.get(request.capability_id)
        if not cap:
            raise AuthorizationDeniedError(f"Capability {request.capability_id} not found in registry")

        if not cap.enabled:
            raise AuthorizationDeniedError(f"Capability {request.capability_id} is disabled")

    def _enforce_policy(self, request: ToolRequest, tool: ToolDefinition):
        """Enforce tool policy limits."""
        policy = self.tool_registry.get_policy(request.tool_id)
        if not policy:
            return  # No policy = no additional limits

        # Check invocation count
        exec_counts = self._invocation_counts.get(request.execution_id, {})
        current = exec_counts.get(request.tool_id, 0)
        if current >= policy.max_invocations_per_execution:
            raise PolicyViolationError(
                f"Tool {request.tool_id} invocation limit exceeded: "
                f"{current}/{policy.max_invocations_per_execution}"
            )

        # Check input size
        input_size = len(json.dumps(request.input_data, default=str).encode())
        if input_size > policy.max_input_size:
            raise PolicyViolationError(
                f"Input size {input_size} exceeds policy limit {policy.max_input_size}"
            )

    def _make_error_result(self, request: ToolRequest, error: str,
                           status: ToolInvocationStatus, started_at: datetime) -> ToolResult:
        completed_at = datetime.now(timezone.utc)
        return ToolResult(
            request_id=request.request_id,
            tool_id=request.tool_id,
            status=status,
            output_data=None,
            error_message=error,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            evidence={"error": error, "status": status.value},
        )

    def _emit_audit(self, event_type: str, request: ToolRequest, details: str = ""):
        if not self.audit_manager:
            return
        try:
            self.audit_manager.record(
                "system", event_type, "MCPGateway", "SUCCESS",
                f"tool={request.tool_id} cap={request.capability_id} worker={request.worker_id} {details}"
            )
        except Exception as e:
            logger.warning(f"Audit emission failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Return gateway statistics for the Control Plane UI."""
        tools = self.tool_registry.list_tools()
        available = [t for t in tools if t.state == ToolState.AVAILABLE]
        total_invocations = sum(
            sum(counts.values()) for counts in self._invocation_counts.values()
        )
        return {
            "total_tools": len(tools),
            "available_tools": len(available),
            "total_invocations": total_invocations,
            "active_executions": len(self._invocation_counts),
        }
