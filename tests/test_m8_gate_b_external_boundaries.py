import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from runtime.fabric.trust_verifier import (
    ExternalFabricTrustVerifier,
    TrustVerificationStatus,
)
from runtime.security.external_context_issuer import (
    ExternalExecutionContextIssuerClient,
    ExecutionContextIssuerError,
)


def test_trust_result_never_infers_verified():
    payload = {"verification_status": "VERIFIED", "verified": False}
    result = __import__("runtime.fabric.trust_verifier", fromlist=["TrustVerificationResult"]).TrustVerificationResult.from_payload(payload)
    assert result.status is TrustVerificationStatus.VERIFIED
    assert result.verified is False


def test_trust_result_requires_explicit_verified_true():
    payload = {"verification_status": "UNKNOWN", "verified": True}
    result = __import__("runtime.fabric.trust_verifier", fromlist=["TrustVerificationResult"]).TrustVerificationResult.from_payload(payload)
    assert result.status is TrustVerificationStatus.UNKNOWN
    assert result.verified is False


def test_trust_verifier_requires_https():
    with pytest.raises(Exception):
        ExternalFabricTrustVerifier("http://verifier.invalid")


def test_trust_verifier_requires_installation_credential():
    client = ExternalFabricTrustVerifier("https://verifier.invalid")
    with pytest.raises(Exception):
        client.verify(
            request_id="r1",
            correlation_id="c1",
            nonce="n1",
            runtime_id="rt1",
            installation_id="inst1",
            trust_token={"token_id": "t1"},
            expected_node_id="node1",
            expected_issuer="issuer1",
            expected_audience="CONRRAD.M8.NONPROD.001",
            observed_at="2026-09-28T02:00:00Z",
            installation_credential="",
        )


def test_execution_issuer_requires_https():
    with pytest.raises(Exception):
        ExternalExecutionContextIssuerClient("http://issuer.invalid")


def test_execution_context_parser_rejects_missing_claims():
    client = ExternalExecutionContextIssuerClient("https://issuer.invalid")
    with pytest.raises(ExecutionContextIssuerError):
        client._parse_issued_context({"context_id": "ctx1"}, expected_runtime_id="rt1")


def test_execution_context_parser_rejects_wrong_runtime():
    client = ExternalExecutionContextIssuerClient("https://issuer.invalid")
    now = datetime.now(timezone.utc)
    payload = {
        "context_id": "ctx1",
        "tenant_id": "tenant",
        "account_id": "acct",
        "project_id": "proj",
        "installation_id": "inst",
        "runtime_id": "other-runtime",
        "session_id": "sess",
        "actor_id": "actor",
        "operation_id": "op",
        "execution_id": "exec",
        "generation": 1,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "issuer": "issuer",
        "audience": "CONRRAD.M8.NONPROD.001",
        "capability_claims": [],
        "signature": {
            "algorithm": "EdDSA",
            "key_id": "k1",
            "value": "sig",
            "trust_root_id": "root1",
        },
    }
    with pytest.raises(ExecutionContextIssuerError):
        client._parse_issued_context(payload, expected_runtime_id="rt1")


def test_installation_credential_provider_fails_closed_when_unconfigured(tmp_path):
    from runtime.security.installation_credential import (
        InstallationCredentialError,
        InstallationCredentialProvider,
    )
    from runtime.secrets.backend import FileSecretBackend

    backend = FileSecretBackend(str(tmp_path), b"master-key")
    provider = InstallationCredentialProvider(
        backend,
        credential_ref="installation-credential",
        runtime_id="rt1",
        installation_id="inst1",
    )
    assert provider.is_configured() is False
    with pytest.raises(InstallationCredentialError, match="UNCONFIGURED"):
        provider.get_credential()


def test_installation_binding_description_never_contains_credential(tmp_path):
    from runtime.security.installation_credential import InstallationCredentialProvider
    from runtime.secrets.backend import FileSecretBackend

    backend = FileSecretBackend(str(tmp_path), b"master-key")
    backend.store("installation-credential", b"secret-value")
    provider = InstallationCredentialProvider(
        backend,
        credential_ref="installation-credential",
        runtime_id="rt1",
        installation_id="inst1",
    )
    metadata = provider.describe_binding()
    assert "secret-value" not in json.dumps(metadata)
    assert metadata["runtime_id"] == "rt1"
    assert metadata["installation_id"] == "inst1"


def test_trust_verifier_rejects_partial_token_before_network():
    client = ExternalFabricTrustVerifier("https://verifier.invalid")
    with pytest.raises(Exception, match="missing required claims"):
        client.verify(
            request_id="r1",
            correlation_id="c1",
            nonce="n1",
            runtime_id="rt1",
            installation_id="inst1",
            trust_token={
                "issued_at": "2026-09-28T02:00:00Z",
                "expires_at": "2026-09-28T03:00:00Z",
                "runtime_id": "rt1",
                "node_id": "node1",
                "signature": "sig",
            },
            expected_node_id="node1",
            expected_issuer="issuer1",
            expected_audience="CONRRAD.M8.NONPROD.001",
            observed_at="2026-09-28T02:00:00Z",
            installation_credential="cred",
        )


def test_execution_context_parser_rejects_wrong_installation_or_audience():
    client = ExternalExecutionContextIssuerClient("https://issuer.invalid")
    now = datetime.now(timezone.utc)
    payload = {
        "context_id": "ctx1",
        "tenant_id": "tenant",
        "account_id": "acct",
        "project_id": "proj",
        "installation_id": "inst-other",
        "runtime_id": "rt1",
        "session_id": "sess",
        "actor_id": "actor",
        "operation_id": "op",
        "execution_id": "exec",
        "generation": 1,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "issuer": "issuer",
        "audience": "WRONG-AUDIENCE",
        "capability_claims": [],
        "signature": {
            "algorithm": "EdDSA",
            "key_id": "k1",
            "value": "sig",
            "trust_root_id": "root1",
        },
    }
    with pytest.raises(ExecutionContextIssuerError):
        client._parse_issued_context(
            payload,
            expected_runtime_id="rt1",
            expected_installation_id="inst1",
            expected_audience="CONRRAD.M8.NONPROD.001",
        )
