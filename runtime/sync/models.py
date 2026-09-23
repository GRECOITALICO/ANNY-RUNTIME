"""Durable, sanitized models for governed ANNY Runtime Sync."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"
    MISSING_PROOF = "MISSING_PROOF"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


@dataclass
class CandidateIdentity:
    source: str
    candidate_version: str
    trace_id: str
    release_id: Optional[str] = None
    artifact_name: Optional[str] = None
    artifact_size: Optional[int] = None
    content_digest: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SyncState(str, Enum):
    IDLE = "IDLE"
    SYNCING = "SYNCING"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    STAGING = "STAGING"
    STAGED = "STAGED"
    ACTIVATING = "ACTIVATING"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class SyncResult:
    sync_id: str
    trace_id: str
    requested_at: str
    sync_state: SyncState
    stage: str = "NONE"
    source: str = "UNKNOWN"
    local_version: str = "UNKNOWN"
    candidate_version: Optional[str] = None
    discovered_revision: Optional[str] = None
    comparison: str = "UNKNOWN"
    verification: str = "UNKNOWN"
    activation_performed: bool = False
    error_classification: Optional[str] = None
    evidence_id: Optional[str] = None
    candidate_identity: Optional[Dict[str, Any]] = None
    digest_algorithm: Optional[str] = None
    digest: Optional[str] = None
    proof_reference: Optional[str] = None
    verifier_identity: Optional[str] = None
    operation_id: Optional[str] = None
    operation_type: str = "DISCOVER_VERIFY"
    candidate_id: Optional[str] = None
    candidate_digest: Optional[str] = None
    target: Optional[str] = None
    prior_state: Optional[str] = None
    post_state: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["sync_state"] = self.sync_state.value
        return data
