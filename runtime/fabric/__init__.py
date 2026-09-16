# runtime/fabric/__init__.py
"""
Repository Fabric client package.

The Repository Fabric is a dynamically-bound organizational control plane
for ANNY. The Fabric org and repo are resolved from RuntimeConfig at runtime.
They MUST NOT be hardcoded. Customer Zero uses GRECOITALICO/ANNY-OPERATIONAL
as its specific deployment configuration — this is not an architectural invariant.
Missing fabric_org or fabric_repo configuration yields BOOTSTRAP BLOCKED.
"""
