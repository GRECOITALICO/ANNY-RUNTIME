import uuid
from typing import NewType

RuntimeId = NewType('RuntimeId', str)
InstallationId = NewType('InstallationId', str)
SessionId = NewType('SessionId', str)
AnnyInstanceId = NewType('AnnyInstanceId', str)
TenantId = NewType('TenantId', str)
ActorId = NewType('ActorId', str)
OperationId = NewType('OperationId', str)
ExecutionId = NewType('ExecutionId', str)
WorkspaceId = NewType('WorkspaceId', str)
ProcessId = NewType('ProcessId', str)
TraceId = NewType('TraceId', str)
Generation = NewType('Generation', int)

def generate_id(prefix: str) -> str:
    """
    Generate a unique identifier with a given prefix.
    Uses UUID4 hex to ensure global uniqueness.
    
    Example: generate_id("RT") -> "RT-a1b2c3d4..."
    """
    return f"{prefix}-{uuid.uuid4().hex}"
