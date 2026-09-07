import os
import json
from runtime.capability.gate import Capability
from runtime.tools.registry import ToolManifest, ToolRegistry

def register_builtins(registry: ToolRegistry, filesystem, process, shell, git, workspace):
    # Workspace
    registry.register(
        ToolManifest(
            name="workspace.create", version="1.0",
            input_schema={"repository": "str", "source_revision": "str"}, output_schema={"workspace_id": "str"},
            required_capabilities=[Capability.WORKSPACE_CREATE], side_effects=["Creates local directory"],
            execution_domain="LOCAL", workspace_required=False, network_required=False
        ),
        lambda ctx, args: {"workspace_id": workspace.create(ctx.tenant_id, [ctx.actor_id], args["repository"], args["source_revision"]).workspace_id}
    )
    
    registry.register(
        ToolManifest(
            name="workspace.status", version="1.0",
            input_schema={"workspace_id": "str"}, output_schema={"status": "dict"},
            required_capabilities=[], side_effects=[],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: {"status": workspace.status(args["workspace_id"]).__dict__}
    )

    # Filesystem
    registry.register(
        ToolManifest(
            name="fs.read", version="1.0",
            input_schema={"path": "str"}, output_schema={"content": "str"},
            required_capabilities=[Capability.FILE_READ], side_effects=[],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: {"content": filesystem.read(ctx.workspace_id, args["path"], ctx.tenant_id, ctx.actor_id)}
    )

    registry.register(
        ToolManifest(
            name="fs.write", version="1.0",
            input_schema={"path": "str", "content": "str"}, output_schema={"success": "bool"},
            required_capabilities=[Capability.FILE_WRITE], side_effects=["Modifies file"],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: {"success": filesystem.write(ctx.workspace_id, args["path"], args["content"], ctx.tenant_id, ctx.actor_id)}
    )

    registry.register(
        ToolManifest(
            name="fs.patch", version="1.0",
            input_schema={"path": "str", "search": "str", "replace": "str"}, output_schema={"success": "bool"},
            required_capabilities=[Capability.FILE_READ, Capability.FILE_WRITE], side_effects=["Modifies file"],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: {"success": filesystem.patch(ctx.workspace_id, args["path"], args["search"], args["replace"], ctx.tenant_id, ctx.actor_id)}
    )

    # Shell
    registry.register(
        ToolManifest(
            name="shell.exec", version="1.0",
            input_schema={"command": "str"}, output_schema={"exit_code": "int", "stdout": "str", "stderr": "str"},
            required_capabilities=[Capability.PROCESS_EXECUTION], side_effects=["Executes arbitrary commands"],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: shell.execute(args["command"], ctx.workspace_id, ctx.session_id, ctx.actor_id, ctx.tenant_id).__dict__
    )

    # Git
    registry.register(
        ToolManifest(
            name="git.status", version="1.0",
            input_schema={}, output_schema={"status": "dict"},
            required_capabilities=[Capability.GIT_READ], side_effects=[],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: {"status": git.status(ctx.workspace_id, ctx.session_id, ctx.actor_id, ctx.tenant_id)}
    )

    registry.register(
        ToolManifest(
            name="git.diff", version="1.0",
            input_schema={"ref": "str"}, output_schema={"diff": "str"},
            required_capabilities=[Capability.GIT_READ], side_effects=[],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: {"diff": git.diff(ctx.workspace_id, ctx.session_id, ctx.actor_id, ctx.tenant_id, args.get("ref"))}
    )

    registry.register(
        ToolManifest(
            name="git.commit", version="1.0",
            input_schema={"message": "str"}, output_schema={"commit_sha": "str"},
            required_capabilities=[Capability.GIT_WRITE], side_effects=["Creates a commit"],
            execution_domain="LOCAL", workspace_required=True, network_required=False
        ),
        lambda ctx, args: git.commit(ctx.workspace_id, ctx.session_id, ctx.actor_id, ctx.tenant_id, args["message"])
    )
