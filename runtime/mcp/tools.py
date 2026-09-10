"""
Real tool implementations for the MCP Gateway.

Each tool function receives validated input and returns output data.
These are the actual implementations backing the ToolDefinitions in the registry.
"""
import os
import json
import logging
import subprocess
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
    repo_path = input_data.get("repo_path", "")
    file_path = input_data.get("file_path", "")
    if not file_path:
        raise ToolImplementationError("Missing required field: file_path")

    full_path = os.path.join(repo_path, file_path) if repo_path else file_path
    resolved = os.path.realpath(full_path)

    workspace = context.get("workspace_path", "")
    if workspace and not resolved.startswith(os.path.realpath(workspace)):
        raise ToolImplementationError(f"Path {full_path} is outside workspace boundary")

    if not os.path.isfile(resolved):
        raise ToolImplementationError(f"File not found: {full_path}")

    max_size = context.get("max_output_size", 10 * 1024 * 1024)
    size = os.path.getsize(resolved)
    if size > max_size:
        raise ToolImplementationError(f"File size {size} exceeds limit {max_size}")

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        raise ToolImplementationError(f"Failed to read file: {e}")

    return {
        "content": content,
        "size": size,
        "path": full_path,
        "encoding": "utf-8",
    }


def repository_search(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Search repository content using grep."""
    repo_path = input_data.get("repo_path", ".")
    pattern = input_data.get("pattern", "")
    if not pattern:
        raise ToolImplementationError("Missing required field: pattern")

    workspace = context.get("workspace_path", "")
    resolved = os.path.realpath(repo_path)
    if workspace and not resolved.startswith(os.path.realpath(workspace)):
        raise ToolImplementationError(f"Path {repo_path} is outside workspace boundary")

    if not os.path.isdir(resolved):
        raise ToolImplementationError(f"Directory not found: {repo_path}")

    try:
        result = subprocess.run(
            ["grep", "-rnI", "--include=*.py", "-l", pattern, resolved],
            capture_output=True, text=True, timeout=30
        )
        matches = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except subprocess.TimeoutExpired:
        raise ToolImplementationError("Search timed out")
    except FileNotFoundError:
        matches = []

    return {
        "pattern": pattern,
        "repo_path": repo_path,
        "matches": matches,
        "count": len(matches),
    }


def fabric_read(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Read resource state from Repository Fabric."""
    resource_id = input_data.get("resource_id", "")
    if not resource_id:
        raise ToolImplementationError("Missing required field: resource_id")

    fabric_dir = context.get("fabric_data_dir", "")
    if not fabric_dir:
        raise ToolImplementationError("Fabric data directory not configured")

    resource_file = os.path.join(fabric_dir, f"{resource_id}.json")
    if not os.path.exists(resource_file):
        return {"resource_id": resource_id, "found": False}

    try:
        with open(resource_file, "r") as f:
            data = json.load(f)
    except Exception as e:
        raise ToolImplementationError(f"Failed to read fabric resource: {e}")

    return {"resource_id": resource_id, "found": True, "resource": data}


def fabric_register(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Register a new resource in Repository Fabric."""
    import uuid as _uuid
    import hashlib

    resource_id = input_data.get("resource_id", "")
    resource_type = input_data.get("resource_type", "")
    metadata = input_data.get("metadata", {})

    if not resource_id or not resource_type:
        raise ToolImplementationError("Missing required fields: resource_id, resource_type")

    fabric_dir = context.get("fabric_data_dir", "")
    if not fabric_dir:
        raise ToolImplementationError("Fabric data directory not configured")

    os.makedirs(fabric_dir, exist_ok=True)

    provenance_id = f"prov-{_uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    resource_data = {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "state": "ACTIVE",
        "provenance_id": provenance_id,
        "metadata": metadata,
        "registered_at": now,
        "registered_by": context.get("caller_id", "mcp_gateway"),
    }

    resource_file = os.path.join(fabric_dir, f"{resource_id}.json")
    with open(resource_file, "w") as f:
        json.dump(resource_data, f, indent=2)

    return {
        "resource_id": resource_id,
        "provenance_id": provenance_id,
        "state": "ACTIVE",
        "registered_at": now,
    }


# Map tool_id -> implementation function
TOOL_IMPLEMENTATIONS = {
    "filesystem.inspect": filesystem_inspect,
    "repository.read": repository_read,
    "repository.search": repository_search,
    "fabric.read": fabric_read,
    "fabric.register": fabric_register,
}
