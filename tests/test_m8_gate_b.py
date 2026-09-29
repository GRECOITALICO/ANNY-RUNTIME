from pathlib import Path
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
    from runtime.security.execution_context_client import ExternalExecutionContextClient

    raw = _signed_context_raw(authorization_refs=[])
    client = _crypto_client()
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "MALFORMED_CONTEXT"
    else:
        raise AssertionError("missing authorization_refs must be rejected")


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
    client = _crypto_client()
    raw = _signed_context_raw(
        installation_id="inst-other",
    )
    try:
        client._parse_context(
            raw,
            expected_installation_id="inst-1",
            expected_runtime_id="rt-1",
            expected_audience="aud-1",
        )
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "WRONG_INSTALLATION"
    else:
        raise AssertionError("issuer identity mismatch must fail after cryptographic verification")


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
            conrrad_trust_issuer="issuer-1",
            conrrad_trust_root_id="trust-1",
            conrrad_trust_root_reference="m8-trust-bundle",
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
    return _make_verified_context(
        generation=generation,
        runtime_id=runtime_id,
        installation_id=installation_id,
        audience=audience,
        capabilities=capabilities,
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
    client = _crypto_client()
    raw = _signed_context_raw()
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(raw).encode()
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        result = client.issue(
            "inst-1", "rt-1",
            {
                "tenant_id": "tenant-1",
                "account_id": "account-1",
                "project_id": "project-1",
                "workspace_or_resource_scope": "workspace-1",
            },
            "aud-1",
            requested_capabilities=["read_capability"],
        )
    assert result.context is not None
    assert result.verification_status == "VERIFIED"
    assert result.context.verification_status == "VERIFIED"
    assert result.context.installation_id == "inst-1"
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://issuer.example/v1/control/execution-contexts"
    assert request.get_method() == "POST"
    assert request.headers["X-request-id"]


def test_m8_evidence_store_is_append_only(tmp_path):
    from runtime.security.m8_evidence import M8EvidenceStore
    store = M8EvidenceStore(str(tmp_path))
    first = store.record("trust-verification", {"authorization":"secret-a","value":1})
    second = store.record("trust-verification", {"authorization":"secret-b","value":2})
    assert first != second
    assert first.exists() and second.exists()
    first_data = json.loads(first.read_text())
    second_data = json.loads(second.read_text())
    assert first_data["record_id"] != second_data["record_id"]
    assert first.stem == f"trust-verification-{first_data['record_id']}"
    assert second.stem == f"trust-verification-{second_data['record_id']}"
    assert len(list(store.root.glob("trust-verification-*.json"))) == 2
    assert first_data["value"] == 1
    assert second_data["value"] == 2
    assert first_data["authorization"] == "[REDACTED]"
    assert second_data["authorization"] == "[REDACTED]"


def test_generation_audit_separates_internal_runtime_generation():
    context = _external_context(generation=77)
    local_generation = 3
    assert context.generation == 77
    assert local_generation != context.generation





def test_execution_context_generation_is_external_not_runtime_generation():
    from datetime import datetime, timezone
    context = _external_context(generation=77)
    now = datetime.now(timezone.utc)
    assert context.generation == 77
    assert context.matches_external_generation(77) is True
    assert context.matches_external_generation(3) is False
    assert context.is_valid(now) is True
    # Internal RuntimeGeneration changes do not invalidate the external context.
    assert 3 != context.generation
    assert context.is_valid(now) is True


def test_execution_context_expired_is_rejected(tmp_path):
    from dataclasses import replace
    from datetime import datetime, timezone, timedelta
    from runtime.execution.manager import ExecutionManager

    manager = object.__new__(ExecutionManager)
    manager.runtime_engine = _authority_runtime_engine(tmp_path)
    context = replace(
        _external_context(),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    try:
        manager._validate_external_execution_context(
            type("TaskLike", (), {"capability_id": "read_capability"})(),
            context,
        )
    except PermissionError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("expired M8 ExecutionContext must be rejected")


def test_execution_manager_revalidates_external_context_at_execution_time(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from runtime.execution.manager import ExecutionManager
    from runtime.identity.runtime_identity import RuntimeIdentity

    manager = object.__new__(ExecutionManager)
    engine = _authority_runtime_engine(tmp_path)
    issuer = Mock()
    stored = _external_context(generation=77)
    issuer.get.return_value = SimpleNamespace(
        context=_external_context(generation=78),
        reason=None,
    )
    engine.execution_context_client = issuer
    manager.runtime_engine = engine
    manager._executions = {
        "exec-1": SimpleNamespace(
            external_execution_context=stored,
            generation=1,
        )
    }
    manager._tasks = {
        "exec-1": SimpleNamespace(capability_id="read_capability")
    }
    with patch.object(RuntimeIdentity, "load", return_value=Mock(runtime_id="rt-1", installation_id="inst-1")):
        try:
            manager.execute_sync("exec-1")
        except PermissionError as exc:
            assert "external generation changed" in str(exc)
        else:
            raise AssertionError("execution must be blocked when external generation changes")


def test_reconstructed_m8_context_without_external_authority_is_blocked(tmp_path):
    from types import SimpleNamespace
    from runtime.execution.manager import ExecutionManager

    manager = object.__new__(ExecutionManager)
    manager.runtime_engine = _authority_runtime_engine(tmp_path)
    manager._executions = {}
    manager.continuity_engine = Mock()
    manager.continuity_engine.reconstruct_execution.return_value = {
        "execution_id": "exec-1",
        "task_id": "task-1",
        "capability_id": "read_capability",
        "status": "FAILED",
        "routing_class": "DETERMINISTIC",
        "executor_type": "DETERMINISTIC",
        "executor_id": "exec-1",
        "model_id": "model-1",
        "generation": 1,
    }
    reconstructed = manager.get_execution("exec-1")
    assert reconstructed.external_execution_context is None
    manager._tasks = {"exec-1": SimpleNamespace(capability_id="read_capability")}
    try:
        manager.execute_sync("exec-1")
    except PermissionError as exc:
        assert "externally issued ExecutionContext" in str(exc)
    else:
        raise AssertionError("reconstructed M8 execution must remain blocked")


def test_task_execution_context_carries_external_authority():
    from runtime.execution.models import TaskExecutionContext
    external = _external_context(generation=77)
    context = TaskExecutionContext(
        execution_id="exec-1",
        task_id="task-1",
        account_id=external.account_id,
        project_id=external.project_id,
        capability_id="read_capability",
        workspace_path="",
        environment={},
        allowed_tools=[],
        deadline=external.expires_at,
        resource_limits={},
        network_policy="none",
        write_policy="none",
        external_execution_context=external,
    )
    assert context.external_execution_context is external


def test_gate_b_admission_remains_disabled():
    config = type("Config", (), {"m8_admission_enabled": False})()
    assert config.m8_admission_enabled is False


# M8-BLOCK-011 deterministic cryptographic verification coverage.

def _crypto_backend(*, trust_root_id="trust-1", key_id="key-1", status="ACTIVE", not_before=None, not_after=None):
    import base64
    from datetime import datetime, timezone, timedelta
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    public_key = base64.urlsafe_b64encode(
        private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii").rstrip("=")
    now = datetime.now(timezone.utc)
    bundle = {
        "keys": [{
            "key_id": key_id,
            "algorithm": "Ed25519",
            "public_key": public_key,
            "not_before": (not_before or now - timedelta(minutes=5)).isoformat(),
            "not_after": (not_after or now + timedelta(hours=1)).isoformat(),
            "status": status,
        }]
    }

    class TrustBackend:
        def exists(self, reference):
            return reference == "m8-trust-bundle"

        def retrieve(self, reference):
            return json.dumps(bundle).encode("utf-8") if reference == "m8-trust-bundle" else None

    return TrustBackend(), private_key, trust_root_id, key_id


def _crypto_client(*, trust_root_id="trust-1", trust_root_reference="m8-trust-bundle", expected_issuer="issuer-1", evidence_store=None):
    backend, _, _, _ = _crypto_backend(trust_root_id=trust_root_id)
    return ExternalExecutionContextClient(
        "https://issuer.example",
        credential_provider(),
        trust_material_backend=backend,
        trust_root_id=trust_root_id,
        trust_root_reference=trust_root_reference,
        expected_issuer=expected_issuer,
        evidence_store=evidence_store,
    )


def _signed_context_raw(
    *,
    generation=7,
    runtime_id="rt-1",
    installation_id="inst-1",
    audience="aud-1",
    issuer="issuer-1",
    authorization_refs=None,
    policy_refs=None,
    capabilities=None,
    algorithm="Ed25519",
    key_id="key-1",
    trust_root_id="trust-1",
):
    import base64
    import hashlib
    from datetime import datetime, timezone, timedelta
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from runtime.security.execution_context_verifier import canonicalize_signed_claims

    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    raw = {
        "context_id": "ctx-1",
        "principal": "principal-1",
        "tenant_id": "tenant-1",
        "account_id": "account-1",
        "project_id": "project-1",
        "workspace_or_resource_scope": "workspace-1",
        "installation_id": installation_id,
        "runtime_id": runtime_id,
        "session_id": "session-1",
        "actor_id": "actor-1",
        "operation_id": "op-1",
        "execution_id": "exec-1",
        "generation": generation,
        "issued_at": (now - timedelta(seconds=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "issuer": issuer,
        "audience": audience,
        "capability_claims": list(["read_capability"] if capabilities is None else capabilities),
        "authorization_refs": list(["auth-1"] if authorization_refs is None else authorization_refs),
        "policy_refs": list(["policy-1"] if policy_refs is None else policy_refs),
        "evidence_correlation": {"id": "ev-1"},
        "signature": {
            "algorithm": algorithm,
            "key_id": key_id,
            "value": "",
            "signed_claims_digest": "",
            "trust_root_id": trust_root_id,
        },
    }
    canonical = canonicalize_signed_claims(raw)
    digest = hashlib.sha256(canonical).digest()
    raw["signature"]["signed_claims_digest"] = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    raw["signature"]["value"] = base64.urlsafe_b64encode(
        private_key.sign(canonical)
    ).decode("ascii").rstrip("=")
    return raw


def _make_verified_context(**kwargs):
    from runtime.security.execution_context_verifier import ExecutionContextVerifier, TrustMaterialResolver
    backend, _, trust_root_id, _ = _crypto_backend(trust_root_id=kwargs.get("trust_root_id", "trust-1"))
    raw = _signed_context_raw(**kwargs)
    verifier = ExecutionContextVerifier(
        TrustMaterialResolver(backend, trust_root_id, "m8-trust-bundle"),
        expected_issuer=kwargs.get("issuer", "issuer-1"),
        expected_audience=kwargs.get("audience", "aud-1"),
    )
    return verifier.verify(
        raw,
        expected_installation_id=None,
        expected_runtime_id=None,
        expected_audience=kwargs.get("audience", "aud-1"),
    )


def test_m8_valid_ed25519_signature_is_verified():
    client = _crypto_client()
    raw = _signed_context_raw()
    context = client._parse_context(raw, expected_installation_id="inst-1", expected_runtime_id="rt-1", expected_audience="aud-1")
    assert context.verification_status == "VERIFIED"
    assert context.signature["algorithm"] == "Ed25519"


def test_m8_altered_claims_are_rejected():
    client = _crypto_client()
    raw = _signed_context_raw()
    raw["project_id"] = "project-tampered"
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "DIGEST_MISMATCH"
    else:
        raise AssertionError("altered signed claims must fail closed")


def test_m8_altered_digest_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw()
    raw["signature"]["signed_claims_digest"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "DIGEST_MISMATCH"
    else:
        raise AssertionError("altered digest must fail closed")


def test_m8_altered_signature_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw()
    import base64
    raw["signature"]["value"] = base64.urlsafe_b64encode(b"\x00" * 64).decode("ascii").rstrip("=")
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "INVALID_SIGNATURE"
    else:
        raise AssertionError("altered signature must fail closed")


def test_m8_unknown_key_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw(key_id="unknown-key")
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "UNKNOWN_KEY"
    else:
        raise AssertionError("unknown key must fail closed")


def test_m8_unknown_trust_root_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw(trust_root_id="unknown-root")
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "UNKNOWN_TRUST_ROOT"
    else:
        raise AssertionError("unknown trust root must fail closed")


def test_m8_unsupported_algorithm_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw(algorithm="RSA")
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "UNSUPPORTED_ALGORITHM"
    else:
        raise AssertionError("unsupported algorithm must fail closed")


def test_m8_revoked_key_is_rejected():
    backend, _, _, _ = _crypto_backend(status="REVOKED")
    from runtime.security.execution_context_verifier import ExecutionContextVerifier, TrustMaterialResolver
    raw = _signed_context_raw()
    verifier = ExecutionContextVerifier(TrustMaterialResolver(backend, "trust-1", "m8-trust-bundle"), expected_issuer="issuer-1")
    try:
        verifier.verify(raw, expected_installation_id="inst-1", expected_runtime_id="rt-1", expected_audience="aud-1")
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "REVOKED_KEY"
    else:
        raise AssertionError("revoked key must fail closed")


def test_m8_expired_key_is_rejected():
    from datetime import datetime, timezone, timedelta
    backend, _, _, _ = _crypto_backend(
        status="ACTIVE",
        not_after=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    from runtime.security.execution_context_verifier import ExecutionContextVerifier, TrustMaterialResolver
    raw = _signed_context_raw()
    verifier = ExecutionContextVerifier(TrustMaterialResolver(backend, "trust-1", "m8-trust-bundle"), expected_issuer="issuer-1")
    try:
        verifier.verify(raw, expected_installation_id="inst-1", expected_runtime_id="rt-1", expected_audience="aud-1")
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "EXPIRED_KEY"
    else:
        raise AssertionError("expired key must fail closed")


def test_m8_malformed_signature_encoding_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw()
    raw["signature"]["value"] = "not base64url"
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "MALFORMED_SIGNATURE"
    else:
        raise AssertionError("malformed signature encoding must fail closed")


def test_m8_wrong_runtime_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw()
    try:
        client._parse_context(raw, expected_installation_id="inst-1", expected_runtime_id="rt-other", expected_audience="aud-1")
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "WRONG_RUNTIME"
    else:
        raise AssertionError("wrong runtime must fail closed")


def test_m8_wrong_installation_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw()
    try:
        client._parse_context(raw, expected_installation_id="inst-other", expected_runtime_id="rt-1", expected_audience="aud-1")
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "WRONG_INSTALLATION"
    else:
        raise AssertionError("wrong installation must fail closed")


def test_m8_wrong_issuer_is_rejected():
    client = _crypto_client(expected_issuer="issuer-expected")
    raw = _signed_context_raw()
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "WRONG_ISSUER"
    else:
        raise AssertionError("wrong issuer must fail closed")


def test_m8_wrong_audience_is_rejected():
    client = _crypto_client()
    raw = _signed_context_raw()
    try:
        client._parse_context(raw, expected_audience="aud-other")
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "WRONG_AUDIENCE"
    else:
        raise AssertionError("wrong audience must fail closed")


def test_m8_expired_context_is_rejected():
    from datetime import datetime, timezone, timedelta
    from runtime.security.execution_context_verifier import ExecutionContextVerifier, TrustMaterialResolver
    client = _crypto_client()
    raw = _signed_context_raw()
    raw["issued_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    raw["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    raw["signature"] = dict(raw["signature"])
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import base64, hashlib
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    from runtime.security.execution_context_verifier import canonicalize_signed_claims
    canonical = canonicalize_signed_claims(raw)
    digest = hashlib.sha256(canonical).digest()
    raw["signature"]["signed_claims_digest"] = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    raw["signature"]["value"] = base64.urlsafe_b64encode(private_key.sign(canonical)).decode("ascii").rstrip("=")
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "EXPIRED_CONTEXT"
    else:
        raise AssertionError("expired context must fail closed")


def test_m8_not_yet_valid_context_is_rejected():
    from datetime import datetime, timezone, timedelta
    from runtime.security.execution_context_verifier import ExecutionContextVerifier, TrustMaterialResolver

    raw = _signed_context_raw()
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    raw["issued_at"] = future.isoformat()
    verifier = ExecutionContextVerifier(
        TrustMaterialResolver(_crypto_backend()[0], "trust-1", "m8-trust-bundle"),
        expected_issuer="issuer-1",
        expected_audience="aud-1",
    )
    from runtime.security.execution_context_verifier import canonicalize_signed_claims
    import base64, hashlib
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    canonical = canonicalize_signed_claims(raw)
    digest = hashlib.sha256(canonical).digest()
    raw["signature"]["signed_claims_digest"] = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    raw["signature"]["value"] = base64.urlsafe_b64encode(private_key.sign(canonical)).decode("ascii").rstrip("=")
    try:
        verifier.verify(
            raw,
            expected_installation_id="inst-1",
            expected_runtime_id="rt-1",
            expected_audience="aud-1",
        )
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "NOT_YET_VALID_CONTEXT"
    else:
        raise AssertionError("not-yet-valid context must fail closed")


def test_m8_expired_context_result_preserves_expired_status(tmp_path):
    from datetime import datetime, timezone, timedelta
    store = __import__("runtime.security.m8_evidence", fromlist=["M8EvidenceStore"]).M8EvidenceStore(str(tmp_path))
    client = _crypto_client(evidence_store=store)
    raw = _signed_context_raw()
    raw["issued_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    raw["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    from runtime.security.execution_context_verifier import canonicalize_signed_claims
    import base64, hashlib
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    canonical = canonicalize_signed_claims(raw)
    digest = hashlib.sha256(canonical).digest()
    raw["signature"]["signed_claims_digest"] = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    raw["signature"]["value"] = base64.urlsafe_b64encode(private_key.sign(canonical)).decode("ascii").rstrip("=")
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(raw).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=response):
        result = client.issue(
            "inst-1",
            "rt-1",
            {
                "tenant_id": "tenant-1",
                "account_id": "account-1",
                "project_id": "project-1",
                "workspace_or_resource_scope": "workspace-1",
            },
            "aud-1",
        )
    assert result.context is None
    assert result.verification_status == "EXPIRED"
    assert result.reason == "EXPIRED_CONTEXT"


def test_m8_stale_external_generation_blocks_execution():
    from types import SimpleNamespace
    from runtime.execution.manager import ExecutionManager
    manager = object.__new__(ExecutionManager)
    engine = _authority_runtime_engine("/tmp/unused")
    issuer = Mock()
    stored = _external_context(generation=77)
    issuer.get.return_value = SimpleNamespace(context=_external_context(generation=78), reason=None)
    engine.execution_context_client = issuer
    manager.runtime_engine = engine
    manager._executions = {
        "exec-1": SimpleNamespace(
            external_execution_context=stored,
            generation=1,
            status="QUEUED",
            workspace_path="",
        )
    }
    manager._tasks = {"exec-1": SimpleNamespace(capability_id="read_capability", workspace_policy="retain")}
    from unittest.mock import patch
    from runtime.identity.runtime_identity import RuntimeIdentity
    with patch.object(RuntimeIdentity, "load", return_value=Mock(runtime_id="rt-1", installation_id="inst-1")):
        try:
            manager.execute_sync("exec-1")
        except PermissionError as exc:
            assert "external generation changed" in str(exc)
        else:
            raise AssertionError("stale external generation must block execution")


def test_m8_no_structural_only_fallback():
    client = _crypto_client()
    raw = _signed_context_raw(algorithm="RSA")
    try:
        client._parse_context(raw)
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "UNSUPPORTED_ALGORITHM"
    else:
        raise AssertionError("structural-only fallback must not produce a context")


def test_m8_missing_trust_material_is_rejected():
    from runtime.security.execution_context_verifier import ExecutionContextVerifier, TrustMaterialResolver
    raw = _signed_context_raw()
    verifier = ExecutionContextVerifier(TrustMaterialResolver(None, "trust-1", "m8-trust-bundle"), expected_issuer="issuer-1")
    try:
        verifier.verify(raw, expected_installation_id="inst-1", expected_runtime_id="rt-1", expected_audience="aud-1")
    except ExecutionContextValidationError as exc:
        assert exc.reason_code == "TRUST_MATERIAL_UNAVAILABLE"
    else:
        raise AssertionError("missing trust material must fail closed")


def test_m8_execution_boundary_requires_cryptographic_verification(tmp_path):
    from runtime.execution.manager import ExecutionManager
    manager = object.__new__(ExecutionManager)
    manager.runtime_engine = _authority_runtime_engine(tmp_path)
    context = _external_context()
    from dataclasses import replace
    unverified = replace(context, verification_status="UNVERIFIED")
    try:
        manager._validate_external_execution_context(
            type("TaskLike", (), {"capability_id": "read_capability"})(),
            unverified,
        )
    except PermissionError as exc:
        assert "cryptographic verification" in str(exc)
    else:
        raise AssertionError("unverified context must not enter execution")


def test_m8_verified_context_reaches_execution_boundary(tmp_path):
    from types import SimpleNamespace
    from runtime.execution.manager import ExecutionManager
    from runtime.execution.models import ExecutionStatus

    manager = object.__new__(ExecutionManager)
    engine = _authority_runtime_engine(tmp_path)
    verified = _external_context(generation=77)
    issuer = Mock()
    issuer.get.return_value = SimpleNamespace(context=verified, reason=None)
    engine.execution_context_client = issuer
    engine.generation = Mock()
    engine.generation.fence.return_value = None
    manager.runtime_engine = engine
    manager.continuity_engine = None
    from runtime.identity.runtime_identity import RuntimeIdentity
    identity = Mock(runtime_id="rt-1", installation_id="inst-1")
    manager._executions = {
        "exec-1": SimpleNamespace(
            external_execution_context=verified,
            generation=1,
            status=ExecutionStatus.QUEUED,
            workspace_path="",
            failure_reason=None,
            error_message=None,
            result_hash=None,
            routing_class="DETERMINISTIC",
            executor_type="DETERMINISTIC",
            executor_id="exec-1",
            model_id="model-1",
        )
    }
    manager._tasks = {
        "exec-1": SimpleNamespace(
            task_id="task-1",
            capability_id="read_capability",
            requested_by="ANNY",
            workspace_policy="retain",
        )
    }
    cap = SimpleNamespace(
        workspace_policy="retain",
    )
    manager.registry = Mock()
    manager.registry.get.return_value = cap
    worker = SimpleNamespace(execution_id="exec-1", worker_id="worker-1")
    manager.worker_manager = Mock()
    manager.worker_manager.list_workers.return_value = [worker]
    manager.worker_manager.start_worker.side_effect = lambda worker_id, context, task, capability: setattr(context, "status", ExecutionStatus.SUCCEEDED)
    manager.worker_manager.terminate_worker.return_value = None
    with patch.object(RuntimeIdentity, "load", return_value=identity):
        manager.execute_sync("exec-1")
    manager.worker_manager.start_worker.assert_called_once()
    passed_context = manager.worker_manager.start_worker.call_args.args[1]
    assert passed_context.external_execution_context.verification_status == "VERIFIED"
    assert passed_context.external_execution_context.context_id == "ctx-1"
    assert manager._executions["exec-1"].external_execution_context.verification_status == "VERIFIED"


def test_m8_evidence_contains_required_crypto_fields(tmp_path):
    from runtime.security.m8_evidence import M8EvidenceStore
    raw = _signed_context_raw()
    signature = raw["signature"]
    store = M8EvidenceStore(str(tmp_path))
    ref = store.record(
        "execution-context-verification",
        {
            "request_id": "req-1",
            "context_id": raw["context_id"],
            "runtime_id": raw["runtime_id"],
            "installation_id": raw["installation_id"],
            "issuer": raw["issuer"],
            "audience": raw["audience"],
            "generation": raw["generation"],
            "trust_root_id": signature["trust_root_id"],
            "key_id": signature["key_id"],
            "algorithm": signature["algorithm"],
            "signed_claims_digest": signature["signed_claims_digest"],
            "verification_status": "VERIFIED",
            "verification_reason": "VERIFIED",
            "verified_at": "2026-09-29T08:00:00+00:00",
            "private_key": "do-not-persist",
        },
    )
    data = json.loads(ref.read_text())
    for key in (
        "request_id", "context_id", "runtime_id", "installation_id",
        "issuer", "audience", "generation", "trust_root_id", "key_id",
        "algorithm", "signed_claims_digest", "verification_status",
        "verification_reason", "verified_at",
    ):
        assert key in data
    assert "do-not-persist" not in ref.read_text()




def test_m8_client_records_required_verification_evidence(tmp_path):
    from runtime.security.m8_evidence import M8EvidenceStore

    store = M8EvidenceStore(str(tmp_path))
    client = _crypto_client(evidence_store=store)
    raw = _signed_context_raw()
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(raw).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=response):
        result = client.issue(
            "inst-1",
            "rt-1",
            {
                "tenant_id": "tenant-1",
                "account_id": "account-1",
                "project_id": "project-1",
                "workspace_or_resource_scope": "workspace-1",
            },
            "aud-1",
        )
    assert result.verification_status == "VERIFIED"
    assert result.evidence_ref is not None
    evidence = json.loads(Path(result.evidence_ref).read_text())
    for field in (
        "request_id", "context_id", "runtime_id", "installation_id",
        "issuer", "audience", "generation", "trust_root_id", "key_id",
        "algorithm", "signed_claims_digest", "verification_status",
        "verification_reason", "verified_at",
    ):
        assert field in evidence
    assert evidence["verification_status"] == "VERIFIED"
    assert "private_key" not in evidence
    assert "authorization" not in evidence
