from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

class UpdateState(Enum):
    IDLE = auto()
    CHECKING = auto()
    DOWNLOADING = auto()
    VERIFYING = auto()
    STAGING = auto()
    QUIESCING = auto()
    ACTIVATING = auto()
    ROLLING_BACK = auto()
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
    """Manages runtime updates safely without destroying core state."""
    def __init__(self, config: dict, current_version: str) -> None:
        self.config = config
        self.current_version = current_version
        self._state = UpdateState.IDLE

    @property
    def state(self) -> UpdateState:
        return self._state

    def check(self) -> Optional[UpdateInfo]:
        self._state = UpdateState.CHECKING
        # Stub implementation
        self._state = UpdateState.IDLE
        return None

    def download(self, update: UpdateInfo) -> Path:
        self._state = UpdateState.DOWNLOADING
        # Stub implementation
        self._state = UpdateState.IDLE
        return Path("/tmp/update.stub")

    def verify(self, path: Path, expected_checksum: str) -> bool:
        self._state = UpdateState.VERIFYING
        self._state = UpdateState.IDLE
        return True

    def stage(self, path: Path) -> bool:
        self._state = UpdateState.STAGING
        self._state = UpdateState.IDLE
        return True

    def activate(self) -> bool:
        self._state = UpdateState.ACTIVATING
        self._state = UpdateState.IDLE
        return True

    def rollback(self) -> bool:
        self._state = UpdateState.ROLLING_BACK
        self._state = UpdateState.IDLE
        return True

    def health_check(self) -> bool:
        return True
