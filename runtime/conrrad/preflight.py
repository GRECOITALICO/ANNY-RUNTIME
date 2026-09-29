"""Fail-closed CONRRAD bootstrap preflight.

The Runtime must complete this preflight before any GitHub network operation.
The endpoint is configuration-driven; there is no fallback authority or fixture.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

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

    def _endpoint_is_https(self) -> bool:
        parsed = urlparse(self.endpoint)
        return parsed.scheme.lower() == "https" and bool(parsed.netloc)

    def run(
        self,
        runtime_id: str,
        installation_id: str,
        requested_scope: Optional[Dict[str, str]] = None,
        expected_node_id: Optional[str] = None,
    ) -> ConrradPreflightResult:
        request_id = uuid.uuid4().hex
        if not self.endpoint:
            return ConrradPreflightResult(
                PlaneStatus.NOT_CONFIGURED,
                EvidenceStatus.UNKNOWN,
                None,
                reason="CONRRAD preflight endpoint is not configured",
                request_id=request_id,
            )

        if not self._endpoint_is_https():
            return ConrradPreflightResult(
                PlaneStatus.NOT_CONFIGURED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight endpoint must use HTTPS",
                request_id=request_id,
            )

        if not isinstance(runtime_id, str) or not runtime_id:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="Runtime identity is incomplete",
                request_id=request_id,
            )
        if not isinstance(installation_id, str) or not installation_id:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="Installation identity is incomplete",
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

        body = {
            "runtime_id": runtime_id,
            "installation_id": installation_id,
        }
        if requested_scope is not None:
            body["requested_scope"] = {
                key: requested_scope[key]
                for key in ("tenant_id", "project_id", "workspace_or_resource_scope")
                if key in requested_scope
            }

        payload_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=payload_bytes,
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
            return self._parse_payload(
                payload,
                runtime_id,
                installation_id,
                request_id,
                expected_node_id,
            )
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
        except (ValueError, KeyError, TypeError):
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
        expected_node_id: Optional[str] = None,
    ) -> ConrradPreflightResult:
        if not isinstance(payload, dict):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight payload must be an object",
                request_id=request_id,
            )

        required_top = (
            "status",
            "evidence_status",
            "request_id",
            "endpoint",
            "binding",
            "dependency_registry",
            "reason",
        )
        if any(key not in payload for key in required_top):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight response missing required fields",
                request_id=request_id,
            )

        response_request_id = payload["request_id"]
        response_endpoint = payload["endpoint"]
        if not isinstance(response_request_id, str) or response_request_id != request_id:
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight response request_id mismatch",
                request_id=request_id,
            )
        if not isinstance(response_endpoint, str) or response_endpoint != self.endpoint:
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight response endpoint mismatch",
                request_id=request_id,
            )

        try:
            status = PlaneStatus(payload["status"])
            evidence_status = EvidenceStatus(payload["evidence_status"])
        except (ValueError, TypeError):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight response status is invalid",
                request_id=request_id,
            )

        binding_data = payload["binding"]
        registry = payload["dependency_registry"]
        reason = payload["reason"]
        required_binding = [
            "runtime_id",
            "installation_id",
            "node_id",
            "trust_authority",
            "issuer_id",
            "tenant_id",
            "project_id",
            "workspace_or_resource_scope",
            "source_reference",
        ]
        if not isinstance(registry, list) or not all(isinstance(item, str) for item in registry):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD dependency registry is malformed",
                request_id=request_id,
            )
        if not isinstance(reason, str) and reason is not None:
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD preflight reason is malformed",
                request_id=request_id,
            )
        if not isinstance(binding_data, dict) or any(
            not isinstance(binding_data.get(key), str) or not binding_data.get(key)
            for key in required_binding
        ):
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                EvidenceStatus.UNKNOWN,
                self.endpoint,
                reason="CONRRAD runtime/installation/node binding is incomplete",
                request_id=request_id,
            )

        binding = ConrradBinding(**{key: binding_data[key] for key in required_binding})
        if binding.runtime_id != runtime_id or binding.installation_id != installation_id:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED,
                evidence_status,
                self.endpoint,
                binding=binding,
                dependency_registry=registry,
                reason="CONRRAD runtime/install identity mismatch",
                request_id=request_id,
            )

        configured_expected_node_id = (expected_node_id or os.environ.get("M8_NODE_ID", "")).strip()
        if configured_expected_node_id and binding.node_id != configured_expected_node_id:
            return ConrradPreflightResult(
                PlaneStatus.BLOCKED,
                evidence_status,
                self.endpoint,
                binding=binding,
                dependency_registry=registry,
                reason="CONRRAD node binding mismatch",
                request_id=request_id,
            )

        if status is not PlaneStatus.ONLINE_VERIFIED:
            return ConrradPreflightResult(
                status,
                evidence_status,
                self.endpoint,
                binding=binding,
                dependency_registry=registry,
                reason=reason,
                request_id=request_id,
            )

        if not configured_expected_node_id:
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                evidence_status,
                self.endpoint,
                binding=binding,
                dependency_registry=registry,
                reason="Runtime expected node binding is not configured",
                request_id=request_id,
            )

        if evidence_status is not EvidenceStatus.CERTIFIED_BY_LIVE_EVIDENCE:
            return ConrradPreflightResult(
                PlaneStatus.ONLINE_UNVERIFIED,
                evidence_status,
                self.endpoint,
                binding=binding,
                dependency_registry=registry,
                reason=reason or "CONRRAD evidence is not certified by live evidence",
                request_id=request_id,
            )

        return ConrradPreflightResult(
            PlaneStatus.ONLINE_VERIFIED,
            EvidenceStatus.CERTIFIED_BY_LIVE_EVIDENCE,
            self.endpoint,
            binding=binding,
            dependency_registry=registry,
            reason=reason,
            request_id=request_id,
        )
