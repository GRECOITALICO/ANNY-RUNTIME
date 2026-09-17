"""Durable, sanitized models for governed ANNY Runtime Sync."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class SyncState(str, Enum):
    IDLE = "IDLE"
    SYNCING = "SYNCING"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


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
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["sync_state"] = self.sync_state.value
        return data
