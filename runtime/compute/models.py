from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime

class RemoteSessionState(Enum):
    DISCONNECTED = "DISCONNECTED"
    AUTH_PENDING = "AUTH_PENDING"
    CONNECTING = "CONNECTING"
    PROVISIONING = "PROVISIONING"
    CONNECTED = "CONNECTED"
    AUDITING = "AUDITING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"

class TrustLevel(Enum):
    UNKNOWN = "UNKNOWN"
    DECLARED = "DECLARED"
    OBSERVED = "OBSERVED"

class ExecutionClassification(Enum):
    TEST = "TEST"
    MOCK = "MOCK"
    EMULATED = "EMULATED"
    REAL_REMOTE = "REAL_REMOTE"

@dataclass(frozen=True)
class TrustProfile:
    cpu: TrustLevel = TrustLevel.UNKNOWN
    cores: TrustLevel = TrustLevel.UNKNOWN
    ram: TrustLevel = TrustLevel.UNKNOWN
    gpu_present: TrustLevel = TrustLevel.UNKNOWN
    gpu_vendor: TrustLevel = TrustLevel.UNKNOWN
    gpu_model: TrustLevel = TrustLevel.UNKNOWN
    vram: TrustLevel = TrustLevel.UNKNOWN
    accelerator_type: TrustLevel = TrustLevel.UNKNOWN
    runtime: TrustLevel = TrustLevel.UNKNOWN
    python_version: TrustLevel = TrustLevel.UNKNOWN

@dataclass
class RemoteComputeResourceProfile:
    cpu: Optional[str] = None
    cores: Optional[int] = None
    ram: Optional[int] = None  # in MB
    gpu_present: Optional[bool] = None
    gpu_vendor: Optional[str] = None
    gpu_model: Optional[str] = None
    vram: Optional[int] = None # in MB
    accelerator_type: Optional[str] = None
    runtime: Optional[str] = None
    python_version: Optional[str] = None
    observed_at: Optional[datetime] = None
    trust_levels: TrustProfile = field(default_factory=TrustProfile)

@dataclass
class RemoteComputeLease:
    lease_id: str
    session_id: str
    issued_at: datetime
    expires_at: datetime
    max_runtime: int # seconds
    renewable: bool
    renewal_policy: Optional[str] = None

@dataclass
class RemoteComputeArtifact:
    artifact_id: str
    job_id: str
    artifact_type: str
    reference: str  # URI or ref
    sha256: str
    size: int
    created_at: datetime
    source_session: str

@dataclass
class RemoteComputeJob:
    job_id: str
    session_id: str
    work_package_ref: str
    created_at: datetime
    status: str
    deadline: datetime
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    network_policy: str = "DENY_ALL"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    artifact_refs: List[str] = field(default_factory=list)
    evidence_ref: Optional[str] = None

@dataclass
class RemoteComputeSession:
    session_id: str
    provider_id: str
    state: RemoteSessionState
    classification: ExecutionClassification
    lease: Optional[RemoteComputeLease] = None
    profile: Optional[RemoteComputeResourceProfile] = None
