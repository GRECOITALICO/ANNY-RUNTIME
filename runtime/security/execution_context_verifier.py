"""Deterministic Runtime-side cryptographic verification for M8 ExecutionContext."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key

from runtime.security.execution_context import ExecutionContext
from runtime.secrets.backend import SecretBackend


ALLOWED_ALGORITHM = "Ed25519"
DIGEST_SIZE = 32
ED25519_SIGNATURE_SIZE = 64
ED25519_PUBLIC_KEY_SIZE = 32
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")

UNKNOWN_REASONS = {
    "UNKNOWN_TRUST_ROOT",
    "UNKNOWN_KEY",
    "TRUST_MATERIAL_UNAVAILABLE",
    "ISSUER_UNAVAILABLE",
}


@dataclass(frozen=True)
class TrustedVerificationKey:
    key_id: str
    algorithm: str
    public_key: Ed25519PublicKey
    not_before: datetime
    not_after: datetime
    status: str


class ExecutionContextValidationError(ValueError):
    def __init__(self, reason_code: str, message: Optional[str] = None) -> None:
        self.reason_code = reason_code
        super().__init__(message or reason_code)


class TrustMaterialResolver:
    """Resolve trusted verification material only from the existing SecretBackend."""

    def __init__(
        self,
        backend: Optional[SecretBackend],
        trust_root_id: str,
        trust_root_reference: str,
    ) -> None:
        self._backend = backend
        self._trust_root_id = (trust_root_id or "").strip()
        self._trust_root_reference = (trust_root_reference or "").strip()

    def resolve(
        self,
        trust_root_id: str,
        key_id: str,
        now: datetime,
    ) -> TrustedVerificationKey:
        if not self._trust_root_id or trust_root_id != self._trust_root_id:
            raise ExecutionContextValidationError(
                "UNKNOWN_TRUST_ROOT",
                "ExecutionContext trust_root_id is not an explicitly configured trusted root",
            )
        if self._backend is None or not self._trust_root_reference:
            raise ExecutionContextValidationError(
                "TRUST_MATERIAL_UNAVAILABLE",
                "Configured trust-root bundle is unavailable",
            )

        try:
            raw_bundle = self._backend.retrieve(self._trust_root_reference)
        except Exception as exc:
            raise ExecutionContextValidationError(
                "TRUST_MATERIAL_UNAVAILABLE",
                "Trusted verification material could not be retrieved",
            ) from exc
        if not raw_bundle:
            raise ExecutionContextValidationError(
                "TRUST_MATERIAL_UNAVAILABLE",
                "Trusted verification material is absent",
            )

        try:
            bundle = json.loads(raw_bundle.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ExecutionContextValidationError(
                "TRUST_MATERIAL_UNAVAILABLE",
                "Trusted trust-root bundle is malformed",
            ) from exc

        if not isinstance(bundle, dict) or not isinstance(bundle.get("keys"), list):
            raise ExecutionContextValidationError(
                "TRUST_MATERIAL_UNAVAILABLE",
                "Trusted trust-root bundle must contain a keys array",
            )

        candidate = None
        for key in bundle["keys"]:
            if isinstance(key, dict) and key.get("key_id") == key_id:
                candidate = key
                break
        if candidate is None:
            raise ExecutionContextValidationError(
                "UNKNOWN_KEY",
                "ExecutionContext key_id is absent from the trusted trust-root bundle",
            )

        required = ("key_id", "algorithm", "public_key", "not_before", "not_after", "status")
        if any(field not in candidate for field in required):
            raise ExecutionContextValidationError(
                "TRUST_MATERIAL_UNAVAILABLE",
                "Trusted verification key metadata is incomplete",
            )

        algorithm = candidate["algorithm"]
        if algorithm != ALLOWED_ALGORITHM:
            raise ExecutionContextValidationError(
                "UNSUPPORTED_ALGORITHM",
                "Trusted verification key algorithm is not Ed25519",
            )

        status = candidate["status"]
        if status == "REVOKED":
            raise ExecutionContextValidationError("REVOKED_KEY")
        if status == "EXPIRED":
            raise ExecutionContextValidationError("EXPIRED_KEY")
        if status != "ACTIVE":
            raise ExecutionContextValidationError(
                "UNKNOWN_KEY",
                "Trusted verification key status is not active",
            )

        not_before = _parse_aware_datetime(candidate["not_before"], "TRUST_MATERIAL_UNAVAILABLE")
        not_after = _parse_aware_datetime(candidate["not_after"], "TRUST_MATERIAL_UNAVAILABLE")
        if now > not_after:
            raise ExecutionContextValidationError("EXPIRED_KEY")
        if now < not_before:
            raise ExecutionContextValidationError("KEY_NOT_YET_VALID")
        if not_before > not_after:
            raise ExecutionContextValidationError(
                "TRUST_MATERIAL_UNAVAILABLE",
                "Trusted verification key validity window is malformed",
            )

        public_key = _load_public_key(candidate["public_key"])
        return TrustedVerificationKey(
            key_id=str(candidate["key_id"]),
            algorithm=algorithm,
            public_key=public_key,
            not_before=not_before,
            not_after=not_after,
            status=status,
        )


class ExecutionContextVerifier:
    """Verify externally issued M8 ExecutionContext values before acceptance."""

    def __init__(
        self,
        trust_material_resolver: TrustMaterialResolver,
        expected_issuer: str = "",
        expected_audience: str = "",
    ) -> None:
        self._trust_material = trust_material_resolver
        self._expected_issuer = (expected_issuer or "").strip()
        self._expected_audience = (expected_audience or "").strip()

    def verify(
        self,
        raw: Dict[str, Any],
        *,
        expected_installation_id: Optional[str],
        expected_runtime_id: Optional[str],
        expected_audience: Optional[str] = None,
        expected_issuer: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ExecutionContext:
        if now is None:
            now = datetime.now(timezone.utc)

        self._validate_schema(raw)
        signature = raw["signature"]
        algorithm = signature["algorithm"]
        if algorithm != ALLOWED_ALGORITHM:
            raise ExecutionContextValidationError("UNSUPPORTED_ALGORITHM")

        trust_root_id = signature["trust_root_id"]
        key_id = signature["key_id"]
        if not isinstance(trust_root_id, str) or not trust_root_id:
            raise ExecutionContextValidationError("UNKNOWN_TRUST_ROOT")
        if not isinstance(key_id, str) or not key_id:
            raise ExecutionContextValidationError("UNKNOWN_KEY")

        trusted_key = self._trust_material.resolve(trust_root_id, key_id, now)

        canonical = canonicalize_signed_claims(raw)
        signed_claims_digest = signature["signed_claims_digest"]
        digest_bytes = _decode_b64url(
            signed_claims_digest,
            DIGEST_SIZE,
            "MALFORMED_SIGNATURE",
        )
        recomputed_digest = hashlib.sha256(canonical).digest()
        canonical_digest = _encode_b64url(recomputed_digest)
        if canonical_digest != signed_claims_digest or digest_bytes != recomputed_digest:
            raise ExecutionContextValidationError("DIGEST_MISMATCH")

        signature_bytes = _decode_b64url(
            signature["value"],
            ED25519_SIGNATURE_SIZE,
            "MALFORMED_SIGNATURE",
        )
        try:
            trusted_key.public_key.verify(signature_bytes, canonical)
        except InvalidSignature as exc:
            raise ExecutionContextValidationError("INVALID_SIGNATURE") from exc
        except (TypeError, ValueError) as exc:
            raise ExecutionContextValidationError("INVALID_SIGNATURE") from exc

        expected_runtime = expected_runtime_id
        if expected_runtime is not None and raw["runtime_id"] != expected_runtime:
            raise ExecutionContextValidationError("WRONG_RUNTIME")

        expected_installation = expected_installation_id
        if expected_installation is not None and raw["installation_id"] != expected_installation:
            raise ExecutionContextValidationError("WRONG_INSTALLATION")

        configured_issuer = expected_issuer if expected_issuer is not None else self._expected_issuer
        if configured_issuer and raw["issuer"] != configured_issuer:
            raise ExecutionContextValidationError("WRONG_ISSUER")

        configured_audience = expected_audience if expected_audience is not None else self._expected_audience
        if configured_audience and raw["audience"] != configured_audience:
            raise ExecutionContextValidationError("WRONG_AUDIENCE")

        issued_at = _parse_aware_datetime(raw["issued_at"], "MALFORMED_CONTEXT")
        expires_at = _parse_aware_datetime(raw["expires_at"], "MALFORMED_CONTEXT")
        if now < issued_at:
            raise ExecutionContextValidationError("NOT_YET_VALID_CONTEXT")
        if now > expires_at:
            raise ExecutionContextValidationError("EXPIRED_CONTEXT")
        if expires_at < issued_at:
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")

        generation = raw["generation"]
        if type(generation) is not int or generation < 1:
            raise ExecutionContextValidationError("STALE_GENERATION")

        capabilities = set(raw["capability_claims"])
        if not all(isinstance(value, str) for value in capabilities):
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")
        if not raw["authorization_refs"]:
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")
        if not raw["policy_refs"]:
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")

        return ExecutionContext(
            context_id=raw["context_id"],
            tenant_id=raw["tenant_id"],
            account_id=raw["account_id"],
            project_id=raw["project_id"],
            anny_instance_id=raw["principal"],
            runtime_id=raw["runtime_id"],
            session_id=raw["session_id"],
            actor_id=raw["actor_id"],
            operation_id=raw["operation_id"],
            execution_id=raw["execution_id"],
            generation=generation,
            issued_at=issued_at,
            expires_at=expires_at,
            workspace_id=raw.get("workspace_or_resource_scope") or raw.get("workspace_id"),
            capabilities=capabilities,
            installation_id=raw["installation_id"],
            principal=raw["principal"],
            issuer=raw["issuer"],
            audience=raw["audience"],
            authorization_refs=tuple(raw["authorization_refs"]),
            policy_refs=tuple(raw["policy_refs"]),
            evidence_correlation=raw["evidence_correlation"],
            signature=dict(signature),
            verification_status="VERIFIED",
            verification_reason="VERIFIED",
            verified_at=now,
        )

    @staticmethod
    def _validate_schema(raw: Dict[str, Any]) -> None:
        if not isinstance(raw, dict):
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")

        required = (
            "context_id", "principal", "tenant_id", "account_id", "project_id",
            "installation_id", "runtime_id", "session_id", "actor_id",
            "operation_id", "execution_id", "generation", "issued_at",
            "expires_at", "issuer", "audience", "capability_claims",
            "authorization_refs", "policy_refs", "evidence_correlation", "signature",
        )
        missing = [field for field in required if field not in raw]
        if missing:
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")

        string_fields = (
            "context_id", "principal", "tenant_id", "account_id", "project_id",
            "installation_id", "runtime_id", "session_id", "actor_id",
            "operation_id", "execution_id", "issued_at", "expires_at",
            "issuer", "audience",
        )
        if any(not isinstance(raw[field], str) for field in string_fields):
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")

        if not isinstance(raw["capability_claims"], list) or any(
            not isinstance(value, str) for value in raw["capability_claims"]
        ):
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")
        if not isinstance(raw["authorization_refs"], list) or any(
            not isinstance(value, str) for value in raw["authorization_refs"]
        ):
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")
        if not isinstance(raw["policy_refs"], list) or any(
            not isinstance(value, str) for value in raw["policy_refs"]
        ):
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")
        if not isinstance(raw["evidence_correlation"], (dict, str)):
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")
        signature = raw["signature"]
        if not isinstance(signature, dict):
            raise ExecutionContextValidationError("MALFORMED_SIGNATURE")

        signature_required = (
            "algorithm", "key_id", "value", "signed_claims_digest", "trust_root_id"
        )
        if any(field not in signature for field in signature_required):
            raise ExecutionContextValidationError("MALFORMED_SIGNATURE")
        if any(not isinstance(signature[field], str) for field in signature_required):
            raise ExecutionContextValidationError("MALFORMED_SIGNATURE")
        if type(raw["generation"]) is not int or raw["generation"] < 1:
            raise ExecutionContextValidationError("MALFORMED_CONTEXT")
        _validate_json_value(raw)


def canonicalize_signed_claims(raw: Dict[str, Any]) -> bytes:
    """Canonicalize every issued_context field except signature."""
    claims = {key: value for key, value in raw.items() if key != "signature"}
    _validate_json_value(claims)
    try:
        return json.dumps(
            claims,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ExecutionContextValidationError("MALFORMED_CONTEXT") from exc


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise ExecutionContextValidationError("MALFORMED_CONTEXT")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ExecutionContextValidationError("MALFORMED_CONTEXT")
            _validate_json_value(child)
        return
    if isinstance(value, list):
        for child in value:
            _validate_json_value(child)
        return
    raise ExecutionContextValidationError("MALFORMED_CONTEXT")


def _parse_aware_datetime(value: Any, reason: str) -> datetime:
    if not isinstance(value, str):
        raise ExecutionContextValidationError(reason)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExecutionContextValidationError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionContextValidationError(reason)
    return parsed


def _decode_b64url(value: Any, expected_size: int, reason: str) -> bytes:
    if not isinstance(value, str) or not value or "=" in value or not _B64URL_RE.fullmatch(value):
        raise ExecutionContextValidationError(reason)
    try:
        decoded = base64.b64decode(
            value + ("=" * ((4 - len(value) % 4) % 4)),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as exc:
        raise ExecutionContextValidationError(reason) from exc
    if len(decoded) != expected_size or _encode_b64url(decoded) != value:
        raise ExecutionContextValidationError(reason)
    return decoded


def _encode_b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _load_public_key(value: Any) -> Ed25519PublicKey:
    if not isinstance(value, str) or not value:
        raise ExecutionContextValidationError("TRUST_MATERIAL_UNAVAILABLE")
    try:
        if value.startswith("-----BEGIN"):
            key = load_pem_public_key(value.encode("ascii"))
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("Not an Ed25519 public key")
            raw_key = key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        else:
            raw_key = _decode_b64url(value, ED25519_PUBLIC_KEY_SIZE, "TRUST_MATERIAL_UNAVAILABLE")
        return Ed25519PublicKey.from_public_bytes(raw_key)
    except ExecutionContextValidationError:
        raise
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ExecutionContextValidationError("TRUST_MATERIAL_UNAVAILABLE") from exc
