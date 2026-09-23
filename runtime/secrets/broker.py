import logging
from typing import Optional
from .backend import SecretBackend

logger = logging.getLogger(__name__)

class SecretHandle:
    """Handle to a secret that allows releasing it when done."""
    def __init__(self, reference: str, value: bytes) -> None:
        self._reference = reference
        self._value = value
        self._released = False

    @property
    def value(self) -> bytes:
        if self._released:
            raise RuntimeError("Secret handle already released")
        return self._value

    def release(self) -> None:
        """Clear secret from memory."""
        self._value = b""
        self._released = True

class SecretBroker:
    """Broker for requesting access to secrets."""
    def __init__(self, backend: SecretBackend) -> None:
        self.backend = backend

    def use(self, reference: str, operation_id: str, actor_id: str, tenant_id: str) -> Optional[SecretHandle]:
        """Quarantined legacy entry point; use SecureBroker with ExecutionContext."""
        raise PermissionError("LEGACY_SECRET_BROKER_QUARANTINED")
        if value is None:
            return None
        return SecretHandle(reference, value)

    def store(self, reference: str, value: bytes) -> bool:
        raise PermissionError("LEGACY_SECRET_BROKER_QUARANTINED")

    def exists(self, reference: str) -> bool:
        raise PermissionError("LEGACY_SECRET_BROKER_QUARANTINED")

    def revoke(self, reference: str) -> bool:
        raise PermissionError("LEGACY_SECRET_BROKER_QUARANTINED")
