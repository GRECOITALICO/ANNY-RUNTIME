"""
Bootstrap Gate Tests — Positive and MANDATORY Negative Cases.

RULE: Tests must verify failure semantics explicitly.
      ANNY_READY=True requires ALL MANDATORY_GATES to pass.
      Individual gate failures must block ANNY_READY.
      Status must be BLOCKED, never DEGRADED.
"""
import pytest
import urllib.error
from unittest.mock import Mock, MagicMock, patch
from runtime.bootstrap.planes import ThreePlaneBootstrap
from runtime.bootstrap.report import BootstrapReport, ChatGPTBootstrapFormatter
from runtime.bootstrap.gates import ReadinessGate, MANDATORY_GATES
from runtime.identity.runtime_identity import RuntimeIdentity
from runtime.fabric.client import FabricError, FabricAdmissionResult
from runtime.fabric.models import FabricHealthResult, FabricNode, FabricTenant, FabricTrustToken
from runtime.core.engine import RuntimeEngine
from runtime.core.config import RuntimeConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_identity():
    ident = Mock(spec=RuntimeIdentity)
    ident.runtime_id = "RT-1234"
    ident._private_key = b"dummy_key_bytes"
    ident.origin_commit = "abc1234def5678"
    return ident


@pytest.fixture
def mock_github():
    gh = Mock()
    gh.get_authenticated_principal.return_value = {"login": "dummy_user"}
    gh.list_organizations.return_value = [{"login": "GRECOITALICO"}]
    return gh


@pytest.fixture
def mock_fabric():
    fab = Mock()
    fab.org = "GRECOITALICO"
    fab.repo = "ANNY-OPERATIONAL"
    fab.probe_reachability.return_value = (True, 45.0, None)
    fab.read_node_config.return_value = FabricNode(
        "NODE-001", "GRECOITALICO", "ANNY-OPERATIONAL",
        "REPOSITORY_FABRIC", "2026-09-15T00:00:00Z"
    )
    fab.node_json_exists_at_remote_head.return_value = (True, "sha_abc123")
    fab.read_tenant_binding.return_value = FabricTenant(
        "TENANT-1", "RT-1234", [], "2026-09-15T00:00:00Z"
    )
    fab.issue_trust_token.return_value = FabricTrustToken(
        "RT-1234", "NODE-001",
        "2026-09-15T00:00:00Z", "2026-09-15T01:00:00Z",
        "dummy_sig_here_xyz", True
    )
    fab.validate_provenance.return_value = (True, None)
    fab.check_admission.return_value = FabricAdmissionResult(
        FabricAdmissionResult.ALLOW, "Explicit ALLOW from fabric/admissions/RT-1234.json"
    )
    fab.read_fabric_state.return_value = {
        "version": "1.0",
        "registered_runtimes": ["RT-1234"],
        "status": "ACTIVE"
    }
    return fab


@pytest.fixture
def mock_continuity():
    cont = Mock()
    cont.status = {"state": "COHERENT"}
    return cont


@pytest.fixture
def mock_config():
    cfg = Mock()
    cfg.fabric_org = "GRECOITALICO"
    cfg.fabric_repo = "ANNY-OPERATIONAL"
    cfg.data_dir = "/tmp"
    return cfg


def _make_bootstrap(mock_identity, mock_github, mock_fabric, mock_continuity, mock_config=None):
    """Helper: build ThreePlaneBootstrap with RT probe mocked as reachable."""
    import urllib.request, json as _json, io
    resp_data = _json.dumps({
        "anny_ready": True,
        "state": "WAITING_FOR_SESSION",
        "fabric_org": "GRECOITALICO",
        "fabric_repo": "ANNY-OPERATIONAL",
    }).encode()
    mock_resp = Mock()
    mock_resp.status = 200
    mock_resp.read.return_value = resp_data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = Mock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        bs = ThreePlaneBootstrap(
            data_dir="/tmp",
            github_client=mock_github,
            fabric_client=mock_fabric,
            continuity_engine=mock_continuity,
            config=mock_config,
        )
    return bs


# ---------------------------------------------------------------------------
# NEGATIVE TESTS — Each mandatory gate must individually block ANNY_READY
# ---------------------------------------------------------------------------

class TestNegative_FabricUnreachable:
    """NEGATIVE: Fabric unreachable → ANNY_READY=False, BLOCKED."""

    def test_fabric_unreachable_blocks_ready(
        self, mock_identity, mock_github, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: mock_identity
        )
        mock_fabric.probe_reachability.return_value = (False, 0.0, "Connection refused")

        resp_data = b'{"anny_ready": false, "state": "ADMIN_MODE", "fabric_org": "GRECOITALICO", "fabric_repo": "ANNY-OPERATIONAL"}'
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            bs = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        assert not report.anny_ready, "Fabric unreachable must block ANNY_READY"
        assert not report.get_gate(ReadinessGate.FABRIC_REACHABLE).passed
        formatted = ChatGPTBootstrapFormatter.format(report)
        assert "BLOCKED" in formatted, f"Expected BLOCKED, got: {formatted!r}"
        assert "DEGRADED" not in formatted


class TestNegative_GitHubMissing:
    """NEGATIVE: No GitHub client → all downstream fabric gates fail."""

    def test_no_github_blocks_ready(
        self, mock_identity, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: mock_identity
        )
        resp_data = b'{"anny_ready": false, "state": "ADMIN_MODE", "fabric_org": "GRECOITALICO", "fabric_repo": "ANNY-OPERATIONAL"}'
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            bs = ThreePlaneBootstrap("/tmp", None, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        assert not report.anny_ready
        assert not report.get_gate(ReadinessGate.GITHUB_CONNECTED).passed
        assert not report.get_gate(ReadinessGate.FABRIC_REACHABLE).passed


class TestNegative_RuntimeNotReachable:
    """NEGATIVE: Runtime localhost not reachable → RUNTIME_REACHABLE gate FAIL.

    RuntimeIdentity.load() succeeding must NOT be counted as RUNTIME_REACHABLE.
    """

    def test_runtime_identity_load_does_not_satisfy_reachable_gate(
        self, mock_identity, mock_github, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: mock_identity
        )
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused")
        ):
            bs = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        # Identity gate passes (disk load), runtime reachable gate FAILS (no HTTP)
        assert report.get_gate(ReadinessGate.RUNTIME_IDENTITY).passed, \
            "Identity should load from disk"
        assert not report.get_gate(ReadinessGate.RUNTIME_REACHABLE).passed, \
            "RUNTIME_REACHABLE must fail when localhost is down"
        assert not report.anny_ready, \
            "ANNY_READY must be False when RUNTIME_REACHABLE fails"


class TestNegative_RuntimeAdmissionDenied:
    """NEGATIVE: Fabric returns DENY → RUNTIME_ADMITTED gate FAIL."""

    def test_fabric_deny_blocks_admission(
        self, mock_identity, mock_github, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: mock_identity
        )
        mock_fabric.check_admission.return_value = FabricAdmissionResult(
            FabricAdmissionResult.DENY, "RT-1234 not in approved list"
        )

        resp_data = b'{"anny_ready": false, "state": "ADMIN_MODE", "fabric_org": "GRECOITALICO", "fabric_repo": "ANNY-OPERATIONAL"}'
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            bs = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        assert not report.get_gate(ReadinessGate.RUNTIME_ADMITTED).passed
        assert not report.anny_ready


class TestNegative_FabricNodeMissingAtHead:
    """NEGATIVE: fabric/node.json absent at remote HEAD → gate fails."""

    def test_node_json_absent_blocks_ready(
        self, mock_identity, mock_github, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: mock_identity
        )
        mock_fabric.node_json_exists_at_remote_head.return_value = (False, None)

        resp_data = b'{"anny_ready": false, "state": "ADMIN_MODE", "fabric_org": "GRECOITALICO", "fabric_repo": "ANNY-OPERATIONAL"}'
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            bs = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        assert not report.get_gate(ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD).passed
        assert not report.anny_ready


class TestNegative_TenantUnbound:
    """NEGATIVE: Tenant not bound → FABRIC_TENANT_BOUND fails."""

    def test_unbound_tenant_blocks_ready(
        self, mock_identity, mock_github, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: mock_identity
        )
        mock_fabric.read_tenant_binding.side_effect = FabricError(
            "TENANT_UNBOUND", "No tenant binding for RT-1234"
        )

        resp_data = b'{"anny_ready": false, "state": "ADMIN_MODE", "fabric_org": "GRECOITALICO", "fabric_repo": "ANNY-OPERATIONAL"}'
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            bs = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        assert not report.get_gate(ReadinessGate.FABRIC_TENANT_BOUND).passed
        assert not report.anny_ready


class TestNegative_IdentityMissing:
    """NEGATIVE: RuntimeIdentity cannot load → all gates fail."""

    def test_missing_identity_blocks_all(
        self, mock_github, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: (_ for _ in ()).throw(FileNotFoundError("identity.json missing"))
        )

        resp_data = b'{"anny_ready": false, "state": "ADMIN_MODE"}'
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            bs = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        assert not report.get_gate(ReadinessGate.RUNTIME_IDENTITY).passed
        assert not report.anny_ready


class TestNegative_ContinuityIncoherent:
    """NEGATIVE: Continuity state not COHERENT → gate fails."""

    def test_incoherent_continuity_blocks_ready(
        self, mock_identity, mock_github, mock_fabric, mock_continuity, mock_config, monkeypatch
    ):
        monkeypatch.setattr(
            "runtime.identity.runtime_identity.RuntimeIdentity.load",
            lambda x: mock_identity
        )
        mock_continuity.status = {"state": "FRAGMENTED"}

        resp_data = b'{"anny_ready": false, "state": "ADMIN_MODE", "fabric_org": "GRECOITALICO", "fabric_repo": "ANNY-OPERATIONAL"}'
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            bs = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity, config=mock_config)
            report = bs.resolve()

        assert not report.get_gate(ReadinessGate.CONTINUITY_COHERENT).passed
        assert not report.anny_ready


# ---------------------------------------------------------------------------
# FORMAT TESTS — Status word semantics
# ---------------------------------------------------------------------------

class TestFormatSemantics:
    def test_failed_bootstrap_says_blocked_not_degraded(self, mock_continuity):
        report = BootstrapReport(anny_ready=False, runtime_id="RT-1234", fabric_node="UNKNOWN")
        output = ChatGPTBootstrapFormatter.format(report)
        assert "BLOCKED" in output
        assert "DEGRADED" not in output

    def test_ready_bootstrap_says_ready(self, mock_continuity):
        report = BootstrapReport(anny_ready=True, runtime_id="RT-1234", fabric_node="NODE-001")
        output = ChatGPTBootstrapFormatter.format(report)
        assert "READY" in output
        assert "BLOCKED" not in output


# ---------------------------------------------------------------------------
# MANDATORY GATE COVERAGE
# ---------------------------------------------------------------------------

class TestMandatoryGateCoverage:
    """Verify that all MANDATORY_GATES are in the gates enum and are evaluated."""

    def test_all_mandatory_gates_defined(self):
        for gate in MANDATORY_GATES:
            assert isinstance(gate, ReadinessGate)

    def test_mandatory_gates_include_runtime_gates(self):
        assert ReadinessGate.RUNTIME_REACHABLE in MANDATORY_GATES
        assert ReadinessGate.RUNTIME_HEALTH_VERIFIED in MANDATORY_GATES
        assert ReadinessGate.RUNTIME_BINDING_VERIFIED in MANDATORY_GATES
        assert ReadinessGate.RUNTIME_ADMITTED in MANDATORY_GATES

    def test_mandatory_gates_include_fabric_gates(self):
        assert ReadinessGate.FABRIC_REACHABLE in MANDATORY_GATES
        assert ReadinessGate.FABRIC_TENANT_BOUND in MANDATORY_GATES
        assert ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD in MANDATORY_GATES
        assert ReadinessGate.FABRIC_STATE_READABLE in MANDATORY_GATES
        assert ReadinessGate.FABRIC_PROVENANCE_VALID in MANDATORY_GATES

    def test_mandatory_gates_include_cross_plane(self):
        assert ReadinessGate.PLANE_RECONCILIATION in MANDATORY_GATES
        assert ReadinessGate.CONTINUITY_COHERENT in MANDATORY_GATES
