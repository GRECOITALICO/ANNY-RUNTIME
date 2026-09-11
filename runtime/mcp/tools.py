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


def repository_read(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Read file content from a repository workspace."""
    github_client = context.get("github_client")
    if not github_client:
        raise ToolImplementationError("GitHubClient not provided in context")
        
    repo_path = input_data.get("repo_path", "")
    file_path = input_data.get("file_path", "")
    if not file_path or not repo_path:
        raise ToolImplementationError("Missing required fields: repo_path, file_path")

    try:
        parts = repo_path.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]
    except Exception:
        raise ToolImplementationError(f"Invalid repo_path format. Expected owner/repo, got {repo_path}")

    try:
        content = github_client.get_file(owner, repo, file_path)
    except Exception as e:
        raise ToolImplementationError(f"Failed to read file from GitHub: {e}")

    return {
        "content": content,
        "size": len(content),
        "path": file_path,
        "encoding": "utf-8",
    }


def repository_search(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Search repository content."""
    github_client = context.get("github_client")
    if not github_client:
        raise ToolImplementationError("GitHubClient not provided in context")
        
    repo_path = input_data.get("repo_path", "")
    pattern = input_data.get("pattern", "")
    if not pattern or not repo_path:
        raise ToolImplementationError("Missing required fields: repo_path, pattern")

    try:
        parts = repo_path.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]
    except Exception:
        raise ToolImplementationError(f"Invalid repo_path format. Expected owner/repo, got {repo_path}")

    try:
        # Use canonical GitHubClient search API
        res = github_client.search_code(f"{owner}/{repo}", pattern)
        items = res.get("items", [])
        matches = [item["path"] for item in items]
    except Exception as e:
        raise ToolImplementationError(f"Failed to search GitHub: {e}")

    return {
        "pattern": pattern,
        "repo_path": repo_path,
        "matches": matches,
        "count": len(matches),
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
    "repository.read": repository_read,
    "repository.search": repository_search,
    "fabric.read": fabric_read,
    "fabric.register": fabric_register,
}
