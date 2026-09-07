from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from runtime.security.execution_context import ExecutionContext

class SecurityViolationError(Exception):
    pass

@dataclass
class ExecutionReceipt:
    execution_id: str
    tool_name: str
    status: str
    timestamp: datetime
    result: Any

class AuthorizedExecutionPipeline:
    """
    The singular Authorized Execution Pipeline for all physical effects in ANNY-RUNTIME.
    Enforces the strict 10-step security validation sequence.
    """
    
    def __init__(self, runtime_identity_service: Any, capability_gate: Any, tool_registry: Any):
        self.runtime_identity = runtime_identity_service
        self.capability_gate = capability_gate
        self.tool_registry = tool_registry

    def execute(self, context: ExecutionContext, tool_name: str, tool_args: Dict[str, Any]) -> ExecutionReceipt:
        now = datetime.utcnow()
        
        # 1. Context Integrity
        if not context:
            raise SecurityViolationError("ExecutionContext missing")
        if not context.execution_id or not context.session_id:
            raise SecurityViolationError("ExecutionContext structurally invalid")

        # 2. Tenant Binding
        # Will be validated against the active runtime tenant during enrollment,
        # but for pipeline we verify the context claims the correct tenant.
        if context.tenant_id != self.runtime_identity.get_tenant_id():
            raise SecurityViolationError(f"Tenant Binding failure: {context.tenant_id}")

        # 3. Session Validity & 5. Generation Fencing
        # Validates expiration, issuance, and generation match
        if not context.is_valid(now, self.runtime_identity.get_current_generation()):
            raise SecurityViolationError("Session expired or generation stale")

        # 4. Runtime Identity
        if context.runtime_id != self.runtime_identity.get_runtime_id():
            raise SecurityViolationError("Runtime Identity mismatch")

        # Retrieve Tool
        tool_entry = self.tool_registry.get(tool_name)
        if not tool_entry:
            raise SecurityViolationError(f"Tool {tool_name} not registered")
        manifest, handler = tool_entry

        # 6. Capability Grant & 8. Tool Policy
        # Verify the context holds all capabilities demanded by the tool manifest
        for required_cap in manifest.required_capabilities:
            # We check if the execution context carries the capability.
            # (In a full system, CapabilityGate might also dynamically check the AuthorizationStore,
            # but per directive, the context holds the authorized capabilities for this execution).
            if not context.has_capability(required_cap.name):
                raise SecurityViolationError(f"Capability Authorization failure: missing {required_cap.name}")

        # 7. Resource Ownership
        if manifest.workspace_required:
            if not context.workspace_id:
                raise SecurityViolationError("Resource Ownership failure: missing workspace_id in context")
            # The actual workspace manager will double check workspace existence,
            # but the pipeline enforces the declaration.

        # 9. Effect Execution
        try:
            # We pass the context to the handler so internal services (Filesystem, Shell)
            # can double check specific granular policies (e.g. read vs write paths)
            result = handler(context, **tool_args)
            status = "SUCCESS"
        except Exception as e:
            result = str(e)
            status = "FAILED"

        # 10. Receipt
        return ExecutionReceipt(
            execution_id=context.execution_id,
            tool_name=tool_name,
            status=status,
            timestamp=datetime.utcnow(),
            result=result
        )
