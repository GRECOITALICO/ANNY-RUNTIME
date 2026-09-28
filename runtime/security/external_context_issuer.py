"""External authoritative ExecutionContext issuer client.

The Runtime is a consumer of authority. This module requests, parses and
carries externally issued contexts but never invents tenant, principal,
generation or capability authority.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional


class ExecutionContextIssuerError(RuntimeError):
    pass


@dataclass(frozen=True)
class IssuedExecutionContext:
    context: Any
    context_id: str
    issuer: str
    audience: str
    lifecycle_state: str
    evidence_correlation: Optional[str]
    raw: dict[str, Any]


class ExternalExecutionContextIssuerClient:
    """HTTPS client for issue/refresh/revoke against the canonical external issuer."""

    def __init__(self, endpoint: str, timeout_seconds: float = 10.0):
        endpoint = endpoint.rstrip("/")
        if not endpoint.startswith("https://"):
            raise ExecutionContextIssuerError("ExecutionContext issuer must use HTTPS")
        self.base_url = endpoint
        self.timeout_seconds = timeout_seconds

    def issue(
        self,
        *,
        request_id: str,
        correlation_id: str,
        installation_id: str,
        runtime_id: str,
        audience: str,
        requested_scope: Mapping[str, Any],
        nonce: str,
        installation_credential: str,
        requested_capabilities: Optional[list[str]] = None,
        session_hint: Optional[str] = None,
        client_version: Optional[str] = None,
    ) -> IssuedExecutionContext:
        payload = {
            "request_id": request_id,
            "installation_id": installation_id,
            "runtime_id": runtime_id,
            "audience": audience,
            "requested_scope": dict(requested_scope),
            "nonce": nonce,
        }
        if requested_capabilities is not None:
            payload["requested_capabilities"] = list(requested_capabilities)
        if session_hint is not None:
            payload["session_hint"] = session_hint
        if client_version is not None:
            payload["client_version"] = client_version
        return self._request(
            "/v1/control/execution-contexts",
            payload=payload,
            method="POST",
            request_id=request_id,
            correlation_id=correlation_id,
            nonce=nonce,
            installation_credential=installation_credential,
        )

    def refresh(
        self,
        *,
        request_id: str,
        correlation_id: str,
        context_id: str,
        installation_id: str,
        runtime_id: str,
        audience: str,
        nonce: str,
        installation_credential: str,
    ) -> IssuedExecutionContext:
        payload = {
            "request_id": request_id,
            "context_id": context_id,
            "installation_id": installation_id,
            "runtime_id": runtime_id,
            "audience": audience,
            "nonce": nonce,
        }
        return self._request(
            "/v1/control/execution-contexts/refresh",
            payload=payload,
            method="POST",
            request_id=request_id,
            correlation_id=correlation_id,
            nonce=nonce,
            installation_credential=installation_credential,
        )

    def revoke(
        self,
        *,
        request_id: str,
        correlation_id: str,
        context_id: str,
        installation_id: str,
        runtime_id: str,
        nonce: str,
        installation_credential: str,
    ) -> dict[str, Any]:
        payload = {
            "request_id": request_id,
            "context_id": context_id,
            "installation_id": installation_id,
            "runtime_id": runtime_id,
            "nonce": nonce,
        }
        return self._request_raw(
            "/v1/control/execution-contexts/revoke",
            payload=payload,
            method="POST",
            request_id=request_id,
            correlation_id=correlation_id,
            nonce=nonce,
            installation_credential=installation_credential,
        )

    def _request(
        self, path: str, *, payload: dict[str, Any], method: str,
        request_id: str, correlation_id: str, nonce: str, installation_credential: str,
    ) -> IssuedExecutionContext:
        raw = self._request_raw(
            path,
            payload=payload,
            method=method,
            request_id=request_id,
            correlation_id=correlation_id,
            nonce=nonce,
            installation_credential=installation_credential,
        )
        return self._parse_issued_context(raw, expected_runtime_id=payload.get("runtime_id"))

    def _request_raw(
        self, path: str, *, payload: dict[str, Any], method: str,
        request_id: str, correlation_id: str, nonce: str, installation_credential: str,
    ) -> dict[str, Any]:
        if not installation_credential:
            raise ExecutionContextIssuerError("Authenticated Runtime installation credential is required")
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}{path}", data=body, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Bearer {installation_credential}")
        req.add_header("X-Request-ID", request_id)
        req.add_header("X-Correlation-ID", correlation_id)
        req.add_header("X-Nonce", nonce)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise ExecutionContextIssuerError("Issuer response must be a JSON object")
                return parsed
        except urllib.error.HTTPError as exc:
            try:
                parsed = json.loads(exc.read().decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                parsed = {"error": f"HTTP_{exc.code}"}
            raise ExecutionContextIssuerError(
                f"ExecutionContext issuer returned HTTP {exc.code}: {parsed.get('error', 'UNKNOWN')}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise ExecutionContextIssuerError(
                f"ExecutionContext issuer unavailable: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _parse_issued_context(
        payload: Mapping[str, Any], expected_runtime_id: Optional[str]
    ) -> IssuedExecutionContext:
        required = (
            "context_id", "tenant_id", "account_id", "project_id", "installation_id",
            "runtime_id", "session_id", "actor_id", "operation_id", "execution_id",
            "generation", "issued_at", "expires_at", "issuer", "audience",
            "capability_claims", "signature",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ExecutionContextIssuerError(
                "Issuer response missing required claims: " + ", ".join(missing)
            )
        if expected_runtime_id and payload["runtime_id"] != expected_runtime_id:
            raise ExecutionContextIssuerError("Issuer returned a different runtime_id")
        if not isinstance(payload["generation"], int) or payload["generation"] < 1:
            raise ExecutionContextIssuerError("Issuer generation must be a positive integer")
        if str(payload["lifecycle_state"] if "lifecycle_state" in payload else "ACTIVE").upper() != "ACTIVE":
            raise ExecutionContextIssuerError("Only ACTIVE externally issued contexts may enter Runtime")
        signature = payload["signature"]
        if not isinstance(signature, Mapping):
            raise ExecutionContextIssuerError("Issuer signature metadata is malformed")
        for key in ("algorithm", "key_id", "value", "trust_root_id"):
            if not signature.get(key):
                raise ExecutionContextIssuerError(f"Issuer signature missing {key}")

        from runtime.security.execution_context import ExecutionContext

        def parse_dt(value: Any) -> datetime:
            if not isinstance(value, str):
                raise ExecutionContextIssuerError("Issuer timestamps must be strings")
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ExecutionContextIssuerError("Issuer timestamp is malformed") from exc

        issued = parse_dt(payload["issued_at"])
        expires = parse_dt(payload["expires_at"])
        if expires <= issued:
            raise ExecutionContextIssuerError("Issuer expiry must be after issuance")

        context = ExecutionContext(
            tenant_id=str(payload["tenant_id"]),
            account_id=str(payload["account_id"]),
            project_id=str(payload["project_id"]),
            anny_instance_id=str(payload.get("anny_instance_id", "")),
            runtime_id=str(payload["runtime_id"]),
            session_id=str(payload["session_id"]),
            actor_id=str(payload["actor_id"]),
            operation_id=str(payload["operation_id"]),
            execution_id=str(payload["execution_id"]),
            generation=payload["generation"],
            issued_at=issued,
            expires_at=expires,
            workspace_id=payload.get("workspace_id"),
            capabilities=set(payload["capability_claims"]),
        )
        return IssuedExecutionContext(
            context=context,
            context_id=str(payload["context_id"]),
            issuer=str(payload["issuer"]),
            audience=str(payload["audience"]),
            lifecycle_state="ACTIVE",
            evidence_correlation=payload.get("evidence_correlation"),
            raw=dict(payload),
        )
