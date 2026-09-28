"""External Repository Fabric Trust verifier client."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Optional

from runtime.fabric.models import FabricTrustToken
from runtime.security.installation_auth import InstallationCredentialProvider
from runtime.security.m8_evidence import M8EvidenceStore


@dataclass(frozen=True)
class TrustVerificationResult:
    verification_status: str
    verified: bool
    reason_code: str
    verifier_id: Optional[str] = None
    trust_root_id: Optional[str] = None
    key_id: Optional[str] = None
    verified_at: Optional[str] = None
    evidence_ref: Optional[str] = None
    request_id: Optional[str] = None


class ExternalTrustVerifier:
    def __init__(
        self,
        endpoint: str,
        credential_provider: InstallationCredentialProvider,
        evidence_store: Optional[M8EvidenceStore] = None,
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = (endpoint or "").strip()
        self.credential_provider = credential_provider
        self.evidence_store = evidence_store
        self.timeout = timeout

    def verify(
        self,
        token: FabricTrustToken,
        installation_id: str,
        expected_node_id: str,
        expected_issuer: str,
        expected_audience: str,
        correlation_id: Optional[str] = None,
    ) -> TrustVerificationResult:
        request_id = uuid.uuid4().hex
        nonce = uuid.uuid4().hex
        if not self.endpoint:
            return self._result("UNKNOWN", False, "TRUST_ROOT_UNAVAILABLE", request_id)
        if any(not getattr(token, field, "") for field in (
            "token_id", "issued_at", "expires_at", "issuer", "audience",
            "runtime_id", "node_id", "signature"
        )):
            return self._result("REJECTED", False, "MALFORMED_TOKEN", request_id)
        authorization = self.credential_provider.authorization_header()
        if authorization is None:
            return self._result("UNKNOWN", False, "AUTHENTICATION_FAILED", request_id)

        payload = {
            "request_id": request_id,
            "installation_id": installation_id,
            "runtime_id": token.runtime_id,
            "trust_token": {
                "token_id": token.token_id,
                "issued_at": token.issued_at,
                "expires_at": token.expires_at,
                "issuer": token.issuer,
                "audience": token.audience,
                "runtime_id": token.runtime_id,
                "node_id": token.node_id,
                "signature": token.signature,
            },
            "expected_node_id": expected_node_id,
            "expected_issuer": expected_issuer,
            "expected_audience": expected_audience,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "nonce": nonce,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            method="POST",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": authorization,
                "X-Request-ID": request_id,
                "X-Correlation-ID": correlation_id or request_id,
                "X-Nonce": nonce,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
            result = self._parse_response(raw, request_id)
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                result = self._result("UNKNOWN", False, "TRUST_VERIFIER_UNAVAILABLE", request_id)
            else:
                result = self._result("REJECTED", False, "AUTHENTICATION_FAILED", request_id)
        except (urllib.error.URLError, TimeoutError):
            result = self._result("UNKNOWN", False, "TRUST_VERIFIER_UNAVAILABLE", request_id)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            result = self._result("UNKNOWN", False, "MALFORMED_VERIFIER_RESPONSE", request_id)
        except Exception:
            result = self._result("UNKNOWN", False, "UNKNOWN", request_id)

        if self.evidence_store:
            ref = self.evidence_store.record(
                "trust-verification",
                {
                    "request_id": result.request_id,
                    "runtime_id": token.runtime_id,
                    "installation_id": installation_id,
                    "node_id": token.node_id,
                    "verifier_id": result.verifier_id,
                    "trust_root_id": result.trust_root_id,
                    "key_id": result.key_id,
                    "verification_status": result.verification_status,
                    "reason_code": result.reason_code,
                    "verified_at": result.verified_at,
                },
            )
            return TrustVerificationResult(**{**result.__dict__, "evidence_ref": str(ref)})
        return result

    def _parse_response(self, raw: Dict[str, Any], request_id: str) -> TrustVerificationResult:
        required = ["request_id", "verification_status", "verified", "verifier_id", "verified_at", "evidence_ref"]
        if any(key not in raw for key in required):
            return self._result("UNKNOWN", False, "MALFORMED_VERIFIER_RESPONSE", request_id)
        if raw["request_id"] != request_id:
            return self._result("UNKNOWN", False, "MALFORMED_VERIFIER_RESPONSE", request_id)
        status = str(raw["verification_status"])
        if not isinstance(raw["verified"], bool):
            return self._result("UNKNOWN", False, "MALFORMED_VERIFIER_RESPONSE", request_id)
        verified = raw["verified"]
        if (status == "VERIFIED") != verified:
            return self._result("UNKNOWN", False, "MALFORMED_VERIFIER_RESPONSE", request_id)
        return TrustVerificationResult(
            verification_status=status,
            verified=verified,
            reason_code=str(raw.get("reason_code", "UNKNOWN")),
            verifier_id=str(raw["verifier_id"]),
            trust_root_id=raw.get("trust_root_id"),
            key_id=raw.get("key_id"),
            verified_at=str(raw["verified_at"]),
            evidence_ref=str(raw["evidence_ref"]),
            request_id=str(raw["request_id"]),
        )

    @staticmethod
    def _result(status: str, verified: bool, reason: str, request_id: str) -> TrustVerificationResult:
        return TrustVerificationResult(status, verified, reason, request_id=request_id)
