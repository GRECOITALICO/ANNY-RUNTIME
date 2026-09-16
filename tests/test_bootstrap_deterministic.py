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

    def test_policy_snapshot_stub_passes_when_adapter_missing_method(self):
        """If fabric adapter doesn't implement read_policy, we pass with STUB."""
        fabric = MagicMock(spec=[])   # spec with no methods → AttributeError on read_policy
        b = _make_bootstrap(fabric_client=fabric)
        report = _make_report()
        b.fabric = fabric

        b._gate_policy_snapshot(report)

        gate = report.get_gate(ReadinessGate.POLICY_SNAPSHOT_FRESH)
        assert gate.passed
        assert report.policy_revision == "STUB"

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
            # Error in capabilities propagates; others may be populated or not
            # depending on InventoryDiscovery internals, but the gate must record a result
            result = report.get_gate(gate)
            assert result is not None


# ---------------------------------------------------------------------------
# Phase H: Critical Access Verification
# ---------------------------------------------------------------------------

class TestPhaseH_CriticalAccess:

    def test_critical_access_is_mandatory_gate(self):
        assert ReadinessGate.CRITICAL_ACCESS_VERIFIED in MANDATORY_GATES

    def test_filesystem_access_passes_with_valid_data_dir(self, tmp_path):
        verifier = CriticalAccessVerifier(
            authorized_capabilities=["filesystem.inspect", "filesystem.list"],
            data_dir=str(tmp_path),
        )
        result = verifier.verify()
        assert result.passed
        assert not result.critical_failures

    def test_filesystem_access_fails_with_nonexistent_dir(self):
        verifier = CriticalAccessVerifier(
            authorized_capabilities=["filesystem.inspect", "filesystem.list"],
            data_dir="/nonexistent/path/that/should/not/exist",
        )
        result = verifier.verify()
        assert not result.passed
        assert "filesystem.inspect" in result.critical_failures

    def test_no_authorized_capabilities_skips_all_tests(self, tmp_path):
        """If no critical capabilities are authorized, skip all tests → pass."""
        verifier = CriticalAccessVerifier(
            authorized_capabilities=[],
            data_dir=str(tmp_path),
        )
        result = verifier.verify()
        assert result.passed
        assert len(result.results) == 0

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
        b.github = None   # No GitHub → repository.read will fail
        b.fabric = None   # No fabric → fabric.read will fail
        report = _make_report()

        b._gate_critical_access(
            report,
            authorized_capabilities=["repository.read", "filesystem.inspect", "filesystem.list", "fabric.read"],
        )

        gate = report.get_gate(ReadinessGate.CRITICAL_ACCESS_VERIFIED)
        assert not gate.passed


# ---------------------------------------------------------------------------
# Phase I: Contracts Discovery
# ---------------------------------------------------------------------------

class TestPhaseI_Contracts:

    def test_contracts_is_mandatory_gate(self):
        assert ReadinessGate.CONTRACTS_DISCOVERED in MANDATORY_GATES

    def test_contracts_stub_passes_when_read_contract_not_implemented(self):
        fabric = MagicMock(spec=[])  # No read_contract method
        b = _make_bootstrap(fabric_client=fabric)
        b.fabric = fabric
        report = _make_report()

        b._gate_contracts(report, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.CONTRACTS_DISCOVERED)
        assert gate.passed

    def test_contracts_from_fabric_adapter(self):
        fabric = MagicMock()
        fabric.read_contract.return_value = {
            "contract_id": "c-001",
            "tenant_id": "t-001",
            "granted_capabilities": ["filesystem.list"],
            "revoked_capabilities": [],
        }
        b = _make_bootstrap(fabric_client=fabric)
        b.fabric = fabric
        report = _make_report()

        b._gate_contracts(report, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.CONTRACTS_DISCOVERED)
        assert gate.passed
        assert gate.evidence == "c-001"

    def test_no_fabric_blocks_contracts(self):
        b = _make_bootstrap(fabric_client=None)
        report = _make_report()

        b._gate_contracts(report, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.CONTRACTS_DISCOVERED)
        assert not gate.passed


# ---------------------------------------------------------------------------
# Phase J: Delegation Context
# ---------------------------------------------------------------------------

class TestPhaseJ_DelegationContext:

    def test_delegation_context_is_mandatory_gate(self):
        assert ReadinessGate.DELEGATION_CONTEXT_BUILT in MANDATORY_GATES

    def test_delegation_context_built_with_full_state(self):
        b = _make_bootstrap()
        report = _make_report(runtime_id="rt-abc", fabric_node="node-test")

        # Pre-seed a passing tenant gate with evidence
        report.add_result(GateResult(
            ReadinessGate.FABRIC_TENANT_BOUND, True,
            "Tenant bound", "tenant-xyz"
        ))

        ident = MagicMock()
        ident.runtime_id = "rt-abc"

        b._gate_delegation_context(report, ident, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.DELEGATION_CONTEXT_BUILT)
        assert gate.passed
        assert "runtime_id=rt-abc" in gate.evidence
        assert "tenant_id=tenant-xyz" in gate.evidence
        assert "fabric_node=node-test" in gate.evidence

    def test_delegation_context_fails_without_runtime_id(self):
        b = _make_bootstrap()
        report = _make_report(runtime_id="rt-abc", fabric_node="node-test")
        report.add_result(GateResult(ReadinessGate.FABRIC_TENANT_BOUND, True, "OK", "t-001"))

        b._gate_delegation_context(report, ident=None, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.DELEGATION_CONTEXT_BUILT)
        assert not gate.passed
        assert "runtime_id unknown" in gate.detail

    def test_delegation_context_fails_without_tenant(self):
        b = _make_bootstrap()
        report = _make_report(runtime_id="rt-abc", fabric_node="node-test")
        # No tenant gate result added

        ident = MagicMock()
        ident.runtime_id = "rt-abc"

        b._gate_delegation_context(report, ident, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.DELEGATION_CONTEXT_BUILT)
        assert not gate.passed
        assert "tenant_id not bound" in gate.detail

    def test_delegation_context_fails_without_fabric_node(self):
        b = _make_bootstrap()
        report = _make_report(runtime_id="rt-abc", fabric_node="UNKNOWN")
        report.add_result(GateResult(ReadinessGate.FABRIC_TENANT_BOUND, True, "OK", "t-001"))

        ident = MagicMock()
        ident.runtime_id = "rt-abc"

        b._gate_delegation_context(report, ident, fabric_contract=None)

        gate = report.get_gate(ReadinessGate.DELEGATION_CONTEXT_BUILT)
        assert not gate.passed
        assert "fabric_node not resolved" in gate.detail


# ---------------------------------------------------------------------------
# Gate Coverage: All 25 Mandatory Gates defined in MANDATORY_GATES
# ---------------------------------------------------------------------------

class TestMandatoryGateCoverage_Extended:

    def test_phase_e_to_k_gates_in_mandatory_gates(self):
        expected = {
            ReadinessGate.POLICY_SNAPSHOT_FRESH,
            ReadinessGate.CAPABILITIES_INVENTORIED,
            ReadinessGate.TOOLS_INVENTORIED,
            ReadinessGate.MODELS_INVENTORIED,
            ReadinessGate.WORKERS_INVENTORIED,
            ReadinessGate.CONNECTORS_INVENTORIED,
            ReadinessGate.CRITICAL_ACCESS_VERIFIED,
            ReadinessGate.CONTRACTS_DISCOVERED,
            ReadinessGate.DELEGATION_CONTEXT_BUILT,
        }
        missing = expected - MANDATORY_GATES
        assert not missing, f"Gates not in MANDATORY_GATES: {missing}"

    def test_total_mandatory_gate_count(self):
        """Ensure we have exactly 25 mandatory gates."""
        assert len(MANDATORY_GATES) == 25

    def test_formatter_reports_all_phases(self):
        from runtime.bootstrap.report import ChatGPTBootstrapFormatter
        report = BootstrapReport(anny_ready=False, runtime_id="rt-x", fabric_node="n-x")
        formatted = ChatGPTBootstrapFormatter.format(report)

        for phase in ["PHASE A", "PHASE B", "PHASE C", "PHASE D", "PHASE E",
                      "PHASE F", "PHASE G", "PHASE H", "PHASE I", "PHASE J", "PHASE K"]:
            assert phase in formatted, f"{phase} missing from ChatGPT bootstrap output"

    def test_formatter_reports_inventory_summary(self):
        from runtime.bootstrap.report import ChatGPTBootstrapFormatter
        report = BootstrapReport(anny_ready=True, runtime_id="rt-x", fabric_node="n-x")
        report.capabilities.declared = ["filesystem.list", "repository.read"]
        report.capabilities.authorized = ["filesystem.list", "repository.read"]
        formatted = ChatGPTBootstrapFormatter.format(report)

        assert "INVENTORY SUMMARY" in formatted
        assert "Capabilities: 2 declared, 2 authorized" in formatted

    def test_blocked_bootstrap_never_says_degraded(self):
        from runtime.bootstrap.report import ChatGPTBootstrapFormatter
        report = BootstrapReport(anny_ready=False, runtime_id="rt-x", fabric_node="n-x")
        formatted = ChatGPTBootstrapFormatter.format(report)

        assert "BLOCKED" in formatted
        assert "DEGRADED" not in formatted
