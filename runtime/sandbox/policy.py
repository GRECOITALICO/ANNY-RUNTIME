import enum
from dataclasses import dataclass, field
from typing import List, Optional

class IsolationLevel(enum.Enum):
    LEVEL_1 = "workspace_isolation"    # Filesystem namespace only
    LEVEL_2 = "restricted_process"     # Process restrictions + filesystem
    LEVEL_3 = "container_sandbox"      # Full container isolation

@dataclass
class SandboxPolicy:
    sandbox_id: str
    tenant_id: str
    actor_id: str
    workspace_id: str
    isolation_level: IsolationLevel = IsolationLevel.LEVEL_1
    filesystem_scope: List[str] = field(default_factory=list)  # Allowed paths
    process_scope: List[str] = field(default_factory=list)      # Allowed executables
    network_scope: str = "none"  # none | loopback | restricted | full
    resource_limits: dict = field(default_factory=lambda: {
        "max_memory_mb": 512,
        "max_cpu_seconds": 300,
        "max_disk_mb": 1024,
        "max_processes": 10,
    })
    generation: int = 1
    created_at: str = ""
    expires_at: str = ""

    def allows_path(self, path: str) -> bool:
        """Check if a filesystem path is within the allowed scope."""
        from pathlib import Path
        target = Path(path).resolve()
        for allowed in self.filesystem_scope:
            if str(target).startswith(str(Path(allowed).resolve())):
                return True
        return False

    def allows_executable(self, executable: str) -> bool:
        """Check if an executable is within the allowed process scope."""
        if not self.process_scope:  # Empty = allow all
            return True
        return executable in self.process_scope

    def allows_network(self) -> bool:
        return self.network_scope != "none"

    @classmethod
    def select_level(cls, operation_risk: str, trust: str) -> IsolationLevel:
        """Select appropriate isolation level based on risk and trust."""
        if operation_risk == "high" or trust == "untrusted":
            return IsolationLevel.LEVEL_3
        elif operation_risk == "medium" or trust == "limited":
            return IsolationLevel.LEVEL_2
        return IsolationLevel.LEVEL_1
