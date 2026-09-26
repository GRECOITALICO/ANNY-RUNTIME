"""
Real tool implementations for the MCP Gateway.

Each tool function receives validated input and returns output data.
These are the actual implementations backing the ToolDefinitions in the registry.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ToolImplementationError(Exception):
    """Raised when a tool implementation fails."""
    pass


def filesystem_inspect(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Inspect file metadata: existence, size, timestamps, permissions."""
    path = input_data.get("path")
    if not path:
        raise ToolImplementationError("Missing required field: path")

    # Security: resolve and validate path is within allowed workspace
    workspace = context.get("workspace_path", "")
    resolved = os.path.realpath(path)
    if workspace and not resolved.startswith(os.path.realpath(workspace)):
        raise ToolImplementationError(f"Path {path} is outside workspace boundary")

    if not os.path.exists(resolved):
        return {"exists": False, "path": path}

    stat = os.stat(resolved)
    return {
        "exists": True,
        "path": path,
        "resolved_path": resolved,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
        "is_file": os.path.isfile(resolved),
        "is_dir": os.path.isdir(resolved),
        "permissions": oct(stat.st_mode)[-3:],
    }


def _safe_workspace_path(context: Dict[str, Any], relative_path: str) -> str:
    """Resolve a path under the Runtime-provided workspace."""
    from pathlib import Path
    workspace = context.get("workspace_path", "")
    if not workspace:
        raise ToolImplementationError("Workspace is not bound")
    root = Path(workspace).resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ToolImplementationError("Path outside workspace boundary") from exc
    return str(target)


def repository_inspect(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Inspect a checked-out local repository."""
    path = _safe_workspace_path(context, input_data.get("path", "."))
    import subprocess
    if not os.path.exists(path):
        return {"path": path, "exists": False, "is_git_repository": False, "head": None}
    git_dir = os.path.join(path, ".git")
    is_git = os.path.exists(git_dir)
    head = None
    if is_git:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            head = result.stdout.strip()
    return {"path": path, "exists": True, "is_git_repository": is_git, "head": head}


def repository_read(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Read a file from the checked-out Runtime workspace."""
    path = input_data.get("file_path", "")
    if not path:
        raise ToolImplementationError("Missing required field: file_path")
    safe = _safe_workspace_path(context, path)
    if not os.path.isfile(safe):
        raise ToolImplementationError("Repository file not found")
    with open(safe, "r", encoding="utf-8") as handle:
        content = handle.read()
    return {"content": content, "size": len(content.encode("utf-8")), "path": path, "encoding": "utf-8"}


def repository_search(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Search checked-out repository content without requiring GitHub."""
    repo_path = _safe_workspace_path(context, input_data.get("repo_path", "."))
    pattern = input_data.get("pattern", "")
    if not pattern:
        raise ToolImplementationError("Missing required field: pattern")
    import subprocess
    result = subprocess.run(
        ["git", "-C", repo_path, "grep", "-n", "-I", "--", pattern],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    matches = sorted(line for line in result.stdout.splitlines() if line)
    return {
        "repo_path": repo_path,
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
        "exit_code": result.returncode,
    }


def fabric_read(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Read resource state from Repository Fabric."""
    fabric_client = context.get("fabric_client")
    if not fabric_client:
        raise ToolImplementationError("FabricClient not provided in context")
        
    resource_id = input_data.get("resource_id", "")
    if not resource_id:
        raise ToolImplementationError("Missing required field: resource_id")

    try:
        data = fabric_client.get_resource(resource_id)
        if not data:
            return {"resource_id": resource_id, "found": False}
    except Exception as e:
        # Check if it's a "not found" error vs a network error
        if hasattr(e, 'error_code') and e.error_code == "FABRIC_NOT_FOUND":
            return {"resource_id": resource_id, "found": False}
        raise ToolImplementationError(f"Failed to read fabric resource: {e}")

    return {"resource_id": resource_id, "found": True, "resource": data}


def fabric_register(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Register a new resource in Repository Fabric."""
    fabric_client = context.get("fabric_client")
    if not fabric_client:
        raise ToolImplementationError("FabricClient not provided in context")
        
    resource_id = input_data.get("resource_id", "")
    resource_type = input_data.get("resource_type", "")
    metadata = input_data.get("metadata", {})

    if not resource_id or not resource_type:
        raise ToolImplementationError("Missing required fields: resource_id, resource_type")

    try:
        res = fabric_client.register_resource(
            provider="mcp",
            external_id=resource_id,
            name=metadata.get("name", resource_id),
            r_type=resource_type,
            source_revision=metadata.get("source_revision", "HEAD"),
            observed_by=context.get("caller_id", "mcp_gateway")
        )
    except Exception as e:
        raise ToolImplementationError(f"Failed to register fabric resource: {e}")

    return {
        "resource_id": resource_id,
        "provenance_id": res.get("provenance_id", "unknown"),
        "state": "ACTIVE",
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }


# Map tool_id -> implementation function
TOOL_IMPLEMENTATIONS = {
    "filesystem.inspect": filesystem_inspect,
    "repository.inspect": repository_inspect,
    "repository.read": repository_read,
    "repository.search": repository_search,
    "fabric.read": fabric_read,
    "fabric.register": fabric_register,
}
