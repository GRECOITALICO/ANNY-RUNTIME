import enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

class CapabilityTier(str, enum.Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"

class DelegationDecision(str, enum.Enum):
    DELEGATE = "DELEGATE"
    SELF_EXECUTE = "SELF_EXECUTE"
    ESCALATE = "ESCALATE"
    DEFER = "DEFER"
    FAIL_CAPABILITY_INSUFFICIENT = "FAIL_CAPABILITY_INSUFFICIENT"

class ExecutionMode(str, enum.Enum):
    LOCAL_INFERENCE = "LOCAL_INFERENCE"
    EXTERNAL_INFERENCE = "EXTERNAL_INFERENCE"
    ANNY_SELF = "ANNY_SELF"
    DETERMINISTIC = "DETERMINISTIC"

class CertificationStatus(str, enum.Enum):
    CERTIFIED = "CERTIFIED"
    STALE = "STALE"
    REQUIRES_REBENCHMARK = "REQUIRES_REBENCHMARK"
    REVOKED = "REVOKED"
    VALID = "VALID"

class ResourceFit(str, enum.Enum):
    FIT = "FIT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"

@dataclass
class ImplementationProfile:
    implementation_id: str
    capability_ids: List[str]
    quality_profile: str
    resource_profile: Dict[str, Any]
    latency_profile: Dict[str, Any]
    cost_profile: Dict[str, Any]
    availability: bool
    certification: CertificationStatus
    artifact_references: List[str]
    adapter_references: List[str]
    base_model_revision: Optional[str] = None
    adapter_revision: Optional[str] = None
    runtime_version: Optional[str] = None
    hardware_profile: Optional[Dict[str, Any]] = None
    execution_class: str = "LOCAL_MODEL"

@dataclass
class ImplementationCandidate:
    implementation_id: str
    execution_class: str # DETERMINISTIC, LOCAL_MODEL, REMOTE_MODEL
    availability: bool
    quality: float
    confidence: float
    latency: float
    resource_fit: ResourceFit
    policy_fit: bool
    evidence_ref: Optional[str] = None

@dataclass
class BenchmarkCase:
    benchmark_id: str
    capability_id: str
    input: Any
    expected_output: Any
    grading_method: str
    difficulty: str
    dataset_partition: str
    version: str

@dataclass
class BenchmarkResult:
    benchmark_id: str
    implementation_id: str
    capability_id: str
    dataset_version: str
    score: float
    confidence: float
    latency: float
    resource_usage: Dict[str, Any]
    timestamp: datetime
    certification_status: CertificationStatus

@dataclass
class CapabilityAssessmentRequest:
    capability_id: str
    quality_required: float
    latency_requirement: Optional[float] = None
    resource_constraints: Optional[Dict[str, Any]] = None
    policy_constraints: Optional[Dict[str, Any]] = None

@dataclass
class CapabilityAssessmentResponse:
    decision: DelegationDecision
    selected_implementation: Optional[ImplementationCandidate]
    quality_score: float
    confidence: float
    tier: CapabilityTier
    reason: str
    assessment_provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkScorecard:
    """Phase 11: Capability certification scorecard."""
    scorecard_id: str
    capability_id: str
    implementation_id: str
    implementation_revision: str
    benchmark_version: str
    dataset_version: str
    score: float
    confidence: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    resource_usage: Dict[str, Any]
    certification_status: CertificationStatus
    hardware_profile: Optional[Dict[str, Any]] = None
    adapter_revision: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class HardwareProfile:
    """Phase 12: Hardware environment for benchmark reproducibility."""
    cpu_model: str
    cpu_cores: int
    ram_gb: float
    gpu_model: str
    vram_gb: float
    runtime_env: str
    os_info: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_model": self.cpu_model,
            "cpu_cores": self.cpu_cores,
            "ram_gb": self.ram_gb,
            "gpu_model": self.gpu_model,
            "vram_gb": self.vram_gb,
            "runtime_env": self.runtime_env,
            "os_info": self.os_info,
        }


@dataclass
class RepeatabilityStats:
    """Phase 25: Statistics across multiple benchmark runs."""
    run_count: int
    mean: float
    variance: float
    stddev: float
    best: float
    worst: float
    scores: List[float]


@dataclass
class FailureRecord:
    """Phase 26: Structured failure classification."""
    case_id: str
    capability_id: str
    failure_type: str  # benchmark_failure | implementation_failure | resource_failure | timeout | environmental | policy_denied | invalid_case | grading_failure
    details: str
    timestamp: Optional[datetime] = None

