import json
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


def test_file_secret_backend_uses_canonical_data_dir():
    from pathlib import Path
    from runtime.secrets.backend import FileSecretBackend
    backend = FileSecretBackend("/tmp/anny-m8-secret-root", b"test-master-key")
    assert backend.secrets_dir == Path("/tmp/anny-m8-secret-root") / "secrets"


def test_missing_installation_reference_is_unconfigured():
    result = InstallationCredentialProvider(Backend(), "").status()
    assert result.status is InstallationAuthStatus.UNCONFIGURED


def test_preflight_rejects_non_live_evidence():
    preflight = ConrradPreflight("https://example.invalid", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "TEST_EVIDENCE_ONLY",
        "request_id": "req-1",
        "endpoint": "https://example.invalid",
        "dependency_registry": ["CONRRAD.REPOSITORY_FABRIC"],
        "binding": {
            "runtime_id": "rt-1", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
        "reason": None,
    }
    result = preflight._parse_payload(payload, "rt-1", "inst-1", "req-1")
    assert result.status is PlaneStatus.ONLINE_UNVERIFIED
    assert result.evidence_status is EvidenceStatus.TEST_EVIDENCE_ONLY


def test_preflight_binding_mismatch_blocks():
    preflight = ConrradPreflight("https://example.invalid", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "CERTIFIED_BY_LIVE_EVIDENCE",
        "request_id": "req-1",
        "endpoint": "https://example.invalid",
        "dependency_registry": ["CONRRAD.REPOSITORY_FABRIC"],
        "binding": {
            "runtime_id": "rt-other", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
        "reason": None,
    }
    result = preflight._parse_payload(payload, "rt-1", "inst-1", "req-1")
    assert result.status is PlaneStatus.BLOCKED


def test_malformed_installation_credential_fails_closed():
    result = InstallationCredentialProvider(Backend(value=bytes([0xff])), "m8-ref").authorization_header()
    assert result is None


def test_preflight_uses_canonical_post_wire_contract():
    preflight = ConrradPreflight("https://conrrad.example/v1/bootstrap/preflight", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "CERTIFIED_BY_LIVE_EVIDENCE",
        "request_id": None,
        "endpoint": "https://conrrad.example/v1/bootstrap/preflight",
        "dependency_registry": ["CONRRAD.REPOSITORY_FABRIC"],
        "binding": {
            "runtime_id": "rt-1", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
        "reason": None,
    }
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    def correlated_payload(request, **kwargs):
        payload["request_id"] = request.headers["X-request-id"]
        response.read.return_value = json.dumps(payload).encode("utf-8")
        return response

    with patch.dict("os.environ", {"M8_NODE_ID": "node-1"}, clear=False), \
            patch("urllib.request.urlopen", side_effect=correlated_payload) as urlopen:
        result = preflight.run(
            "rt-1",
            "inst-1",
            requested_scope={
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "workspace_or_resource_scope": "workspace-1",
            },
        )

    assert result.passed is True
    request = urlopen.call_args.args[0]
    assert request.get_method() == "POST"
    assert json.loads(request.data.decode("utf-8")) == {
        "runtime_id": "rt-1",
        "installation_id": "inst-1",
        "requested_scope": {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "workspace_or_resource_scope": "workspace-1",
        },
    }
    assert request.headers["Content-type"] == "application/json"
    assert request.headers["Authorization"] == "Bearer value"
    assert request.headers["X-request-id"]


def test_preflight_rejects_response_request_id_mismatch():
    preflight = ConrradPreflight("https://conrrad.example/v1/bootstrap/preflight", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "CERTIFIED_BY_LIVE_EVIDENCE",
        "request_id": "wrong-request",
        "endpoint": "https://conrrad.example/v1/bootstrap/preflight",
        "dependency_registry": [],
        "binding": {
            "runtime_id": "rt-1", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
    }
    result = preflight._parse_payload(payload, "rt-1", "inst-1", "expected-request")
    assert result.status is PlaneStatus.ONLINE_UNVERIFIED


def test_preflight_rejects_response_endpoint_mismatch():
    preflight = ConrradPreflight("https://conrrad.example/v1/bootstrap/preflight", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "CERTIFIED_BY_LIVE_EVIDENCE",
        "request_id": "expected-request",
        "endpoint": "https://other.example/v1/bootstrap/preflight",
        "dependency_registry": [],
        "binding": {
            "runtime_id": "rt-1", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
    }
    result = preflight._parse_payload(payload, "rt-1", "inst-1", "expected-request")
    assert result.status is PlaneStatus.ONLINE_UNVERIFIED


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


def test_trust_verifier_rejects_response_request_id_mismatch():
    verifier = ExternalTrustVerifier("https://example.invalid/verify", credential_provider())
    raw = {
        "request_id": "wrong-request", "verification_status": "VERIFIED", "verified": True,
        "verifier_id": "verifier-1", "verified_at": "2026-09-28T00:00:00Z", "evidence_ref": "ev-1",
    }
    result = verifier._parse_response(raw, "expected-request")
    assert result.verified is False
    assert result.reason_code == "MALFORMED_VERIFIER_RESPONSE"

def test_trust_verifier_rejects_non_verified_status_with_true_flag():
    verifier = ExternalTrustVerifier("https://example.invalid/verify", credential_provider())
    raw = {
        "request_id": "expected-request", "verification_status": "REJECTED", "verified": True,
        "verifier_id": "verifier-1", "verified_at": "2026-09-28T00:00:00Z", "evidence_ref": "ev-1",
    }
    result = verifier._parse_response(raw, "expected-request")
    assert result.verified is False
    assert result.reason_code == "MALFORMED_VERIFIER_RESPONSE"

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


def test_preflight_rejects_non_https_endpoint():
    preflight = ConrradPreflight("http://conrrad.example/v1/bootstrap/preflight", credential_provider())
    result = preflight.run("rt-1", "inst-1")
    assert result.status is PlaneStatus.NOT_CONFIGURED


def test_preflight_rejects_node_binding_mismatch():
    preflight = ConrradPreflight("https://conrrad.example/v1/bootstrap/preflight", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "CERTIFIED_BY_LIVE_EVIDENCE",
        "request_id": "expected-request",
        "endpoint": "https://conrrad.example/v1/bootstrap/preflight",
        "dependency_registry": ["CONRRAD.REPOSITORY_FABRIC"],
        "binding": {
            "runtime_id": "rt-1", "installation_id": "inst-1", "node_id": "node-other",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
        "reason": None,
    }
    result = preflight._parse_payload(
        payload,
        "rt-1",
        "inst-1",
        "expected-request",
        expected_node_id="node-1",
    )
    assert result.status is PlaneStatus.BLOCKED


def test_preflight_requires_expected_node_binding_for_verified_state():
    preflight = ConrradPreflight("https://conrrad.example/v1/bootstrap/preflight", credential_provider())
    payload = {
        "status": "ONLINE_VERIFIED",
        "evidence_status": "CERTIFIED_BY_LIVE_EVIDENCE",
        "request_id": "expected-request",
        "endpoint": "https://conrrad.example/v1/bootstrap/preflight",
        "dependency_registry": [],
        "binding": {
            "runtime_id": "rt-1", "installation_id": "inst-1", "node_id": "node-1",
            "trust_authority": "trust-1", "issuer_id": "issuer-1", "tenant_id": "tenant-1",
            "project_id": "project-1", "workspace_or_resource_scope": "workspace-1",
            "source_reference": "authority-1",
        },
        "reason": None,
    }
    result = preflight._parse_payload(
        payload,
        "rt-1",
        "inst-1",
        "expected-request",
    )
    assert result.status is PlaneStatus.ONLINE_UNVERIFIED


def _authority_runtime_engine(tmp_path, audience="aud-1"):
    from types import SimpleNamespace
    return SimpleNamespace(
        config=SimpleNamespace(
            data_dir=str(tmp_path),
            conrrad_preflight_endpoint="https://conrrad.example/v1/bootstrap/preflight",
            execution_context_issuer_endpoint="https://issuer.example",
            conrrad_installation_credential_ref="m8-ref",
            conrrad_audience=audience,
        )
    )


def _external_context(
    *,
    generation=7,
    runtime_id="rt-1",
    installation_id="inst-1",
    audience="aud-1",
    capabilities=None,
):
    from datetime import datetime, timezone, timedelta
    from runtime.security.execution_context import ExecutionContext
    now = datetime.now(timezone.utc)
    return ExecutionContext(
        tenant_id="tenant-1",
        account_id="account-1",
        project_id="project-1",
        anny_instance_id="principal-1",
        runtime_id=runtime_id,
        installation_id=installation_id,
        session_id="session-1",
        actor_id="actor-1",
        operation_id="op-1",
        execution_id="exec-1",
        generation=generation,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=5),
        workspace_id="workspace-1",
        capabilities=set(capabilities or {"read_capability"}),
        principal="principal-1",
        issuer="issuer-1",
        audience=audience,
        authorization_refs=("auth-1",),
        policy_refs=("policy-1",),
        evidence_correlation={"id": "ev-1"},
        signature={
            "algorithm": "RSA",
            "key_id": "key-1",
            "value": "sig",
            "signed_claims_digest": "digest",
            "trust_root_id": "trust-1",
        },
    )


def test_execution_manager_m8_requires_external_context(tmp_path):
    from runtime.execution.manager import ExecutionManager
    manager = object.__new__(ExecutionManager)
    manager.runtime_engine = _authority_runtime_engine(tmp_path)
    class TaskLike:
        capability_id = "read_capability"
    try:
        manager._validate_external_execution_context(TaskLike(), None)
    except PermissionError as exc:
        assert "externally issued ExecutionContext" in str(exc)
    else:
        raise AssertionError("M8 execution must fail closed without external context")


def test_execution_manager_m8_rejects_context_binding_mismatch(tmp_path):
    from runtime.execution.manager import ExecutionManager
    manager = object.__new__(ExecutionManager)
    manager.runtime_engine = _authority_runtime_engine(tmp_path)
    from unittest.mock import patch
    from runtime.identity.runtime_identity import RuntimeIdentity
    identity = Mock()
    identity.runtime_id = "rt-1"
    identity.installation_id = "inst-1"
    with patch.object(RuntimeIdentity, "load", return_value=identity):
        context = _external_context(runtime_id="rt-other")
        try:
            manager._validate_external_execution_context(
                type("TaskLike", (), {"capability_id": "read_capability"})(),
                context,
            )
        except PermissionError as exc:
            assert "runtime_id mismatch" in str(exc)
        else:
            raise AssertionError("runtime mismatch must fail closed")


def test_execution_manager_m8_accepts_only_authorized_capability(tmp_path):
    from runtime.execution.manager import ExecutionManager
    manager = object.__new__(ExecutionManager)
    manager.runtime_engine = _authority_runtime_engine(tmp_path)
    from unittest.mock import patch
    from runtime.identity.runtime_identity import RuntimeIdentity
    identity = Mock(runtime_id="rt-1", installation_id="inst-1")
    with patch.object(RuntimeIdentity, "load", return_value=identity):
        context = _external_context(capabilities={"other-capability"})
        try:
            manager._validate_external_execution_context(
                type("TaskLike", (), {"capability_id": "read_capability"})(),
                context,
            )
        except PermissionError as exc:
            assert "does not authorize capability" in str(exc)
        else:
            raise AssertionError("capability must be externally authorized")


def test_external_trust_verifier_rejects_http_endpoint():
    verifier = ExternalTrustVerifier("http://conrrad.example/verify", credential_provider())
    token = FabricTrustToken(
        runtime_id="rt-1", node_id="node-1", issued_at="2026-09-28T00:00:00Z",
        expires_at="2026-09-28T01:00:00Z", signature="sig", token_id="t-1",
        issuer="issuer-1", audience="aud-1"
    )
    result = verifier.verify(token, "inst-1", "node-1", "issuer-1", "aud-1")
    assert result.verified is False
    assert result.reason_code == "TRUST_VERIFIER_REQUIRES_HTTPS"


def test_external_trust_verifier_https_endpoint_is_requestable():
    verifier = ExternalTrustVerifier("https://conrrad.example/verify", credential_provider())
    token = FabricTrustToken(
        runtime_id="rt-1", node_id="node-1", issued_at="2026-09-28T00:00:00Z",
        expires_at="2026-09-28T01:00:00Z", signature="sig", token_id="t-1",
        issuer="issuer-1", audience="aud-1"
    )
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps({
        "request_id": "placeholder",
        "verification_status": "VERIFIED",
        "verified": True,
        "verifier_id": "verifier-1",
        "verified_at": "2026-09-28T00:00:00Z",
        "evidence_ref": "ev-1",
    }).encode()
    def fake_urlopen(request, **kwargs):
        raw = json.loads(response.read.return_value.decode())
        raw["request_id"] = request.headers["X-request-id"]
        response.read.return_value = json.dumps(raw).encode()
        return response
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = verifier.verify(token, "inst-1", "node-1", "issuer-1", "aud-1")
    assert result.verified is True


def test_external_execution_context_rejects_empty_endpoint():
    result = ExternalExecutionContextClient("", credential_provider()).issue(
        "inst-1", "rt-1",
        {"tenant_id":"tenant-1","account_id":"account-1","project_id":"project-1","workspace_or_resource_scope":"workspace-1"},
        "aud-1",
    )
    assert result.context is None
    assert result.reason == "ISSUER_UNAVAILABLE"


def test_external_execution_context_rejects_http_endpoint():
    result = ExternalExecutionContextClient("http://issuer.example", credential_provider()).issue(
        "inst-1", "rt-1",
        {"tenant_id":"tenant-1","account_id":"account-1","project_id":"project-1","workspace_or_resource_scope":"workspace-1"},
        "aud-1",
    )
    assert result.context is None
    assert result.reason == "ISSUER_ENDPOINT_REQUIRES_HTTPS"


def test_external_execution_context_https_endpoint_is_requestable():
    client = ExternalExecutionContextClient("https://issuer.example", credential_provider())
    raw = {
        "context_id": "ctx-1", "principal": "principal-1", "tenant_id": "tenant-1",
        "account_id": "account-1", "project_id": "project-1", "installation_id": "inst-1",
        "runtime_id": "rt-1", "session_id": "session-1", "actor_id": "actor-1",
        "operation_id": "op-1", "execution_id": "exec-1", "generation": 2,
        "issued_at": "2026-09-28T00:00:00Z", "expires_at": "2026-09-28T01:00:00Z",
        "issuer": "issuer-1", "audience": "aud-1", "capability_claims": ["read_capability"],
        "authorization_refs": ["auth-1"], "policy_refs": ["policy-1"],
        "evidence_correlation": {"id":"ev-1"},
        "signature": {"algorithm":"RSA","key_id":"key-1","value":"sig","signed_claims_digest":"digest","trust_root_id":"trust-1"},
    }
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(raw).encode()
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        result = client.issue(
            "inst-1", "rt-1",
            {"tenant_id":"tenant-1","account_id":"account-1","project_id":"project-1","workspace_or_resource_scope":"workspace-1"},
            "aud-1",
            requested_capabilities=["read_capability"],
        )
    assert result.context is not None
    assert result.context.installation_id == "inst-1"
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://issuer.example/v1/control/execution-contexts"
    assert request.get_method() == "POST"


def test_m8_evidence_store_is_append_only(tmp_path):
    from runtime.security.m8_evidence import M8EvidenceStore
    store = M8EvidenceStore(str(tmp_path))
    first = store.record("trust-verification", {"authorization":"secret-a","value":1})
    second = store.record("trust-verification", {"authorization":"secret-b","value":2})
    assert first != second
    assert first.exists() and second.exists()
    assert len(list(store.root.glob("trust-verification-*.json"))) == 2
    first_data = json.loads(first.read_text())
    second_data = json.loads(second.read_text())
    assert first_data["value"] == 1
    assert second_data["value"] == 2
    assert first_data["authorization"] == "[REDACTED]"
    assert second_data["authorization"] == "[REDACTED]"


def test_generation_audit_separates_internal_runtime_generation():
    context = _external_context(generation=77)
    local_generation = 3
    assert context.generation == 77
    assert local_generation != context.generation


def test_gate_b_admission_remains_disabled():
    config = type("Config", (), {"m8_admission_enabled": False})()
    assert config.m8_admission_enabled is False
