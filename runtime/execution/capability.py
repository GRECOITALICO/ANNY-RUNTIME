import enum
from dataclasses import dataclass
from typing import List, Dict, Optional


class ExecutorType(str, enum.Enum):
    DETERMINISTIC = "DETERMINISTIC"
    LOCAL_MODEL = "LOCAL_MODEL"
    REMOTE_MODEL = "REMOTE_MODEL"


@dataclass
class CapabilityDefinition:
    capability_id: str
    name: str
    description: str
    version: str
    risk_level: str
    inference_required: bool
    deterministic_allowed: bool
    network_policy: str
    filesystem_policy: str
    required_tools: List[str]
    max_runtime: int
    max_output: int
    evidence_required: bool
    preferred_executor: ExecutorType
    fallback_executor: Optional[ExecutorType]
    enabled: bool
    family: str = "unknown"
    side_effect: str = "read"
    cacheable: bool = True
    hermetic: bool = True


class CapabilityRegistry:
    """Registry holding governed capability definitions."""

    def __init__(self):
        self._capabilities: Dict[str, CapabilityDefinition] = {}
        self._register_initial()

    def _register_initial(self):
        caps = [
            ("document.classify", "Document Classify", "Classifies a document.", True, ExecutorType.LOCAL_MODEL, "document", "read", False, False),
            ("filesystem.inspect", "Filesystem Inspect", "Inspects file metadata.", False, ExecutorType.DETERMINISTIC, "filesystem", "read", True, True),
            ("filesystem.list", "Filesystem List", "Lists directory contents.", False, ExecutorType.DETERMINISTIC, "filesystem", "read", True, True),
            ("filesystem.hash", "Filesystem Hash", "Hashes file contents.", False, ExecutorType.DETERMINISTIC, "integrity", "read", True, True),
            ("repository.inspect", "Repository Inspect", "Inspects repository metadata.", False, ExecutorType.DETERMINISTIC, "repository", "read", True, True),
            ("repository.search", "Repository Search", "Searches a local repository.", False, ExecutorType.DETERMINISTIC, "repository", "read", True, True),
            ("repository.read", "Repository Read", "Reads repository state and metadata.", False, ExecutorType.DETERMINISTIC, "repository", "read", True, True),
            ("repository.diff", "Repository Diff", "Computes a local repository diff.", False, ExecutorType.DETERMINISTIC, "repository", "read", True, True),
            ("artifact.metadata", "Artifact Metadata", "Gets local artifact metadata.", False, ExecutorType.DETERMINISTIC, "artifact", "read", True, True),
            ("schema.validate", "Schema Validate", "Validates structured data against an explicit schema contract.", False, ExecutorType.DETERMINISTIC, "validation", "read", True, True),
            ("fabric.read", "Fabric Read", "Reads operational fabric state.", False, ExecutorType.DETERMINISTIC, "fabric", "read", False, False),
            ("fabric.register", "Fabric Register", "Registers a fabric entry.", False, ExecutorType.DETERMINISTIC, "fabric", "write", False, False),
        ]
        for cap_id, name, desc, inf_req, pref_exec, family, side_effect, cacheable, hermetic in caps:
            self.register(CapabilityDefinition(
                capability_id=cap_id,
                name=name,
                description=desc,
                version="1.1.0",
                risk_level="low" if side_effect == "read" else "high",
                inference_required=inf_req,
                deterministic_allowed=pref_exec == ExecutorType.DETERMINISTIC,
                network_policy="disabled",
                filesystem_policy="read_only" if side_effect == "read" else "workspace_only",
                required_tools=[cap_id],
                max_runtime=60,
                max_output=1024 * 1024,
                evidence_required=True,
                preferred_executor=pref_exec,
                fallback_executor=None,
                enabled=side_effect == "read",
                family=family,
                side_effect=side_effect,
                cacheable=cacheable,
                hermetic=hermetic,
            ))

    def register(self, cap: CapabilityDefinition):
        self._capabilities[cap.capability_id] = cap

    def get(self, capability_id: str) -> Optional[CapabilityDefinition]:
        return self._capabilities.get(capability_id)

    def list_all(self) -> List[CapabilityDefinition]:
        return list(self._capabilities.values())
