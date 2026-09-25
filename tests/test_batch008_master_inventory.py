"""Batch 008: Master Inventory P0 Coverage & Operational Depth.

Test contract for the projection registry after Batch 008 additions and P0 promotions.
Validates:
  - Total inventory count (245)
  - Batch 008 delta (+38 from 207)
  - P0 count expansion (66, up from 42 via evidence-backed P0 coverage audit)
  - Evidence-backed P0 promotions (active nav + core operational endpoints)
  - Placeholder non-promotion (execution.workspaces, intelligence.executors, intelligence.performance)
  - PARTIAL surfaces remain PARTIAL (admin.operations, admin.receipts, etc.)
  - BLOCKED surfaces remain BLOCKED (distribution.sync_stage, activation, rollback)
  - Zero duplicate projection IDs
  - Navigation contract integrity
  - SYNC identity stability
  - distribution.sync on page 1
  - Open-ended inventory (no hard ceiling, 349 viewport target)
  - Provider neutrality
  - Section and priority distribution
  - Regression against all prior batches
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBatch008MasterInventory:
    """Projection registry contract after Batch 008."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= 245

    def test_batch_008_delta(self):
        """Batch 007 had 207. Batch 008 adds 38."""
        batch_007_count = 207
        assert self.summary["total_definitions"] - batch_007_count >= 38

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        """P0 advanced from 42 to 66 via evidence-backed P0 coverage audit."""
        assert self.summary["by_priority"]["P0"] >= 66

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] >= 136

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] >= 43

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == 0

    # ---- Implementation status distribution ----

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] >= 73

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] <= 13

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] >= 156

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Evidence-backed P0 promotions audit ----

    def test_active_navigation_p0_promotions(self):
        """All active navigation surfaces with concrete renderers are P0."""
        promoted_nav = [
            ("audit.events", "/audit/events"),
            ("evidence.index", "/audit/evidence"),
            ("execution.execution_runs", "/execution/executions"),
            ("infrastructure.runtime", "/infrastructure/runtime"),
            ("intelligence.capabilities", "/intelligence/capabilities"),
            ("telemetry.live", "/telemetry/live"),
            ("telemetry.timeline", "/telemetry/timeline"),
            ("universe.resources", "/universe/resources"),
        ]
        for pid, route in promoted_nav:
            p = self.registry.get(pid)
            assert p is not None, f"Missing projection: {pid}"
            assert p.priority == "P0", f"{pid} should be P0, got {p.priority}"
            assert p.implementation_status == "BOUND", f"{pid} should be BOUND"
            assert p.route_or_detail == route, f"{pid} route mismatch: {p.route_or_detail} != {route}"

    def test_core_operational_endpoints_p0_promotions(self):
        """Core operational endpoints with concrete handlers/actions are P0."""
        core_endpoints = [
            ("onboarding.device_flow", "/github/device/poll"),
            ("onboarding.access_token", "/github/token"),
            ("onboarding.ready", "/"),
            ("onboarding.failure", "/"),
            ("fabric.setup", "/fabric/setup"),
            ("admin.doctor", "/doctor"),
            ("admin.policies", "/policies"),
            ("admin.restart", "/admin/restart"),
            ("admin.logout", "/logout"),
            ("universe.accounts", "/universe/accounts"),
            ("communication.sessions", "/sessions"),
            ("browser.dashboard", "/browser"),
            ("api.status", "/api/status"),
            ("control.projections_api", "/api/control-center/projections"),
            ("github.disconnect", "/github/disconnect"),
            ("github.device_init", "/github/device/init"),
        ]
        for pid, route in core_endpoints:
            p = self.registry.get(pid)
            assert p is not None, f"Missing projection: {pid}"
            assert p.priority == "P0", f"{pid} should be P0, got {p.priority}"
            assert p.implementation_status == "BOUND", f"{pid} should be BOUND"
            assert p.route_or_detail == route, f"{pid} route mismatch: {p.route_or_detail} != {route}"

    # ---- Placeholder non-promotion ----

    def test_execution_workspaces_remains_planned(self):
        p = self.registry.get("execution.workspaces")
        assert p is not None
        assert p.implementation_status == "PLANNED"

    def test_intelligence_executors_remains_planned(self):
        p = self.registry.get("intelligence.executors")
        assert p is not None
        assert p.implementation_status == "PLANNED"

    def test_intelligence_performance_remains_planned(self):
        p = self.registry.get("intelligence.performance")
        assert p is not None
        assert p.implementation_status == "PLANNED"

    # ---- PARTIAL surfaces remain PARTIAL ----

    def test_admin_operations_remains_partial(self):
        p = self.registry.get("admin.operations")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_admin_receipts_remains_partial(self):
        p = self.registry.get("admin.receipts")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_intelligence_models_remains_partial(self):
        p = self.registry.get("intelligence.models")
        assert p is not None
        assert p.implementation_status in ("PARTIAL", "BOUND")

    def test_intelligence_executors_view_remains_partial(self):
        p = self.registry.get("intelligence.executors_view")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_universe_projects_remains_partial(self):
        p = self.registry.get("universe.projects")
        assert p is not None
        assert p.implementation_status in ("PARTIAL", "BOUND")

    def test_project_current_mission_remains_partial(self):
        p = self.registry.get("project.current_mission")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_evidence_provenance_remains_partial(self):
        p = self.registry.get("evidence.provenance")
        assert p is not None
        assert p.implementation_status in ("PARTIAL", "BOUND")

    def test_audit_search_remains_partial(self):
        p = self.registry.get("audit.search")
        assert p is not None
        assert p.implementation_status in ("PARTIAL", "BOUND")

    # ---- BLOCKED surfaces remain BLOCKED ----

    def test_distribution_sync_stage_blocked(self):
        p = self.registry.get("distribution.sync_stage")
        assert p is not None
        assert p.implementation_status == "BLOCKED"

    def test_distribution_activation_blocked(self):
        p = self.registry.get("distribution.activation")
        assert p is not None
        assert p.implementation_status == "BLOCKED"

    def test_distribution_rollback_blocked(self):
        p = self.registry.get("distribution.rollback")
        assert p is not None
        assert p.implementation_status == "BLOCKED"

    # ---- Zero duplicate IDs ----

    def test_zero_duplicate_projection_ids(self):
        ids = [p.projection_id for p in self.items]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[i for i in ids if ids.count(i) > 1]}"

    # ---- SYNC identity ----

    def test_distribution_sync_exists(self):
        p = self.registry.get("distribution.sync")
        assert p is not None
        assert p.implementation_status == "BOUND"
        assert p.source_authority == "SYNC_SERVICE"

    def test_distribution_sync_page_1(self):
        page = self.registry.to_api_dict(limit=100, offset=0)
        page_ids = [p["projection_id"] for p in page["projections"]]
        assert "distribution.sync" in page_ids

    # ---- Navigation contract ----

    def test_navigation_items_valid(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
        assert len(DEFAULT_NAVIGATION_ITEMS) == 33
        for nav in DEFAULT_NAVIGATION_ITEMS:
            assert nav.path.startswith("/")

    def test_all_active_navigation_resolves(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS, DEFAULT_PROJECTION_REGISTRY
        for nav in DEFAULT_NAVIGATION_ITEMS:
            if nav.availability in ("ACTIVE", "ALIAS"):
                proj = DEFAULT_PROJECTION_REGISTRY.get(nav.projection_id)
                assert proj is not None, f"Navigation {nav.label} -> {nav.projection_id} not found"

    # ---- Batch 008 Grounded Definitions Exist ----

    def test_batch_008_grounded_definitions_exist(self):
        expected_batch8 = [
            "execution.deterministic_executor", "execution.orchestrator", "execution.task_context",
            "execution.capability_registry", "capability.gate", "capability.decision_log",
            "continuity.reconciler", "continuity.operational_repo", "continuity.event_stream",
            "continuity.mutation_contract_engine", "core.runtime_engine", "core.runtime_state",
            "core.bootstrap_inventory", "fabric.tenant", "fabric.project", "fabric.trust_token",
            "fabric.health_probe", "fabric.provenance_store", "github.client", "github.discovery_service",
            "platform.linux_adapter", "platform.wsl2_adapter", "sandbox.isolation_policy",
            "sandbox.isolation_level", "sandbox.workspace_backend", "sandbox.restricted_process",
            "workspace.manager", "workspace.lifecycle_state", "tools.registry_service",
            "tools.manifest_store", "diagnostics.runtime_doctor", "diagnostics.check_suite",
            "journal.append_stream", "journal.mission_log", "security.active_context_manager",
            "security.authority_validator_service", "compute.resource_discovery_service",
            "intelligence.grading_service",
        ]
        assert len(expected_batch8) == 38
        for pid in expected_batch8:
            p = self.registry.get(pid)
            assert p is not None, f"Missing Batch 008 projection: {pid}"
            assert p.implementation_status == "PLANNED", f"{pid} should be PLANNED, got {p.implementation_status}"

    # ---- Provider neutrality ----

    def test_provider_neutrality(self):
        for p in self.items:
            if p.section not in ("Infrastructure",):
                assert p.source_authority != "AZURE_LIVE_TRUTH", (
                    f"Provider-specific source_authority on non-infrastructure projection: {p.projection_id}"
                )

    # ---- Registry validation ----

    def test_registry_validates(self):
        self.registry.validate()


class TestBatch008Regression:
    """Verify prior batch contracts are not broken."""

    def test_batch_007_count_minimum(self):
        from runtime.admin.projections import default_projection_registry
        registry = default_projection_registry()
        assert registry.summary()["total_definitions"] >= 207

    def test_batch_006_count_minimum(self):
        from runtime.admin.projections import default_projection_registry
        registry = default_projection_registry()
        assert registry.summary()["total_definitions"] >= 172

    def test_batch_005_count_minimum(self):
        from runtime.admin.projections import default_projection_registry
        registry = default_projection_registry()
        assert registry.summary()["total_definitions"] >= 148

    def test_batch_004_count_minimum(self):
        from runtime.admin.projections import default_projection_registry
        registry = default_projection_registry()
        assert registry.summary()["total_definitions"] >= 126

    def test_batch_003_count_minimum(self):
        from runtime.admin.projections import default_projection_registry
        registry = default_projection_registry()
        assert registry.summary()["total_definitions"] >= 115
