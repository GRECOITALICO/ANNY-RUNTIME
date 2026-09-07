from dataclasses import dataclass
from typing import Any, Dict
import time

@dataclass
class ToolInvocation:
    name: str
    args: Dict[str, Any]
    session_id: str
    actor_id: str
    tenant_id: str
    workspace_id: str

@dataclass
class ToolResult:
    success: bool
    data: Any
    error: str
    execution_time_ms: int

class ExecutionOrchestrator:
    def __init__(
        self,
        tool_registry: Any,
        capability_gate: Any,
        workspace_manager: Any,
        process_manager: Any,
        session_manager: Any,
        generation: int
    ) -> None:
        self.tool_registry = tool_registry
        self.capability_gate = capability_gate
        self.workspace_manager = workspace_manager
        self.process_manager = process_manager
        self.session_manager = session_manager
        self.generation = generation

    def execute(self, tool_invocation: ToolInvocation) -> ToolResult:
        start_time = time.time()
        
        # 1. Validate session
        if self.session_manager and hasattr(self.session_manager, 'validate'):
            if not self.session_manager.validate(tool_invocation.session_id):
                return ToolResult(False, None, "Invalid session", 0)
        
        # 2. Validate capabilities for tool
        if not self.tool_registry.validate_capabilities(
            name=tool_invocation.name,
            actor_id=tool_invocation.actor_id,
            gate=self.capability_gate,
            session_id=tool_invocation.session_id,
            workspace_id=tool_invocation.workspace_id,
            runtime_generation=self.generation,
            current_generation=self.generation
        ):
            return ToolResult(False, None, "Capabilities denied for tool", 0)
            
        # 3. Validate workspace access
        if not self.workspace_manager.validate_access(
            workspace_id=tool_invocation.workspace_id,
            tenant_id=tool_invocation.tenant_id,
            actor_id=tool_invocation.actor_id
        ):
            return ToolResult(False, None, "Workspace access denied", 0)
            
        # 4. Validate generation (fence stale)
        if self.process_manager.generation != self.generation:
            return ToolResult(False, None, "Stale execution generation", 0)
            
        # 5. Call tool handler
        tool_entry = self.tool_registry.get(tool_invocation.name)
        if not tool_entry:
            return ToolResult(False, None, "Tool not found", 0)
            
        manifest, handler = tool_entry
        try:
            result_data = handler(**tool_invocation.args)
            
            # 6. Generate receipt (stubbed)
            
            # 7. Return result
            duration = int((time.time() - start_time) * 1000)
            return ToolResult(True, result_data, "", duration)
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            return ToolResult(False, None, str(e), duration)
