import enum
from dataclasses import dataclass, field
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

class CapabilityRegistry:
    """Registry holding capability definitions."""
    
    def __init__(self):
        self._capabilities: Dict[str, CapabilityDefinition] = {}
        self._register_initial()

    def _register_initial(self):
        caps = [
            ("document.classify", "Document Classify", "Classifies a document.", True, ExecutorType.LOCAL_MODEL),
            ("filesystem.inspect", "Filesystem Inspect", "Inspects file metadata.", False, ExecutorType.DETERMINISTIC),
            ("filesystem.list", "Filesystem List", "Lists directory contents.", False, ExecutorType.DETERMINISTIC),
            ("filesystem.hash", "Filesystem Hash", "Hashes file contents.", False, ExecutorType.DETERMINISTIC),
            ("repository.inspect", "Repository Inspect", "Inspects repo metadata.", False, ExecutorType.DETERMINISTIC),
            ("repository.search", "Repository Search", "Searches repo.", False, ExecutorType.DETERMINISTIC),
            ("repository.diff", "Repository Diff", "Diffs repo.", False, ExecutorType.DETERMINISTIC),
            ("artifact.metadata", "Artifact Metadata", "Gets artifact metadata.", False, ExecutorType.DETERMINISTIC),
            ("schema.validate", "Schema Validate", "Validates JSON schemas.", False, ExecutorType.DETERMINISTIC),
        ]
        for cap_id, name, desc, inf_req, pref_exec in caps:
            self.register(CapabilityDefinition(
                capability_id=cap_id,
                name=name,
                description=desc,
                version="1.0.0",
                risk_level="low",
                inference_required=inf_req,
                deterministic_allowed=True,
                network_policy="disabled",
                filesystem_policy="read_only",
                required_tools=[cap_id],
                max_runtime=60,
                max_output=1024 * 1024,
                evidence_required=True,
                preferred_executor=pref_exec,
                fallback_executor=None,
                enabled=True
            ))

    def register(self, cap: CapabilityDefinition):
        self._capabilities[cap.capability_id] = cap

    def get(self, capability_id: str) -> Optional[CapabilityDefinition]:
        return self._capabilities.get(capability_id)
        
    def list_all(self) -> List[CapabilityDefinition]:
        return list(self._capabilities.values())
