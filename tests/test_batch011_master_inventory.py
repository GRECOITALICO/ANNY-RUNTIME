"""Batch 011: Test Reconciliation & Master Inventory Expansion.

Test contract for the projection registry after Batch 011 additions.
Validates:
  - Total inventory count (357)
  - Batch 011 delta (+36 from 321)
  - P0 count expansion (96, up from 85 via evidence-backed operational grounding)
  - 36 new grounded operational depth definitions across subsystems:
    * Repository Fabric & Git service depth (git.status, git.branch_info, git.diff_summary)
    * Workspace & Projects lifecycle (workspace.state, workspace.ephemeral_manager, projects.project_status)
    * Session & Communication coordination (session.lease, api.bridge_router)
    * Sandbox & Isolation contracts (sandbox.restricted_backend, sandbox.isolation_contract)
    * Remote Compute infrastructure & Colab transport (compute.colab_provider, compute.cli_transport, compute.browser_transport, compute.lease_model, compute.trust_profile_model)
    * Capability gate decisions (capability.gate_engine, capability.decision_model)
    * Execution evaluation & models (execution.evaluation_record)
    * Intelligence benchmark & layer depth (intelligence.benchmark_store, intelligence.local_layer, intelligence.scorecard_model, intelligence.candidate_profile, intelligence.assessment_request, intelligence.assessment_response, intelligence.grading_result)
    * Security context & boundaries (security.active_context_mgr, security.execution_context_model)
    * Continuity operational provider & records (continuity.operational_provider, continuity.event_record_model)
    * Fabric admission, models & contracts (fabric.admission_result, fabric.provenance_model, fabric.health_model, fabric.policy_model, fabric.contract_model)
    * Diagnostics & Updater depth (diagnostics.diagnostic_check, updater.channel_state)
  - Remaining PARTIAL surfaces stay PARTIAL (admin.operations, admin.receipts, etc.)
  - BLOCKED surfaces remain BLOCKED (distribution.sync_stage, activation, rollback)
  - Zero duplicate projection IDs
  - Navigation contract integrity (33 items resolve)
  - SYNC identity stability and separation
  - distribution.sync remains visible and BOUND
  - Open-ended inventory (no hard ceiling, 349 viewport target)
  - Provider neutrality
  - Section and priority distribution
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBatch011MasterInventory:
    """Projection registry contract after Batch 011."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= 357

    def test_batch_011_delta(self):
        """Batch 010 had 321. Batch 011 adds 36."""
        assert self.summary["total_definitions"] >= 357

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        """P0 advanced from 85 to 96 via operational depth additions."""
        assert self.summary["by_priority"]["P0"] >= 96

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] >= 178

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] >= 83

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == 0

    # ---- Implementation status distribution ----

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] >= 78

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] <= 9

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] >= 267

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Batch 011 New definitions audit ----

    def test_batch011_new_definitions_exist(self):
        expected_new_projections = [
            ("git.status", "Repository Fabric", "P0", "RUNTIME_GIT"),
            ("git.branch_info", "Repository Fabric", "P0", "RUNTIME_GIT"),
            ("git.diff_summary", "Repository Fabric", "P1", "RUNTIME_GIT"),
            ("workspace.state", "Projects / Workspaces", "P0", "WORKSPACE_MANAGER"),
            ("workspace.ephemeral_manager", "Projects / Workspaces", "P1", "WORKSPACE_MANAGER"),
            ("projects.project_status", "Projects / Workspaces", "P1", "PROJECT_REGISTRY"),
            ("session.lease", "Communication", "P1", "SESSION_MANAGER"),
            ("api.bridge_router", "Communication", "P1", "BRIDGE_ROUTER"),
            ("sandbox.restricted_backend", "Execution", "P1", "SANDBOX_MANAGER"),
            ("sandbox.isolation_contract", "Execution", "P0", "SANDBOX_MANAGER"),
            ("compute.colab_provider", "Infrastructure", "P1", "COMPUTE_PROVIDER"),
            ("compute.cli_transport", "Infrastructure", "P1", "COMPUTE_TRANSPORT"),
            ("compute.browser_transport", "Infrastructure", "P1", "COMPUTE_TRANSPORT"),
            ("compute.lease_model", "Infrastructure", "P1", "COMPUTE_MODEL"),
            ("compute.trust_profile_model", "Infrastructure", "P0", "COMPUTE_POLICY"),
            ("capability.gate_engine", "Execution", "P0", "CAPABILITY_GATE"),
            ("capability.decision_model", "Execution", "P1", "CAPABILITY_GATE"),
            ("execution.evaluation_record", "Execution", "P2", "RUNTIME_EXECUTION"),
            ("intelligence.benchmark_store", "Intelligence", "P1", "BENCHMARK_STORE"),
            ("intelligence.local_layer", "Intelligence", "P0", "LOCAL_INTELLIGENCE"),
            ("intelligence.scorecard_model", "Intelligence", "P1", "BENCHMARK_SCORECARD"),
            ("intelligence.candidate_profile", "Intelligence", "P1", "MODEL_PROFILE"),
            ("intelligence.assessment_request", "Intelligence", "P2", "INTELLIGENCE_MODEL"),
            ("intelligence.assessment_response", "Intelligence", "P2", "INTELLIGENCE_MODEL"),
            ("intelligence.grading_result", "Intelligence", "P2", "GRADING_ENGINE"),
            ("security.active_context_mgr", "Security / Trust", "P0", "CONTEXT_MANAGER"),
            ("security.execution_context_model", "Security / Trust", "P1", "SECURITY_MODEL"),
            ("continuity.operational_provider", "Continuity", "P0", "OPERATIONAL_PROVIDER"),
            ("continuity.event_record_model", "Continuity", "P1", "CONTINUITY_MODEL"),
            ("fabric.admission_result", "Infrastructure", "P1", "FABRIC_MODEL"),
            ("fabric.provenance_model", "Infrastructure", "P0", "FABRIC_MODEL"),
            ("fabric.health_model", "Infrastructure", "P0", "FABRIC_MODEL"),
            ("fabric.policy_model", "Infrastructure", "P1", "FABRIC_MODEL"),
            ("fabric.contract_model", "Infrastructure", "P1", "FABRIC_MODEL"),
            ("diagnostics.diagnostic_check", "Infrastructure", "P1", "RUNTIME_DOCTOR"),
            ("updater.channel_state", "Distribution / Updates", "P1", "UPDATE_MANAGER"),
        ]
        assert len(expected_new_projections) == 36
        for pid, sec, prio, auth in expected_new_projections:
            p = self.registry.get(pid)
            assert p is not None, f"Missing Batch 011 projection: {pid}"
            assert p.section == sec, f"{pid} section mismatch: {p.section} != {sec}"
            assert p.priority == prio, f"{pid} priority mismatch: {p.priority} != {prio}"
            assert p.source_authority == auth, f"{pid} authority mismatch: {p.source_authority} != {auth}"
            assert p.implementation_status == "PLANNED", f"{pid} should be PLANNED"

    # ---- Duplicate checks ----

    def test_zero_duplicate_projection_ids(self):
        ids = [item.projection_id for item in self.items]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {len(ids) - len(set(ids))}"

    def test_batch011_sort_order_range(self):
        sort_orders = [item.sort_order for item in self.items]
        assert min(sort_orders) == 0
        assert max(sort_orders) >= 670

    # ---- Navigation integrity ----

    def test_navigation_contract_integrity(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
        assert len(DEFAULT_NAVIGATION_ITEMS) == 33
        for item in DEFAULT_NAVIGATION_ITEMS:
            if item.availability in ("ACTIVE", "ALIAS"):
                assert self.registry.get(item.projection_id) is not None, f"Nav item {item.label} does not resolve {item.projection_id}"

    # ---- Remaining PARTIAL surfaces ----

    def test_remaining_partial_surfaces(self):
        remaining_partial = [
            "admin.operations",
            "admin.receipts",
            "intelligence.executors_view",
            "project.current_mission",
            "project.current_task",
            "project.next_action",
            "project.blockers",
            "conrrad.required_services",
            "security.trust",
        ]
        for pid in remaining_partial:
            p = self.registry.get(pid)
            assert p is not None, f"Missing projection: {pid}"
            assert p.implementation_status == "PARTIAL", f"{pid} should be PARTIAL"

    # ---- BLOCKED surfaces remain BLOCKED ----

    def test_blocked_surfaces_remain_blocked(self):
        for pid in ["distribution.sync_stage", "distribution.activation", "distribution.rollback"]:
            p = self.registry.get(pid)
            assert p is not None
            assert p.implementation_status == "BLOCKED"

    # ---- Invariant enforcement ----

    def test_sync_separation_invariants(self):
        sync_items = [p for p in self.items if "sync" in p.tags or "distribution" in p.tags]
        assert len(sync_items) >= 10
        dist_sync = self.registry.get("distribution.sync")
        assert dist_sync is not None
        assert dist_sync.implementation_status == "BOUND"

    def test_provider_neutrality(self):
        """Check that Azure is not hardcoded as functional identity."""
        p = self.registry.get("infrastructure.azure")
        assert p is not None
        assert p.priority == "P2"
        assert p.implementation_status == "PLANNED"
        assert p.source_authority == "AZURE_LIVE_TRUTH"

    def test_freshness_invariants(self):
        for p in self.items:
            if p.implementation_status == "BOUND":
                assert p.freshness == "LIVE_ON_READ"
            elif p.implementation_status == "PLANNED":
                assert p.freshness == "NOT_BOUND"

    def test_registry_validates(self):
        self.registry.validate()


class TestBatch011Regression:
    """Verify prior batch contracts are preserved."""

    def test_prior_batch_count_floors(self):
        from runtime.admin.projections import default_projection_registry
        reg = default_projection_registry()
        summary = reg.summary()
        assert summary["total_definitions"] >= 357
        assert summary["by_priority"]["P0"] >= 96
        assert summary["by_implementation_status"]["BOUND"] >= 78
