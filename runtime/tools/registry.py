from dataclasses import dataclass
from typing import Callable, Optional, Dict, List, Tuple
from runtime.capability.gate import Capability, CapabilityGate

@dataclass
class ToolManifest:
    name: str
    version: str
    input_schema: dict
    output_schema: dict
    required_capabilities: List[Capability]
    side_effects: List[str]
    execution_domain: str
    workspace_required: bool
    network_required: bool

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tuple[ToolManifest, Callable]] = {}

    def register(self, manifest: ToolManifest, handler: Callable) -> None:
        """Registers a tool manifest and handler."""
        self._tools[manifest.name] = (manifest, handler)

    def get(self, name: str) -> Optional[Tuple[ToolManifest, Callable]]:
        """Retrieves a registered tool."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolManifest]:
        """Lists all registered tool manifests."""
        return [manifest for manifest, _ in self._tools.values()]

    def validate_capabilities(
        self,
        name: str,
        actor_id: str,
        gate: CapabilityGate,
        session_id: str,
        workspace_id: str,
        runtime_generation: int,
        current_generation: int
    ) -> bool:
        """Validates all required capabilities for a tool."""
        tool_entry = self.get(name)
        if not tool_entry:
            return False
        
        manifest = tool_entry[0]
        for cap in manifest.required_capabilities:
            decision = gate.check(
                session_id=session_id,
                actor_id=actor_id,
                capability=cap,
                workspace_id=workspace_id,
                runtime_generation=runtime_generation,
                current_generation=current_generation
            )
            if not decision.allowed:
                return False
        return True
