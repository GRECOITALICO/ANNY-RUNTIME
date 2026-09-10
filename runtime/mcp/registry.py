"""
MCP Tool Registry for ANNY Runtime.

Independent of ModelRegistry. Registers tool definitions and policies.
Only tools with REAL implementations are registered.
"""
import logging
from typing import Dict, List, Optional

from runtime.mcp import ToolDefinition, ToolPolicy, ToolState

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools and their policies."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._policies: Dict[str, ToolPolicy] = {}
        self._register_initial_tools()

    def _register_initial_tools(self):
        """Register tools that have REAL implementations in the runtime."""

        initial_tools = [
            ToolDefinition(
                tool_id="filesystem.inspect",
                name="Filesystem Inspect",
                description="Inspects file metadata: size, timestamps, permissions.",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                output_schema={"type": "object", "properties": {"exists": {"type": "boolean"}, "size": {"type": "integer"}, "modified": {"type": "string"}}},
                required_capability="filesystem.inspect",
                network_requirement="none",
                timeout=30,
                version="1.0.0",
                state=ToolState.AVAILABLE,
                tags=["filesystem", "read"],
            ),
            ToolDefinition(
                tool_id="repository.read",
                name="Repository Read",
                description="Reads file content from a repository workspace.",
                input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "file_path": {"type": "string"}}, "required": ["repo_path", "file_path"]},
                output_schema={"type": "object", "properties": {"content": {"type": "string"}, "size": {"type": "integer"}}},
                required_capability="repository.inspect",
                network_requirement="none",
                timeout=30,
                version="1.0.0",
                state=ToolState.AVAILABLE,
                tags=["repository", "read"],
            ),
            ToolDefinition(
                tool_id="repository.search",
                name="Repository Search",
                description="Searches repository content using grep-like patterns.",
                input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["repo_path", "pattern"]},
                output_schema={"type": "object", "properties": {"matches": {"type": "array"}}},
                required_capability="repository.search",
                network_requirement="none",
                timeout=60,
                version="1.0.0",
                state=ToolState.AVAILABLE,
                tags=["repository", "search"],
            ),
            ToolDefinition(
                tool_id="fabric.read",
                name="Fabric Read",
                description="Reads resource state from Repository Fabric.",
                input_schema={"type": "object", "properties": {"resource_id": {"type": "string"}}, "required": ["resource_id"]},
                output_schema={"type": "object", "properties": {"resource": {"type": "object"}}},
                required_capability="fabric.read",
                network_requirement="local",
                timeout=30,
                version="1.0.0",
                state=ToolState.AVAILABLE,
                tags=["fabric", "read"],
            ),
            ToolDefinition(
                tool_id="fabric.register",
                name="Fabric Register",
                description="Registers a new resource in Repository Fabric.",
                input_schema={"type": "object", "properties": {"resource_id": {"type": "string"}, "resource_type": {"type": "string"}, "metadata": {"type": "object"}}, "required": ["resource_id", "resource_type"]},
                output_schema={"type": "object", "properties": {"provenance_id": {"type": "string"}, "state": {"type": "string"}}},
                required_capability="fabric.register",
                network_requirement="local",
                timeout=60,
                version="1.0.0",
                state=ToolState.AVAILABLE,
                tags=["fabric", "write"],
            ),
        ]

        initial_policies = [
            ToolPolicy(
                policy_id="pol-fs-inspect",
                tool_id="filesystem.inspect",
                max_invocations_per_execution=100,
                max_input_size=4096,
                max_output_size=1024 * 1024,
                require_evidence=True,
                allowed_callers=["filesystem.inspect", "filesystem.list", "filesystem.hash"],
                network_policy="disabled",
                filesystem_policy="read_only",
                audit_level="summary",
            ),
            ToolPolicy(
                policy_id="pol-repo-read",
                tool_id="repository.read",
                max_invocations_per_execution=50,
                max_input_size=4096,
                max_output_size=10 * 1024 * 1024,
                require_evidence=True,
                allowed_callers=["repository.inspect", "repository.search", "repository.diff"],
                network_policy="disabled",
                filesystem_policy="read_only",
                audit_level="summary",
            ),
            ToolPolicy(
                policy_id="pol-repo-search",
                tool_id="repository.search",
                max_invocations_per_execution=20,
                max_input_size=4096,
                max_output_size=10 * 1024 * 1024,
                require_evidence=True,
                allowed_callers=["repository.search"],
                network_policy="disabled",
                filesystem_policy="read_only",
                audit_level="summary",
            ),
            ToolPolicy(
                policy_id="pol-fabric-read",
                tool_id="fabric.read",
                max_invocations_per_execution=50,
                max_input_size=4096,
                max_output_size=1024 * 1024,
                require_evidence=True,
                allowed_callers=["fabric.read", "repository.inspect"],
                network_policy="local_only",
                filesystem_policy="none",
                audit_level="full",
            ),
            ToolPolicy(
                policy_id="pol-fabric-register",
                tool_id="fabric.register",
                max_invocations_per_execution=10,
                max_input_size=64 * 1024,
                max_output_size=1024 * 1024,
                require_evidence=True,
                allowed_callers=["fabric.register"],
                network_policy="local_only",
                filesystem_policy="none",
                audit_level="full",
            ),
        ]

        for tool in initial_tools:
            self.register_tool(tool)
        for policy in initial_policies:
            self.register_policy(policy)

        logger.info(f"ToolRegistry initialized with {len(self._tools)} tools and {len(self._policies)} policies")

    def register_tool(self, tool: ToolDefinition):
        self._tools[tool.tool_id] = tool

    def register_policy(self, policy: ToolPolicy):
        self._policies[policy.tool_id] = policy

    def get_tool(self, tool_id: str) -> Optional[ToolDefinition]:
        return self._tools.get(tool_id)

    def get_policy(self, tool_id: str) -> Optional[ToolPolicy]:
        return self._policies.get(tool_id)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def list_available(self) -> List[ToolDefinition]:
        return [t for t in self._tools.values() if t.state == ToolState.AVAILABLE]

    def disable_tool(self, tool_id: str):
        tool = self._tools.get(tool_id)
        if tool:
            tool.state = ToolState.DISABLED
            logger.info(f"Tool {tool_id} disabled")

    def enable_tool(self, tool_id: str):
        tool = self._tools.get(tool_id)
        if tool:
            tool.state = ToolState.AVAILABLE
            logger.info(f"Tool {tool_id} enabled")
