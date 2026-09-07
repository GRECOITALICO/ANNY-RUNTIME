from dataclasses import dataclass
from typing import Callable, Any, Dict, Optional, Tuple, List

from runtime.security.execution_context import ExecutionContext
from runtime.security.authority_validator import SecurityViolationError

@dataclass
class ToolManifest:
    name: str
    required_capabilities: List[str]
    workspace_required: bool
    effect_class: str

class SecureToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tuple[ToolManifest, Callable]] = {}

    def register(self, manifest: ToolManifest, handler: Callable) -> None:
        self._tools[manifest.name] = (manifest, handler)

    def get(self, name: str) -> Optional[Tuple[ToolManifest, Callable]]:
        return self._tools.get(name)

    def execute(self, context: ExecutionContext, tool_name: str, args: dict) -> Any:
        tool = self.get(tool_name)
        if not tool:
            raise SecurityViolationError(f"Tool '{tool_name}' is not registered.")
            
        manifest, handler = tool
        
        for cap in manifest.required_capabilities:
            if cap not in context.capabilities:
                raise SecurityViolationError(f"Missing required capability: {cap}")
                
        if manifest.workspace_required and not context.workspace_id:
            raise SecurityViolationError(f"Tool '{tool_name}' requires a workspace.")
            
        return handler(context, **args)
