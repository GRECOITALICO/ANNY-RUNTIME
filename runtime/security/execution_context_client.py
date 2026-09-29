"""External M8 ExecutionContext issuer client."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from typing import Any, Dict, Optional

from runtime.security.execution_context import ExecutionContext
from runtime.security.execution_context_verifier import (
    ExecutionContextValidationError,
    ExecutionContextVerifier,
    TrustMaterialResolver,
    UNKNOWN_REASONS,
)
from runtime.security.installation_auth import InstallationCredentialProvider
from runtime.security.m8_evidence import M8EvidenceStore


REQUIRED_CONTEXT_FIELDS = (
    "context_id", "principal", "tenant_id", "account_id", "project_id",
    "installation_id", "runtime_id", "session_id", "actor_id", "operation_id",
    "execution_id", "generation", "issued_at", "expires_at", "issuer",
    "audience", "capability_claims", "authorization_refs", "policy_refs",
    "evidence_correlation", "signature",
)
REQUIRED_SIGNATURE_FIELDS = (
    "algorithm", "key_id", "value", "signed_claims_digest", "trust_root_id",
)


@dataclass(frozen=True)
class ExecutionContextAuthorityResult:
    context: Optional[ExecutionContext]
    status_code: Optional[int]
    reason: Optional[str] = None
    evidence_ref: Optional[str] = None
    verification_status: str = "UNKNOWN"


class ExternalExecutionContextClient:
    def __init__(
        self,
        endpoint: str,
        credential_provider: InstallationCredentialProvider,
        evidence_store: Optional[M8EvidenceStore] = None,
        timeout: float = 10.0,
        trust_material_backend: Optional[Any] = None,
        trust_root_id: str = "",
        trust_root_reference: str = "",
        expected_issuer: str = "",
    ) -> None:
        self.endpoint = (endpoint or "").rstrip("/")
        self.credential_provider = credential_provider
        self.evidence_store = evidence_store
        self.timeout = timeout
        self.verifier = ExecutionContextVerifier(
            TrustMaterialResolver(
                trust_material_backend,
                trust_root_id,
                trust_root_reference,
            ),
            expected_issuer=expected_issuer,
        )

    def _endpoint_is_https(self) -> bool:
        parsed = urlparse(self.endpoint)
        return parsed.scheme.lower() == "https" and bool(parsed.netloc)

    def issue(
        self,
        installation_id: str,
        runtime_id: str,
        requested_scope: Dict[str, str],
        audience: str,
        requested_capabilities: Optional[list[str]] = None,
        session_hint: Optional[str] = None,
    ) -> ExecutionContextAuthorityResult:
        required_scope = (
            "tenant_id", "account_id", "project_id", "workspace_or_resource_scope"
        )
        if not isinstance(requested_scope, dict):
            return ExecutionContextAuthorityResult(None, 400, "INVALID_REQUESTED_SCOPE")
        missing = [field for field in required_scope if not requested_scope.get(field)]
        if missing:
            return ExecutionContextAuthorityResult(
                None, 400, "MISSING_REQUESTED_SCOPE:" + ",".join(missing)
            )
        return self._request(
            "/v1/control/execution-contexts",
            {
                "request_id": uuid.uuid4().hex,
                "installation_id": installation_id,
                "runtime_id": runtime_id,
                "audience": audience,
                "requested_scope": requested_scope,
                "requested_capabilities": requested_capabilities or [],
                "session_hint": session_hint,
                "nonce": uuid.uuid4().hex,
            },
            expected_installation_id=installation_id,
            expected_runtime_id=runtime_id,
            expected_audience=audience,
        )

    def refresh(self, context_id: str, installation_id: str, runtime_id: str, audience: str) -> ExecutionContextAuthorityResult:
        return self._request(
            "/v1/control/execution-contexts/refresh",
            {
                "request_id": uuid.uuid4().hex,
                "installation_id": installation_id,
                "runtime_id": runtime_id,
                "audience": audience,
                "context_id": context_id,
                "nonce": uuid.uuid4().hex,
            },
            expected_installation_id=installation_id,
            expected_runtime_id=runtime_id,
            expected_audience=audience,
        )

    def revoke(self, context_id: str, installation_id: str, runtime_id: str, audience: str) -> ExecutionContextAuthorityResult:
        return self._request(
            "/v1/control/execution-contexts/revoke",
            {
                "request_id": uuid.uuid4().hex,
                "installation_id": installation_id,
                "runtime_id": runtime_id,
                "audience": audience,
                "context_id": context_id,
                "nonce": uuid.uuid4().hex,
            },
            expected_installation_id=installation_id,
            expected_runtime_id=runtime_id,
            expected_audience=audience,
        )

    def get(
        self,
        context_id: str,
        installation_id: Optional[str] = None,
        runtime_id: Optional[str] = None,
        audience: Optional[str] = None,
    ) -> ExecutionContextAuthorityResult:
        return self._request(
            f"/v1/control/execution-contexts/{context_id}",
            None,
            method="GET",
            expected_installation_id=installation_id,
            expected_runtime_id=runtime_id,
            expected_audience=audience,
        )

    def _request(
        self,
        suffix: str,
        payload: Optional[Dict[str, Any]],
        method: str = "POST",
        expected_installation_id: Optional[str] = None,
        expected_runtime_id: Optional[str] = None,
        expected_audience: Optional[str] = None,
    ) -> ExecutionContextAuthorityResult:
        request_id = (
            str(payload.get("request_id"))
            if isinstance(payload, dict) and payload.get("request_id")
            else uuid.uuid4().hex
        )
        raw: Optional[Dict[str, Any]] = None
        verified_at = None
        result: ExecutionContextAuthorityResult

        if not self.endpoint:
            result = ExecutionContextAuthorityResult(
                None, None, "ISSUER_UNAVAILABLE", verification_status="UNKNOWN"
            )
        elif not self._endpoint_is_https():
            result = ExecutionContextAuthorityResult(
                None, 400, "ISSUER_ENDPOINT_REQUIRES_HTTPS", verification_status="REJECTED"
            )
        else:
            authorization = self.credential_provider.authorization_header()
            if authorization is None:
                result = ExecutionContextAuthorityResult(
                    None, None, "ISSUER_UNAVAILABLE", verification_status="UNKNOWN"
                )
            else:
                request_payload = dict(payload) if isinstance(payload, dict) else None
                if request_payload is not None:
                    request_payload["request_id"] = request_id
                    data = json.dumps(request_payload).encode("utf-8")
                else:
                    data = None
                req = urllib.request.Request(
                    self.endpoint + suffix,
                    method=method,
                    data=data,
                    headers={
                        "Accept": "application/json",
                        **({"Content-Type": "application/json"} if data is not None else {}),
                        "Authorization": authorization,
                        "X-Request-ID": request_id,
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as response:
                        raw = json.loads(response.read().decode("utf-8"))
                    context = self._parse_context(
                        raw,
                        expected_installation_id=expected_installation_id,
                        expected_runtime_id=expected_runtime_id,
                        expected_audience=expected_audience,
                    )
                    verified_at = context.verified_at
                    result = ExecutionContextAuthorityResult(
                        context,
                        200,
                        "VERIFIED",
                        verification_status="VERIFIED",
                    )
                except ExecutionContextValidationError as exc:
                    status = "UNKNOWN" if exc.reason_code in UNKNOWN_REASONS else "REJECTED"
                    result = ExecutionContextAuthorityResult(
                        None,
                        502,
                        exc.reason_code,
                        verification_status=status,
                    )
                except urllib.error.HTTPError as exc:
                    result = ExecutionContextAuthorityResult(
                        None,
                        exc.code,
                        "ISSUER_REJECTED",
                        verification_status="UNKNOWN",
                    )
                except (urllib.error.URLError, TimeoutError):
                    result = ExecutionContextAuthorityResult(
                        None,
                        None,
                        "ISSUER_UNAVAILABLE",
                        verification_status="UNKNOWN",
                    )
                except (ValueError, TypeError, json.JSONDecodeError):
                    result = ExecutionContextAuthorityResult(
                        None,
                        502,
                        "MALFORMED_CONTEXT",
                        verification_status="REJECTED",
                    )
                except Exception:
                    result = ExecutionContextAuthorityResult(
                        None,
                        None,
                        "UNKNOWN",
                        verification_status="UNKNOWN",
                    )

        if self.evidence_store:
            signature = (
                raw.get("signature")
                if isinstance(raw, dict) and isinstance(raw.get("signature"), dict)
                else {}
            )
            ref = self.evidence_store.record(
                "execution-context-verification",
                {
                    "request_id": request_id,
                    "context_id": raw.get("context_id") if isinstance(raw, dict) else None,
                    "runtime_id": raw.get("runtime_id") if isinstance(raw, dict) else None,
                    "installation_id": raw.get("installation_id") if isinstance(raw, dict) else None,
                    "issuer": raw.get("issuer") if isinstance(raw, dict) else None,
                    "audience": raw.get("audience") if isinstance(raw, dict) else None,
                    "generation": raw.get("generation") if isinstance(raw, dict) else None,
                    "trust_root_id": signature.get("trust_root_id"),
                    "key_id": signature.get("key_id"),
                    "algorithm": signature.get("algorithm"),
                    "signed_claims_digest": signature.get("signed_claims_digest"),
                    "verification_status": result.verification_status,
                    "verification_reason": result.reason,
                    "verified_at": verified_at,
                },
            )
            result = ExecutionContextAuthorityResult(
                result.context,
                result.status_code,
                result.reason,
                evidence_ref=str(ref),
                verification_status=result.verification_status,
            )
        return result

    def _parse_context(
        self,
        raw: Dict[str, Any],
        expected_installation_id: Optional[str] = None,
        expected_runtime_id: Optional[str] = None,
        expected_audience: Optional[str] = None,
    ) -> ExecutionContext:
        return self.verifier.verify(
            raw,
            expected_installation_id=expected_installation_id,
            expected_runtime_id=expected_runtime_id,
            expected_audience=expected_audience,
        )

def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ExecutionContextValidationError("timestamp must be an ISO-8601 string")
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExecutionContextValidationError("invalid timestamp") from exc
