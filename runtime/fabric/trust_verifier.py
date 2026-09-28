"""External authoritative Fabric trust verification client.

This module never upgrades local trust state by construction. A Runtime token is
only VERIFIED when the configured external verifier explicitly returns that
status. Transport failures remain UNKNOWN.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional


class TrustVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TrustVerificationResult:
    status: TrustVerificationStatus
    verified: bool
    verifier_id: Optional[str] = None
    evidence_ref: Optional[str] = None
    reason_code: Optional[str] = None
    raw: Optional[dict[str, Any]] = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "TrustVerificationResult":
        raw_status = str(payload.get("verification_status", "UNKNOWN")).upper()
        try:
            status = TrustVerificationStatus(raw_status)
        except ValueError:
            status = TrustVerificationStatus.UNKNOWN
        # Never infer VERIFIED from a missing/contradictory status.
        verified = status is TrustVerificationStatus.VERIFIED and payload.get("verified") is True
        if status is not TrustVerificationStatus.VERIFIED:
            verified = False
        return cls(
            status=status,
            verified=verified,
            verifier_id=payload.get("verifier_id"),
            evidence_ref=payload.get("evidence_ref"),
            reason_code=payload.get("reason_code"),
            raw=dict(payload),
        )


class TrustVerificationError(RuntimeError):
    pass


class ExternalFabricTrustVerifier:
    """HTTPS client for the canonical POST /v1/fabric/trust/verify endpoint."""

    REQUIRED_REQUEST_FIELDS = (
        "request_id",
        "runtime_id",
        "installation_id",
        "trust_token",
        "expected_node_id",
        "expected_issuer",
        "expected_audience",
        "observed_at",
        "nonce",
    )

    def __init__(self, endpoint: str, timeout_seconds: float = 10.0):
        endpoint = endpoint.rstrip("/")
        if not endpoint.startswith("https://"):
            raise TrustVerificationError("External trust verifier must use HTTPS")
        self.endpoint = f"{endpoint}/v1/fabric/trust/verify"
        self.timeout_seconds = timeout_seconds

    def verify(
        self,
        *,
        request_id: str,
        correlation_id: str,
        nonce: str,
        runtime_id: str,
        installation_id: str,
        trust_token: Mapping[str, Any],
        expected_node_id: str,
        expected_issuer: str,
        expected_audience: str,
        observed_at: str,
        installation_credential: str,
    ) -> TrustVerificationResult:
        request = {
            "request_id": request_id,
            "runtime_id": runtime_id,
            "installation_id": installation_id,
            "trust_token": dict(trust_token),
            "expected_node_id": expected_node_id,
            "expected_issuer": expected_issuer,
            "expected_audience": expected_audience,
            "observed_at": observed_at,
            "nonce": nonce,
        }
        missing = [key for key in self.REQUIRED_REQUEST_FIELDS if not request.get(key)]
        if missing:
            raise TrustVerificationError(
                "Missing required trust verification fields: " + ", ".join(missing)
            )
        if not installation_credential:
            raise TrustVerificationError("Authenticated Runtime installation credential is required")

        body = json.dumps(request, sort_keys=True).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Bearer {installation_credential}")
        req.add_header("X-Request-ID", request_id)
        req.add_header("X-Correlation-ID", correlation_id)
        req.add_header("X-Nonce", nonce)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return TrustVerificationResult.from_payload(payload)
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                return TrustVerificationResult.from_payload(payload)
            except (ValueError, json.JSONDecodeError):
                return TrustVerificationResult(
                    status=TrustVerificationStatus.UNKNOWN,
                    verified=False,
                    reason_code=f"HTTP_{exc.code}",
                )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            return TrustVerificationResult(
                status=TrustVerificationStatus.UNKNOWN,
                verified=False,
                reason_code=type(exc).__name__,
            )
