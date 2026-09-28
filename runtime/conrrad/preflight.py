"""Fail-closed CONRRAD bootstrap preflight.

The Runtime must complete this preflight before any GitHub network operation.
The endpoint is configuration-driven; there is no fallback authority or fixture.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from runtime.security.installation_auth import InstallationCredentialProvider


class PlaneStatus(str, Enum):
    ONLINE_VERIFIED = "ONLINE_VERIFIED"
    ONLINE_UNVERIFIED = "ONLINE_UNVERIFIED"
    OFFLINE = "OFFLINE"
    BLOCKED = "BLOCKED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNKNOWN = "UNKNOWN"


class EvidenceStatus(str, Enum):
    CERTIFIED_BY_LIVE_EVIDENCE = "CERTIFIED_BY_LIVE_EVIDENCE"
    TEST_EVIDENCE_ONLY = "TEST_EVIDENCE_ONLY"
    NOT_CERTIFIED = "NOT_CERTIFIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ConrradBinding:
    runtime_id: str
    installation_id: str
    node_id: str
    trust_authority: str
    issuer_id: str
    tenant_id: str
    project_id: str
    workspace_or_resource_scope: str
    source_reference: str


@dataclass(frozen=True)
class ConrradPreflightResult:
    status: PlaneStatus
    evidence_status: EvidenceStatus
    endpoint: Optional[str]
    binding: Optional[ConrradBinding] = None
    dependency_registry: List[str] = field(default_factory=list)
    reason: Optional[str] = None
    request_id: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.status is PlaneStatus.ONLINE_VERIFIED


class ConrradPreflight:
    """Resolve the authoritative CONRRAD startup preflight over HTTPS."""

    def __init__(
        self,
        endpoint: str,
        credential_provider: Optional[InstallationCredentialProvider] = None,
        timeout: float = 5.0,
    ) -> None:
        self.endpoint = (endpoint or "").strip()
        self.credential_provider = credential_provider
        self.timeout = timeout

    def run(self, runtime_id: str, installation_id: str) -> ConrradPreflightResult:
        request_id = uuid.uuid4().hex
        if not self.endpoint:
            return ConrradPreflightResult(
                PlaneStatus.NOT_CONFIGURED,
                EvidenceStatus.UNKNOWN,
                None,
                reason="CONRRAD preflight endpoint is not configured",
                request_id=request_id,
            )

        if self.credential_provider is None:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="Installation credential provider is unavailable",
                request_id=request_id,
            )

        header = self.credential_provider.authorization_header()
        if not header:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="Runtime installation credential is unavailable",
                request_id=request_id,
            )

        body = json.dumps({
            "runtime_id": runtime_id,
            "installation_id": installation_id,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": header,
                "X-Request-ID": request_id,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return self._parse_payload(payload, runtime_id, installation_id, request_id)
        except urllib.error.HTTPError as exc:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED if exc.code in (401, 403) else PlaneStatus.UNKNOWN,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason=f"CONRRAD preflight HTTP {exc.code}",
                request_id=request_id,
            )
        except (urllib.error.URLError, TimeoutError):
            return ConrradPreflightResult(
                PlaneStatus.OFFLINE,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight unavailable",
                request_id=request_id,
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight response malformed or incomplete",
                request_id=request_id,
            )
        except Exception:
            return ConrradPreflightResult(
                PlaneStatus.UNKNOWN,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight failed",
                request_id=request_id,
            )

    def _parse_payload(
        self,
        payload: Dict[str, Any],
        runtime_id: str,
        installation_id: str,
        request_id: str,
    ) -> ConrradPreflightResult:
        if not isinstance(payload, dict):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight payload must be an object",
                request_id=request_id,
            )

        status = PlaneStatus(payload.get("status", PlaneStatus.UNKNOWN.value))
        evidence_status = EvidenceStatus(
            payload.get("evidence_status", EvidenceStatus.UNKNOWN.value)
        )
        binding_data = payload.get("binding")
        registry = payload.get("dependency_registry", [])
        if not isinstance(registry, list) or not all(isinstance(item, str) for item in registry):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD dependency registry is malformed",
                request_id=request_id,
            )

        required = [
            "runtime_id", "installation_id", "node_id", "trust_authority",
            "issuer_id", "tenant_id", "project_id", "workspace_or_resource_scope",
            "source_reference",
        ]
        if not isinstance(binding_data, dict) or any(
            not isinstance(binding_data.get(key), str) or not binding_data.get(key)
            for key in required
        ):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD runtime/installation/node binding is incomplete",
                request_id=request_id,
            )

        binding = ConrradBinding(**{key: binding_data[key] for key in required})
        if binding.runtime_id != runtime_id or binding.installation_id != installation_id:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED,
                evidence_status,
                self.endpoint,
                reason="CONRRAD runtime/install identity mismatch",
                request_id=request_id,
            )

        if status is not PlaneStatus.ONLINE_VERIFIED:
            return ConrradPreflightResult(
                status,
                evidence_status,
                self.endpoint,
                binding=binding,
                dependency_registry=registry,
                reason="CONRRAD preflight did not establish verified online state",
                request_id=request_id,
            )

        if evidence_status is not EvidenceStatus.CERTIFIED_BY_LIVE_EVIDENCE:
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                evidence_status,
                self.endpoint,
                binding=binding,
                dependency_registry=registry,
                reason="CONRRAD evidence is not certified by live evidence",
                request_id=request_id,
            )

        return ConrradPreflightResult(
            PlaneStatus.ONLINE_VERIFIED,
            EvidenceStatus.CERTIFIED_BY_LIVE_EVIDENCE,
            self.endpoint,
            binding=binding,
            dependency_registry=registry,
            request_id=request_id,
        )
