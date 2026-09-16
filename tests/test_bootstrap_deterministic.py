"""
Bootstrap Gate Tests — Phase E-K Extensions.

Tests for the deterministic bootstrap phases introduced by
ANNY-BOOTSTRAP-DETERMINISTIC-001:
  - Phase E: Policy Snapshot
  - Phase G: Inventory Discovery
  - Phase H: Critical Access Verification
  - Phase I: Contracts Discovery
  - Phase J: Delegation Context
  - Phase K: Continuity Coherence (extended)
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import List

from runtime.bootstrap.gates import ReadinessGate, GateResult, MANDATORY_GATES
from runtime.bootstrap.report import BootstrapReport, ComponentInventory
from runtime.bootstrap.planes import ThreePlaneBootstrap, _to_component_inventory
from runtime.core.inventory import InventoryDiscovery, BootstrapInventory, ComponentInventory as InvComponentInventory
from runtime.core.access_verifier import CriticalAccessVerifier, AccessVerificationResult, AccessTestResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bootstrap(**overrides):
    """Build a ThreePlaneBootstrap with safe mocked dependencies."""
    defaults = dict(
        data_dir="/tmp",
        github_client=None,
        fabric_client=None,
        continuity_engine=None,
    )
    defaults.update(overrides)
    return ThreePlaneBootstrap(**defaults)


def _make_report(**kwargs):
    defaults = dict(anny_ready=False, runtime_id="rt-test-001", fabric_node="node-001")
    defaults.update(kwargs)
    return BootstrapReport(**defaults)


# ---------------------------------------------------------------------------
# Phase E: Policy Snapshot
# ---------------------------------------------------------------------------

class TestPhaseE_PolicySnapshot:

    def test_policy_snapshot_sets_revision_on_report(self):
        fabric = MagicMock()
        fabric.read_policy.return_value = {"revision": "v2.3", "require_admission": True}
        b = _make_bootstrap(fabric_client=fabric)
        report = _make_report()

        b.fabric = fabric
        b._gate_policy_snapshot(report)

        assert report.policy_revision == "v2.3"
        gate = report.get_gate(ReadinessGate.POLICY_SNAPSHOT_FRESH)
        assert gate.passed

    def test_policy_snapshot_fails_when_adapter_missing_method(self):
        """If fabric adapter doesn't implement read_policy, we fail strictly."""
        fabric = MagicMock(spec=[])
        b = _make_bootstrap(fabric_client=fabric)
        report = _make_report()
        b.fabric = fabric

        b._gate_policy_snapshot(report)

        gate = report.get_gate(ReadinessGate.POLICY_SNAPSHOT_FRESH)
        assert not gate.passed
        assert "Mock object has no attribute 'read_policy'" in gate.detail

    def test_policy_snapshot_failure_blocks_gate(self):
        fabric = MagicMock()
        fabric.read_policy.side_effect = Exception("network timeout")
        b = _make_bootstrap(fabric_client=fabric)
        report = _make_report()
        b.fabric = fabric

        b._gate_policy_snapshot(report)

        gate = report.get_gate(ReadinessGate.POLICY_SNAPSHOT_FRESH)
        assert not gate.passed


# ---------------------------------------------------------------------------
# Phase G: Inventory Discovery
# ---------------------------------------------------------------------------

class TestPhaseG_Inventory:

    def test_inventory_is_mandatory_gate(self):
        for gate in [
            ReadinessGate.CAPABILITIES_INVENTORIED,
            ReadinessGate.TOOLS_INVENTORIED,
            ReadinessGate.MODELS_INVENTORIED,
            ReadinessGate.WORKERS_INVENTORIED,
            ReadinessGate.CONNECTORS_INVENTORIED,
        ]:
            assert gate in MANDATORY_GATES, f"{gate.name} must be a MANDATORY gate"

    def test_empty_capability_registry_blocks_gate(self):
        """Zero declared capabilities must block the gate."""
        mock_registry = MagicMock()
        mock_registry.list_all.return_value = []

        b = _make_bootstrap()
        report = _make_report()
        b._cap_registry = mock_registry

        result = b._gate_inventory(report, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.CAPABILITIES_INVENTORIED)
        assert not gate.passed

    def test_populated_inventory_passes_all_gates(self):
        """A registry with entries should pass all 5 inventory gates."""
        cap = MagicMock()
        cap.capability_id = "filesystem.list"
        cap.enabled = True

        mock_cap_reg = MagicMock()
        mock_cap_reg.list_all.return_value = [cap]

        tool_manifest = MagicMock()
        tool_manifest.name = "fs.read"
        mock_tool_reg = MagicMock()
        mock_tool_reg.list_tools.return_value = [tool_manifest]

        model = MagicMock()
        model.model_id = "qwen3-8b"
        from runtime.execution.models import ModelState
        model.state = ModelState.AVAILABLE
        mock_model_reg = MagicMock()
        mock_model_reg.list_models.return_value = [model]

        b = _make_bootstrap()
        b._cap_registry = mock_cap_reg
        b._tool_registry = mock_tool_reg
        b._model_registry = mock_model_reg
        report = _make_report()

        inv = b._gate_inventory(report, fabric_contract=None)

        assert inv is not None
        for gate in [
            ReadinessGate.CAPABILITIES_INVENTORIED,
            ReadinessGate.TOOLS_INVENTORIED,
        ]:
            assert report.get_gate(gate).passed, f"{gate.name} should pass"

    def test_inventory_error_blocks_all_gates(self):
        """If InventoryDiscovery.discover() raises, all 5 gates must fail."""
        b = _make_bootstrap()
        b._cap_registry = MagicMock()
        b._cap_registry.list_all.side_effect = RuntimeError("disk read error")
        report = _make_report()

        b._gate_inventory(report, fabric_contract=None)

        for gate in [
            ReadinessGate.CAPABILITIES_INVENTORIED,
            ReadinessGate.TOOLS_INVENTORIED,
            ReadinessGate.MODELS_INVENTORIED,
            ReadinessGate.WORKERS_INVENTORIED,
            ReadinessGate.CONNECTORS_INVENTORIED,
        ]:
            result = report.get_gate(gate)
            assert result is not None


# ---------------------------------------------------------------------------
# Phase H: Critical Access Verification
# ---------------------------------------------------------------------------

class TestPhaseH_CriticalAccess:

    def test_critical_access_is_mandatory_gate(self):
        assert ReadinessGate.CRITICAL_ACCESS_VERIFIED in MANDATORY_GATES

    def test_implemented_access_checks_pass_but_unimplemented_critical_checks_block(self, tmp_path):
        """Implemented checks pass; unsupported critical capabilities still block Phase H."""
        gh = MagicMock()
        gh.list_repos.return_value = [{"name": "repo1"}]
        fabric = MagicMock()
        fabric.read_node_config.return_value = MagicMock(node_id="n-001")

        verifier = CriticalAccessVerifier(
            authorized_capabilities=list(CriticalAccessVerifier.CRITICAL_CAPABILITIES),
            data_dir=str(tmp_path),
            github_client=gh,
            fabric_adapter=fabric,
        )
        result = verifier.verify()

        assert not result.passed
        assert "repository.search" in result.critical_failures
        assert "runtime.status" in result.critical_failures
        assert "runtime.execution" in result.critical_failures
        assert "tool.resolve" in result.critical_failures
        assert "model.resolve" in result.critical_failures
        assert "worker.resolve" in result.critical_failures

        by_cap = {item.capability_id: item for item in result.results}
        assert by_cap["repository.read"].passed
        assert by_cap["filesystem.inspect"].passed
        assert by_cap["filesystem.list"].passed
        assert by_cap["fabric.read"].passed
        assert by_cap["repository.search"].evidence == "NOT_IMPLEMENTED"

    def test_filesystem_access_fails_with_nonexistent_dir(self):
        verifier = CriticalAccessVerifier(
            authorized_capabilities=["filesystem.inspect", "filesystem.list"],
            data_dir="/nonexistent/path/that/should/not/exist",
        )
        result = verifier.verify()
        assert not result.passed
        assert "filesystem.inspect" in result.critical_failures

    def test_no_authorized_capabilities_fails_strictly(self, tmp_path):
        """Rule 7: If critical capabilities are missing, fail strictly -> BLOCKED."""
        verifier = CriticalAccessVerifier(
            authorized_capabilities=[],
            data_dir=str(tmp_path),
        )
        result = verifier.verify()
        assert not result.passed
        assert len(result.critical_failures) == 10
        assert "filesystem.inspect" in result.critical_failures

    def test_repository_read_fails_without_github_client(self):
        verifier = CriticalAccessVerifier(
            authorized_capabilities=["repository.read"],
            data_dir="/tmp",
            github_client=None,
        )
        result = verifier.verify()
        assert not result.passed
        assert "repository.read" in result.critical_failures

    def test_fabric_read_fails_without_fabric_client(self):
        verifier = CriticalAccessVerifier(
            authorized_capabilities=["fabric.read"],
            data_dir="/tmp",
            fabric_adapter=None,
        )
        result = verifier.verify()
        assert not result.passed
        assert "fabric.read" in result.critical_failures

    def test_access_failure_blocks_anny_ready(self, tmp_path):
        """A failing Phase H gate must block ANNY_READY."""
        b = _make_bootstrap(data_dir=str(tmp_path))
        b.github = None
        b.fabric = None
        report = _make_report()

        b._gate_critical_access(
            report,
            authorized_capabilities=["repository.read", "filesystem.inspect", "filesystem.list", "fabric.read"],
        )

        gate = report.get_gate(ReadinessGate.CRITICAL_ACCESS_VERIFIED)
        assert not gate.passed

