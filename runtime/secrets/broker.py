import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from runtime.security.execution_context import ExecutionContext
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


@dataclass(frozen=True)
class SecretAccessGrant:
    """An externally verified authorization claim for one materialization.

    This object is intentionally only a claim.  It becomes usable only when a
    separately supplied authority verifier confirms it; constructing the data
    class locally must never grant secret access.
    """

    secret_reference: str
    tenant_id: str
    account_id: str
    project_id: str
    runtime_id: str
    execution_id: str
    operation_id: str
    generation: int
    expires_at: datetime
    authorization_reference: str
    policy_reference: str


class SecretAuthorityVerifier(Protocol):
    """Adapter for an external secret authorization authority; never an issuer."""

    def __call__(self, grant: SecretAccessGrant, context: ExecutionContext) -> bool:
        ...


class AuthoritativeSecretBroker:
    """Fail-closed secret materialization boundary.

    Runtime does not issue or locally self-verify grants.  A caller supplies a
    canonical ExecutionContext and an external authorization claim, and the
    injected verifier must confirm that claim.  When no verifier is connected,
    every request is BLOCKED.
    """

    def __init__(
        self,
        backend: SecretBackend,
        authority_verifier: Optional[SecretAuthorityVerifier] = None,
    ) -> None:
        self._backend = backend
        self._authority_verifier = authority_verifier

    def use(
        self,
        reference: str,
        context: Optional[ExecutionContext],
        grant: Optional[SecretAccessGrant],
        *,
        current_generation: Optional[int],
    ) -> Optional[SecretHandle]:
        """Return material only after externally verified, exact-scope approval."""
        if context is None or grant is None:
            raise PermissionError("SECRET_ACCESS_CONTEXT_OR_GRANT_REQUIRED")
        if self._authority_verifier is None:
            raise PermissionError("SECRET_AUTHORITY_UNAVAILABLE_BLOCKED")
        if not context.has_capability("SECRET_USE"):
            raise PermissionError("SECRET_USE_CAPABILITY_REQUIRED")
        if current_generation is None or not context.is_valid(datetime.now(timezone.utc), current_generation):
            raise PermissionError("EXECUTION_CONTEXT_INVALID")
        if not all((grant.authorization_reference, grant.policy_reference)):
            raise PermissionError("SECRET_GRANT_REFERENCES_REQUIRED")
        if grant.expires_at < datetime.now(timezone.utc):
            raise PermissionError("SECRET_GRANT_EXPIRED")
        if reference != grant.secret_reference:
            raise PermissionError("SECRET_REFERENCE_SCOPE_MISMATCH")
        context_scope = (
            context.tenant_id,
            context.account_id,
            context.project_id,
            context.runtime_id,
            context.execution_id,
            context.operation_id,
            context.generation,
        )
        grant_scope = (
            grant.tenant_id,
            grant.account_id,
            grant.project_id,
            grant.runtime_id,
            grant.execution_id,
            grant.operation_id,
            grant.generation,
        )
        if context_scope != grant_scope:
            raise PermissionError("SECRET_SCOPE_MISMATCH")
        if not self._authority_verifier(grant, context):
            raise PermissionError("SECRET_AUTHORIZATION_DENIED")

        value = self._backend.retrieve(reference)
        if value is None:
            return None
        return SecretHandle(reference, value)
