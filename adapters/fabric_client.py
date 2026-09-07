import abc
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class FabricSyncResult:
    success: bool
    synced_records: int
    error: Optional[str] = None

class FabricClient(abc.ABC):
    @abc.abstractmethod
    def sync(self, tenant_id: str, repository: str, ref: str) -> FabricSyncResult:
        pass

    @abc.abstractmethod
    def get_records(self, tenant_id: str, record_type: str) -> List[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def get_publication(self, tenant_id: str, repository: str) -> Optional[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def health(self) -> bool:
        pass

class StubFabricClient(FabricClient):
    """Stub client for local execution without external dependencies."""
    def sync(self, tenant_id: str, repository: str, ref: str) -> FabricSyncResult:
        logger.warning("FABRIC_UNAVAILABLE: FabricClient sync is stubbed.")
        return FabricSyncResult(success=False, synced_records=0, error="FABRIC_UNAVAILABLE")

    def get_records(self, tenant_id: str, record_type: str) -> List[Dict[str, Any]]:
        return []

    def get_publication(self, tenant_id: str, repository: str) -> Optional[Dict[str, Any]]:
        return None

    def health(self) -> bool:
        return False
