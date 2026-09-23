from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


class UpdateNotImplementedError(RuntimeError):
    """Raised instead of claiming an update lifecycle action succeeded."""

class UpdateState(Enum):
    IDLE = auto()
    CHECKING = auto()
    DOWNLOADING = auto()
    VERIFYING = auto()
    STAGING = auto()
    QUIESCING = auto()
    ACTIVATING = auto()
    ROLLING_BACK = auto()
    BLOCKED = auto()
    NOT_IMPLEMENTED = auto()
    FAILED = auto()

class UpdateChannel(Enum):
    STABLE = auto()
    BETA = auto()
    DEV = auto()

@dataclass
class UpdateInfo:
    version: str
    channel: UpdateChannel
    url: str
    checksum: str
    release_notes: str
    published_at: str

class UpdateManager:
    """Quarantined update surface until a receipt-backed lifecycle exists."""
    def __init__(self, config: dict, current_version: str) -> None:
        self.config = config
        self.current_version = current_version
        self._state = UpdateState.IDLE

    @property
    def state(self) -> UpdateState:
        return self._state

    def check(self) -> Optional[UpdateInfo]:
        return self._not_implemented("check")

    def download(self, update: UpdateInfo) -> Path:
        return self._not_implemented("download")

    def verify(self, path: Path, expected_checksum: str) -> bool:
        return self._not_implemented("verify")

    def stage(self, path: Path) -> bool:
        return self._not_implemented("stage")

    def activate(self) -> bool:
        return self._not_implemented("activate")

    def rollback(self) -> bool:
        return self._not_implemented("rollback")

    def health_check(self) -> bool:
        return self._not_implemented("health_check")

    def _not_implemented(self, operation: str):
        # A missing implementation is not an attempted-and-failed physical
        # update.  Keep that distinction visible to every caller.
        self._state = UpdateState.NOT_IMPLEMENTED
        raise UpdateNotImplementedError(
            f"UPDATE_{operation.upper()}_NOT_IMPLEMENTED: no receipt-backed lifecycle is configured"
        )
