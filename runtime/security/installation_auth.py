"""Runtime installation credential boundary for M8 Gate B.

Credentials are resolved only through the existing SecretBackend. References are
safe metadata; credential bytes never appear in logs, evidence, or responses.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from runtime.secrets.backend import SecretBackend


class InstallationAuthStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNCONFIGURED = "RUNTIME_INSTALLATION_AUTH_UNCONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class InstallationAuthResult:
    status: InstallationAuthStatus
    reference: Optional[str] = None
    reason: Optional[str] = None


class InstallationCredentialProvider:
    """Resolve a Runtime installation credential without exposing it."""

    def __init__(self, backend: Optional[SecretBackend], reference: str = "") -> None:
        self._backend = backend
        self._reference = (reference or "").strip()

    @property
    def reference(self) -> Optional[str]:
        return self._reference or None

    def status(self) -> InstallationAuthResult:
        if not self._reference:
            return InstallationAuthResult(
                InstallationAuthStatus.UNCONFIGURED,
                reason="Installation credential reference is not configured",
            )
        if self._backend is None:
            return InstallationAuthResult(
                InstallationAuthStatus.UNAVAILABLE,
                self._reference,
                "SecretBackend is unavailable",
            )
        try:
            if not self._backend.exists(self._reference):
                return InstallationAuthResult(
                    InstallationAuthStatus.UNAVAILABLE,
                    self._reference,
                    "Installation credential is absent from SecretBackend",
                )
            return InstallationAuthResult(
                InstallationAuthStatus.VERIFIED,
                self._reference,
                "Credential reference resolves in SecretBackend",
            )
        except Exception:
            return InstallationAuthResult(
                InstallationAuthStatus.UNAVAILABLE,
                self._reference,
                "SecretBackend lookup failed",
            )

    def get_bytes(self) -> Optional[bytes]:
        """Return credential bytes to the caller; never log or serialize them."""
        result = self.status()
        if result.status is not InstallationAuthStatus.VERIFIED or self._backend is None:
            return None
        value = self._backend.retrieve(self._reference)
        return value if value else None

    def authorization_header(self) -> Optional[str]:
        value = self.get_bytes()
        if value is None:
            return None
        try:
            return "Bearer " + value.decode("utf-8")
        except UnicodeDecodeError:
            return None
