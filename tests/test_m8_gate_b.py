import urllib.error
from unittest.mock import Mock, patch

from runtime.conrrad.preflight import ConrradPreflight, EvidenceStatus, PlaneStatus
from runtime.fabric.models import FabricTrustToken
from runtime.fabric.trust_verifier import ExternalTrustVerifier
from runtime.security.execution_context_client import ExecutionContextValidationError, ExternalExecutionContextClient
from runtime.security.installation_auth import InstallationCredentialProvider, InstallationAuthStatus
from runtime.bootstrap.planes import ThreePlaneBootstrap


class Backend:
    def __init__(self, value=b"value"):
        self.value = value

    def exists(self, reference):
        return reference == "m8-ref"

    def retrieve(self, reference):
        return self.value if reference == "m8-ref" else None


def credential_provider():
    return InstallationCredentialProvider(Backend(), "m8-ref")


def test_missing_installation_reference_is_unconfigured():
    result = InstallationCredentialProvider(Backend(), "").status()
    assert result.status is InstallationAuthStatus.UNCONFIGURED


def test_preflight_rejects_non_live_evidence():
    preflight = ConrradPreflight("https://example.invalid", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "TEST_EVIDENCE_ONLY",
        "dependency_registry": ["CONRRAD.REPOSITORY_FABRIC"],
        "binding": {
            "runtime_id": "rt-1", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
    }
    result = preflight._parse_payload(payload, "rt-1", "inst-1", "req-1")
    assert result.status is PlaneStatus.ONLINE_UNVERIFIED
    assert result.evidence_status is EvidenceStatus.TEST_EVIDENCE_ONLY


def test_preflight_binding_mismatch_blocks():
    preflight = ConrradPreflight("https://example.invalid", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "CERTIFIED_BY_LIVE_EVIDENCE",
        "dependency_registry": ["CONRRAD.REPOSITORY_FABRIC"],
        "binding": {
            "runtime_id": "rt-other", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
    }
    result = preflight._parse_payload(payload, "rt-1", "inst-1", "req-1")
    assert result.status is PlaneStatus.BLOCKED


def test_local_trust_is_never_verified():
    token = FabricTrustToken(
        runtime_id="rt-1", node_id="node-1", issued_at="2026-09-28T00:00:00Z",
        expires_at="2026-09-28T01:00:00Z", signature="sig", token_id="t-1",
        issuer="issuer-1", audience="aud-1"
    )
    assert token.verified is False
    assert token.verification_status == "UNVERIFIED"


def test_verifier_unavailable_is_unknown():
    verifier = ExternalTrustVerifier("https://example.invalid/verify", credential_provider())
    token = FabricTrustToken(
        runtime_id="rt-1", node_id="node-1", issued_at="2026-09-28T00:00:00Z",
        expires_at="2026-09-28T01:00:00Z", signature="sig", token_id="t-1",
        issuer="issuer-1", audience="aud-1"
    )
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        result = verifier.verify(token, "inst-1", "node-1", "issuer-1", "aud-1")
    assert result.verification_status == "UNKNOWN"
    assert result.verified is False


def test_execution_context_requires_all_authority_refs():
    client = ExternalExecutionContextClient("https://example.invalid/issuer", credential_provider())
    raw = {
        "context_id": "ctx-1", "principal": "principal-1", "tenant_id": "tenant-1",
        "account_id": "account-1", "project_id": "project-1", "installation_id": "inst-1",
        "runtime_id": "rt-1", "session_id": "session-1", "actor_id": "actor-1",
        "operation_id": "op-1", "execution_id": "exec-1", "generation": 1,
        "issued_at": "2026-09-28T00:00:00Z", "expires_at": "2026-09-28T01:00:00Z",
        "issuer": "issuer-1", "audience": "aud-1", "capability_claims": ["cap-1"],
        "authorization_refs": [], "policy_refs": ["policy-1"],
        "evidence_correlation": {"id": "ev-1"},
        "signature": {"algorithm": "RSA", "key_id": "key-1", "value": "sig",
                       "signed_claims_digest": "digest", "trust_root_id": "trust-1"}
    }
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert "authorization_refs" in str(exc)
    else:
        raise AssertionError("expected authority-reference validation failure")


def test_preflight_failure_blocks_before_github():
    github = Mock()
    preflight = Mock(
        passed=False,
        status=PlaneStatus.BLOCKED,
        evidence_status=EvidenceStatus.UNKNOWN,
        reason="dependency unavailable",
    )
    bootstrap = ThreePlaneBootstrap(
        data_dir="/tmp/anny-m8-test",
        github_client=github,
        fabric_client=None,
        continuity_engine=Mock(),
        preflight_result=preflight,
        installation_auth=credential_provider(),
        external_trust_verifier=None,
    )
    report = bootstrap.resolve()
    assert report.anny_ready is False
    github.get_repository.assert_not_called()
    github.list_organizations.assert_not_called()


def test_issuer_response_installation_runtime_audience_mismatch_rejected():
    client = ExternalExecutionContextClient("https://example.invalid/issuer", credential_provider())
    raw = {
        "context_id": "ctx-1", "principal": "principal-1", "tenant_id": "tenant-1",
        "account_id": "account-1", "project_id": "project-1", "installation_id": "inst-other",
        "runtime_id": "rt-other", "session_id": "session-1", "actor_id": "actor-1",
        "operation_id": "op-1", "execution_id": "exec-1", "generation": 1,
        "issued_at": "2026-09-28T00:00:00Z", "expires_at": "2026-09-28T01:00:00Z",
        "issuer": "issuer-1", "audience": "other-audience", "capability_claims": ["cap-1"],
        "authorization_refs": ["auth-1"], "policy_refs": ["policy-1"],
        "evidence_correlation": {"id": "ev-1"},
        "signature": {"algorithm": "RSA", "key_id": "key-1", "value": "sig",
                       "signed_claims_digest": "digest", "trust_root_id": "trust-1"}
    }
    try:
        client._parse_context(
            raw,
            expected_installation_id="inst-1",
            expected_runtime_id="rt-1",
            expected_audience="aud-1",
        )
    except ExecutionContextValidationError as exc:
        assert "installation_id" in str(exc)
    else:
        raise AssertionError("expected issuer identity mismatch")
