from enum import Enum, auto
from dataclasses import dataclass
from typing import Set, Tuple

class Capability(Enum):
    FILE_READ = auto()
    FILE_WRITE = auto()
    PROCESS_EXECUTION = auto()
    PROCESS_CONTROL = auto()
    GIT_READ = auto()
    GIT_WRITE = auto()
    REMOTE_REPOSITORY_MUTATION = auto()
    SECRET_USE = auto()
    WORKSPACE_CREATE = auto()
    WORKSPACE_DELETE = auto()
    NETWORK_ACCESS = auto()

@dataclass
class CapabilityDecision:
    allowed: bool
    reason: str
    capability: Capability
    actor_id: str
    workspace_id: str

class CapabilityGate:
    def __init__(self) -> None:
        # Grants are stored as tuples of (actor_id, capability, workspace_id)
        self._grants: Set[Tuple[str, Capability, str]] = set()

    def grant(self, actor_id: str, capability: Capability, workspace_id: str = '*') -> None:
        """Grants a capability to an actor for a specific workspace (or all)."""
        self._grants.add((actor_id, capability, workspace_id))

    def revoke(self, actor_id: str, capability: Capability, workspace_id: str = '*') -> None:
        """Revokes a capability from an actor."""
        self._grants.discard((actor_id, capability, workspace_id))

    def check(
        self,
        session_id: str,
        actor_id: str,
        capability: Capability,
        workspace_id: str,
        runtime_generation: int,
        current_generation: int
    ) -> CapabilityDecision:
        """Checks if a capability is allowed."""
        if runtime_generation != current_generation:
            return CapabilityDecision(False, "Stale generation", capability, actor_id, workspace_id)

        if (actor_id, capability, workspace_id) in self._grants or \
           (actor_id, capability, '*') in self._grants:
            return CapabilityDecision(True, "Granted explicitly", capability, actor_id, workspace_id)

        return CapabilityDecision(False, "No explicit grant found", capability, actor_id, workspace_id)
