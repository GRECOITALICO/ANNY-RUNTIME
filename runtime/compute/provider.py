from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from runtime.compute.models import (
    RemoteComputeSession,
    RemoteComputeResourceProfile,
    RemoteSessionState,
    RemoteComputeJob,
    RemoteComputeArtifact
)

class RemoteComputeProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider implementation."""
        pass
        
    @abstractmethod
    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        """Provisions a new remote compute session."""
        pass
        
    @abstractmethod
    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        """Inspects and returns the hardware/software profile of the remote session."""
        pass
        
    @abstractmethod
    def health(self, session: RemoteComputeSession) -> RemoteSessionState:
        """Checks the current health/state of the session."""
        pass
        
    @abstractmethod
    def execute(self, session: RemoteComputeSession, job: RemoteComputeJob) -> RemoteComputeJob:
        """
        Executes a job on the remote session.
        Must enforce that session.state == RemoteSessionState.READY.
        """
        pass
        
    @abstractmethod
    def collect(self, session: RemoteComputeSession, job: RemoteComputeJob) -> List[RemoteComputeArtifact]:
        """Collects artifacts produced by a job."""
        pass
        
    @abstractmethod
    def terminate(self, session: RemoteComputeSession) -> None:
        """Terminates the remote session and releases resources."""
        pass
