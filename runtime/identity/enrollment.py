import json
from enum import Enum, auto
from pathlib import Path
from typing import Optional

class EnrollmentState(Enum):
    UNENROLLED = auto()
    ENROLLING = auto()
    REGISTERED = auto()
    PAIRED = auto()
    READY = auto()

class EnrollmentError(Exception):
    """Raised when an invalid enrollment state transition is attempted."""
    pass

class ChallengeResponse:
    def create_challenge(self, principal: str) -> str:
        import os
        return os.urandom(32).hex()

    def verify_response(self, principal: str, challenge: str, response: str, runtime_identity) -> bool:
        try:
            return runtime_identity.verify(bytes.fromhex(challenge), bytes.fromhex(response))
        except Exception:
            return False

class EnrollmentManager:
    """
    Manages the lifecycle and state transitions for Runtime enrollment with an Anny instance.
    """
    
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self._state = EnrollmentState.UNENROLLED
        self.principal: Optional[str] = None
        self.tenant_id: Optional[str] = None
        self.anny_instance_id: Optional[str] = None
        self.runtime_id: Optional[str] = None
        self._challenge_response = ChallengeResponse()

    @property
    def state(self) -> EnrollmentState:
        return self._state

    def is_ready(self) -> bool:
        return self._state == EnrollmentState.READY

    def begin_enrollment(self, principal: str, tenant_id: str, challenge: str, response: str, runtime_identity) -> None:
        """Transition from UNENROLLED to ENROLLING."""
        if self._state != EnrollmentState.UNENROLLED:
            raise EnrollmentError(f"Invalid transition from {self._state.name} to ENROLLING")
            
        if not self._challenge_response.verify_response(principal, challenge, response, runtime_identity):
            raise EnrollmentError("Challenge verification failed")
            
        self.principal = principal
        self.tenant_id = tenant_id
        self._state = EnrollmentState.ENROLLING

    def register(self, anny_instance_id: str) -> None:
        """Transition from ENROLLING to REGISTERED."""
        if self._state != EnrollmentState.ENROLLING:
            raise EnrollmentError(f"Invalid transition from {self._state.name} to REGISTERED")
        self.anny_instance_id = anny_instance_id
        self._state = EnrollmentState.REGISTERED

    def pair(self, runtime_id: str) -> None:
        """Transition from REGISTERED to PAIRED."""
        if self._state != EnrollmentState.REGISTERED:
            raise EnrollmentError(f"Invalid transition from {self._state.name} to PAIRED")
        self.runtime_id = runtime_id
        self._state = EnrollmentState.PAIRED

    def activate(self) -> None:
        """Transition from PAIRED to READY."""
        if self._state != EnrollmentState.PAIRED:
            raise EnrollmentError(f"Invalid transition from {self._state.name} to READY")
        self._state = EnrollmentState.READY

    def reset(self) -> None:
        """Reset the enrollment process back to UNENROLLED."""
        self._state = EnrollmentState.UNENROLLED
        self.principal = None
        self.tenant_id = None
        self.anny_instance_id = None
        self.runtime_id = None

    def save(self) -> None:
        """Persist the current enrollment state to disk."""
        data = {
            "state": self._state.name,
            "principal": self.principal,
            "tenant_id": self.tenant_id,
            "anny_instance_id": self.anny_instance_id,
            "runtime_id": self.runtime_id
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.data_dir / "enrollment.json", "w") as f:
            json.dump(data, f, indent=2)

    def load(self) -> None:
        """Load the enrollment state from disk if it exists."""
        path = self.data_dir / "enrollment.json"
        if not path.exists():
            return
            
        with open(path, "r") as f:
            data = json.load(f)
            
        self._state = EnrollmentState[data["state"]]
        self.principal = data.get("principal")
        self.tenant_id = data.get("tenant_id")
        self.anny_instance_id = data.get("anny_instance_id")
        self.runtime_id = data.get("runtime_id")
