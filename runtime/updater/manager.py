from dataclasses import dataclass
from enum import Enum, auto
from hashlib import sha256
from pathlib import Path
from typing import Optional


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
    NOT_IMPLEMENTED = auto()


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
    """Truthful update lifecycle boundary.

    Discovery/download/stage/activate/rollback require an authoritative update
    source and physical lifecycle implementation. Until those exist, methods
    fail closed rather than returning synthetic success.
    """

    def __init__(self, config: dict, current_version: str) -> None:
        self.config = config
        self.current_version = current_version
        self._state = UpdateState.IDLE
        self._last_error: Optional[str] = None

    @property
    def state(self) -> UpdateState:
        return self._state

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def _not_implemented(self, operation: str) -> None:
        self._state = UpdateState.NOT_IMPLEMENTED
        self._last_error = f"{operation.upper()}_NOT_IMPLEMENTED"
        raise NotImplementedError(self._last_error)

    def check(self) -> Optional[UpdateInfo]:
        self._not_implemented("check")
        return None

    def download(self, update: UpdateInfo) -> Path:
        self._not_implemented("download")
        raise AssertionError("unreachable")

    def verify(self, path: Path, expected_checksum: str) -> bool:
        """Verify a local artifact checksum; no claim is made about its provenance."""
        self._state = UpdateState.VERIFYING
        self._last_error = None
        if not path.is_file():
            self._state = UpdateState.FAILED
            self._last_error = "ARTIFACT_NOT_FOUND"
            return False
        normalized = expected_checksum.strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            self._state = UpdateState.FAILED
            self._last_error = "INVALID_SHA256"
            return False
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        verified = digest.hexdigest() == normalized
        self._state = UpdateState.IDLE if verified else UpdateState.FAILED
        self._last_error = None if verified else "CHECKSUM_MISMATCH"
        return verified

    def stage(self, path: Path) -> bool:
        self._not_implemented("stage")
        return False

    def activate(self) -> bool:
        self._not_implemented("activate")
        return False

    def rollback(self) -> bool:
        self._not_implemented("rollback")
        return False

    def health_check(self) -> bool:
        return self._state not in {UpdateState.NOT_IMPLEMENTED, UpdateState.FAILED}
