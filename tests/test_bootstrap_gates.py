import pytest
from unittest.mock import Mock, MagicMock
from runtime.bootstrap.planes import ThreePlaneBootstrap
from runtime.bootstrap.report import BootstrapReport, ChatGPTBootstrapFormatter
from runtime.bootstrap.gates import ReadinessGate
from runtime.identity.runtime_identity import RuntimeIdentity
from runtime.fabric.client import FabricError
from runtime.fabric.models import FabricHealthResult, FabricNode, FabricTenant, FabricTrustToken
from runtime.core.engine import RuntimeEngine
from runtime.core.config import RuntimeConfig

@pytest.fixture
def mock_identity():
    ident = Mock(spec=RuntimeIdentity)
    ident.runtime_id = "RT-1234"
    ident._private_key = b"dummy"
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
    fab.probe_reachability.return_value = FabricHealthResult(True, "NODE-001", 10.0, None)
    fab.read_node_config.return_value = FabricNode("NODE-001", "GRECOITALICO", "ANNY-OPERATIONAL", "REPOSITORY_FABRIC", "2026-09-15T00:00:00Z")
    fab.read_tenant_binding.return_value = FabricTenant("TENANT-1", "RT-1234", [], "2026-09-15T00:00:00Z")
    fab.issue_trust_token.return_value = FabricTrustToken("RT-1234", "NODE-001", "2026-09-15T00:00:00Z", "2026-09-15T01:00:00Z", "dummy_sig", True)
    fab.validate_provenance.return_value = True
    return fab

@pytest.fixture
def mock_continuity():
    cont = Mock()
    cont.status = {"state": "COHERENT"}
    return cont

def test_fabric_unreachable_blocks_ready(mock_identity, mock_github, mock_fabric, mock_continuity, monkeypatch):
    monkeypatch.setattr("runtime.identity.runtime_identity.RuntimeIdentity.load", lambda x: mock_identity)
    
    mock_fabric.probe_reachability.return_value = FabricHealthResult(False, None, None, "Connection refused")
    
    bootstrap = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity)
    report = bootstrap.resolve()
    
    assert not report.anny_ready
    assert not report.get_gate(ReadinessGate.FABRIC_REACHABLE).passed

def test_github_missing_blocks_ready(mock_identity, mock_fabric, mock_continuity, monkeypatch):
    monkeypatch.setattr("runtime.identity.runtime_identity.RuntimeIdentity.load", lambda x: mock_identity)
    
    bootstrap = ThreePlaneBootstrap("/tmp", None, mock_fabric, mock_continuity)
    report = bootstrap.resolve()
    
    assert not report.anny_ready
    assert not report.get_gate(ReadinessGate.GITHUB_CONNECTED).passed
    assert not report.get_gate(ReadinessGate.FABRIC_REACHABLE).passed

def test_all_planes_healthy_sets_ready(mock_identity, mock_github, mock_fabric, mock_continuity, monkeypatch):
    monkeypatch.setattr("runtime.identity.runtime_identity.RuntimeIdentity.load", lambda x: mock_identity)
    
    bootstrap = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity)
    report = bootstrap.resolve()
    
    assert report.anny_ready
    assert report.runtime_id == "RT-1234"
    assert report.fabric_node == "NODE-001"
    for gate in ReadinessGate:
        assert report.get_gate(gate).passed

def test_bootstrap_report_format(mock_identity, mock_github, mock_fabric, mock_continuity, monkeypatch):
    monkeypatch.setattr("runtime.identity.runtime_identity.RuntimeIdentity.load", lambda x: mock_identity)
    
    bootstrap = ThreePlaneBootstrap("/tmp", mock_github, mock_fabric, mock_continuity)
    report = bootstrap.resolve()
    
    output = ChatGPTBootstrapFormatter.format(report)
    assert "ANNY BOOTSTRAP: READY" in output
    assert "PLANE_1_GITHUB: True" in output
    assert "PLANE_2_FABRIC: True" in output
    assert "PLANE_3_RUNTIME: True" in output
    assert "RUNTIME_ID: RT-1234" in output
    assert "FABRIC_NODE: NODE-001" in output
    assert "FABRIC_TENANT: TENANT-1" in output
    assert "RECONCILIATION: True" in output
    assert "CONTINUITY_COHERENT: True" in output
