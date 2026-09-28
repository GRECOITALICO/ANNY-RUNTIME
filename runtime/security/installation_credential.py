"""Runtime installation credential boundary for M8 Gate B.

This module exposes only an explicitly configured installation credential from
the existing SecretBackend. It never fabricates credentials, grants binding,
or reports authoritative admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from runtime.secrets.backend import SecretBackend


class InstallationCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallationBinding:
    runtime_id: str
    installation_id: str
    credential_ref: str
    authoritative_status: str = "UNKNOWN"


class InstallationCredentialProvider:
    """Load a configured installation credential without introducing authority."""

    def __init__(
        self,
        secret_backend: SecretBackend,
        *,
        credential_ref: str,
        runtime_id: str,
        installation_id: str,
    ) -> None:
        if not credential_ref:
            raise InstallationCredentialError("Installation credential reference is required")
        if not runtime_id:
            raise InstallationCredentialError("runtime_id is required")
        if not installation_id:
            raise InstallationCredentialError("installation_id is required")
        self._backend = secret_backend
        self.binding = InstallationBinding(
            runtime_id=runtime_id,
            installation_id=installation_id,
            credential_ref=credential_ref,
        )

    def is_configured(self) -> bool:
        return bool(self._backend.exists(self.binding.credential_ref))

    def get_credential(self) -> str:
        """Return the configured credential, or fail closed if absent/corrupt."""
        raw = self._backend.retrieve(self.binding.credential_ref)
        if raw is None:
            raise InstallationCredentialError("RUNTIME_INSTALLATION_AUTH_UNCONFIGURED")
        try:
            credential = raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise InstallationCredentialError("RUNTIME_INSTALLATION_CREDENTIAL_INVALID") from exc
        if not credential:
            raise InstallationCredentialError("RUNTIME_INSTALLATION_CREDENTIAL_EMPTY")
        return credential

    def describe_binding(self) -> dict[str, str]:
        """Return safe binding metadata; never includes credential material."""
        return {
            "runtime_id": self.binding.runtime_id,
            "installation_id": self.binding.installation_id,
            "credential_ref": self.binding.credential_ref,
            "authoritative_status": self.binding.authoritative_status,
        }
