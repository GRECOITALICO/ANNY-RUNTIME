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


class ExecutionContextValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionContextAuthorityResult:
    context: Optional[ExecutionContext]
    status_code: Optional[int]
    reason: Optional[str] = None
    evidence_ref: Optional[str] = None


class ExternalExecutionContextClient:
    def __init__(
        self,
        endpoint: str,
        credential_provider: InstallationCredentialProvider,
        evidence_store: Optional[M8EvidenceStore] = None,
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = (endpoint or "").rstrip("/")
        self.credential_provider = credential_provider
        self.evidence_store = evidence_store
        self.timeout = timeout

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
        if not self.endpoint:
            return ExecutionContextAuthorityResult(None, None, "ISSUER_UNAVAILABLE")
        if not self._endpoint_is_https():
            return ExecutionContextAuthorityResult(None, 400, "ISSUER_ENDPOINT_REQUIRES_HTTPS")

        authorization = self.credential_provider.authorization_header()
        if authorization is None:
            return ExecutionContextAuthorityResult(None, None, "ISSUER_UNAVAILABLE")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            self.endpoint + suffix,
            method=method,
            data=data,
            headers={
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data is not None else {}),
                "Authorization": authorization,
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
            evidence_ref = None
            if self.evidence_store:
                ref = self.evidence_store.record(
                    "execution-context",
                    {
                        "context_id": raw.get("context_id"),
                        "runtime_id": raw.get("runtime_id"),
                        "installation_id": raw.get("installation_id"),
                        "generation": raw.get("generation"),
                        "issuer": raw.get("issuer"),
                        "audience": raw.get("audience"),
                        "authorization_refs": raw.get("authorization_refs"),
                        "policy_refs": raw.get("policy_refs"),
                        "evidence_correlation": raw.get("evidence_correlation"),
                        "signature": raw.get("signature"),
                    },
                )
                evidence_ref = str(ref)
            return ExecutionContextAuthorityResult(context, 200, evidence_ref=evidence_ref)
        except urllib.error.HTTPError as exc:
            return ExecutionContextAuthorityResult(None, exc.code, "ISSUER_REJECTED")
        except (urllib.error.URLError, TimeoutError):
            return ExecutionContextAuthorityResult(None, None, "ISSUER_UNAVAILABLE")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return ExecutionContextAuthorityResult(None, 502, f"MALFORMED_CONTEXT:{type(exc).__name__}")
        except Exception:
            return ExecutionContextAuthorityResult(None, None, "UNKNOWN")

    def _parse_context(
        self,
        raw: Dict[str, Any],
        expected_installation_id: Optional[str] = None,
        expected_runtime_id: Optional[str] = None,
        expected_audience: Optional[str] = None,
    ) -> ExecutionContext:
        if not isinstance(raw, dict):
            raise ExecutionContextValidationError("Context response must be an object")
        missing = [key for key in REQUIRED_CONTEXT_FIELDS if key not in raw]
        if missing:
            raise ExecutionContextValidationError("Missing required context fields: " + ",".join(missing))
        if expected_installation_id is not None and raw["installation_id"] != expected_installation_id:
            raise ExecutionContextValidationError("Issuer response installation_id mismatch")
        if expected_runtime_id is not None and raw["runtime_id"] != expected_runtime_id:
            raise ExecutionContextValidationError("Issuer response runtime_id mismatch")
        if expected_audience is not None and raw["audience"] != expected_audience:
            raise ExecutionContextValidationError("Issuer response audience mismatch")
        signature = raw["signature"]
        if not isinstance(signature, dict) or any(key not in signature for key in REQUIRED_SIGNATURE_FIELDS):
            raise ExecutionContextValidationError("Missing required signature fields")
        if not isinstance(raw["authorization_refs"], list) or not raw["authorization_refs"]:
            raise ExecutionContextValidationError("authorization_refs must be non-empty")
        if not isinstance(raw["policy_refs"], list) or not raw["policy_refs"]:
            raise ExecutionContextValidationError("policy_refs must be non-empty")
        if not isinstance(raw["evidence_correlation"], (dict, str)):
            raise ExecutionContextValidationError("evidence_correlation is required")
        scope = raw.get("workspace_or_resource_scope")
        workspace_id = scope or raw.get("workspace_id")
        issued_at = _parse_datetime(raw["issued_at"])
        expires_at = _parse_datetime(raw["expires_at"])
        if not isinstance(raw["generation"], int) or raw["generation"] < 1:
            raise ExecutionContextValidationError("generation must be an externally issued positive integer")
        capabilities = set(raw.get("capability_claims") or [])
        if not all(isinstance(cap, str) for cap in capabilities):
            raise ExecutionContextValidationError("capability_claims must be strings")
        return ExecutionContext(
            context_id=str(raw["context_id"]),
            tenant_id=str(raw["tenant_id"]),
            account_id=str(raw["account_id"]),
            installation_id=str(raw["installation_id"]),
            project_id=str(raw["project_id"]),
            anny_instance_id=str(raw["principal"]),
            runtime_id=str(raw["runtime_id"]),
            session_id=str(raw["session_id"]),
            actor_id=str(raw["actor_id"]),
            operation_id=str(raw["operation_id"]),
            execution_id=str(raw["execution_id"]),
            generation=raw["generation"],
            issued_at=issued_at,
            expires_at=expires_at,
            workspace_id=workspace_id,
            capabilities=capabilities,
            principal=str(raw["principal"]),
            issuer=str(raw["issuer"]),
            audience=str(raw["audience"]),
            authorization_refs=tuple(str(x) for x in raw["authorization_refs"]),
            policy_refs=tuple(str(x) for x in raw["policy_refs"]),
            evidence_correlation=raw["evidence_correlation"],
            signature=signature,
        )


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ExecutionContextValidationError("timestamp must be an ISO-8601 string")
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExecutionContextValidationError("invalid timestamp") from exc
