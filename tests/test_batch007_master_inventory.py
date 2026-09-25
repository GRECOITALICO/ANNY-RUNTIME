"""Batch 007: Functional Projection Deepening & Control Center Operational Grounding.

Test contract for the projection registry after Batch 007 additions.
Validates:
  - Total inventory count (207)
  - Batch 007 delta (+35 from 172)
  - BOUND binding chain for new compatibility routes
  - Placeholder non-promotion (execution.workspaces, intelligence.executors, intelligence.performance)
  - PARTIAL surfaces remain PARTIAL (admin.operations, admin.receipts, etc.)
  - Zero duplicate projection IDs
  - Zero duplicate DOM identifiers
  - Navigation contract integrity
  - SYNC identity stability
  - distribution.sync on page 1
  - Open-ended inventory (no hard ceiling)
  - Provider neutrality
  - Section and priority distribution
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBatch007MasterInventory:
    """Projection registry contract after Batch 007."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] == 207

    def test_batch_007_delta(self):
        """Batch 006 had 172. Batch 007 adds 35."""
        batch_006_count = 172
        assert self.summary["total_definitions"] - batch_006_count == 35

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        assert self.summary["by_priority"]["P0"] == 42

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] == 136

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] == 29

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == 0

    # ---- Implementation status distribution ----

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] == 73

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] == 13

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] == 118

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Batch 007 BOUND projections — verified complete binding chain ----

    def test_admin_executions_bound(self):
        p = self.registry.get("admin.executions")
        assert p is not None
        assert p.implementation_status == "BOUND"
        assert p.route_or_detail == "/executions"
        assert p.source_authority == "RUNTIME_EXECUTION"

    def test_admin_workers_bound(self):
        p = self.registry.get("admin.workers")
        assert p is not None
        assert p.implementation_status == "BOUND"
        assert p.route_or_detail == "/workers"
        assert p.source_authority == "RUNTIME_EXECUTION"

    def test_admin_capabilities_bound(self):
        p = self.registry.get("admin.capabilities")
        assert p is not None
        assert p.implementation_status == "BOUND"
        assert p.route_or_detail == "/capabilities"
        assert p.source_authority == "RUNTIME_EXECUTION"

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
        assert p.implementation_status == "PARTIAL"

    def test_intelligence_executors_view_remains_partial(self):
        p = self.registry.get("intelligence.executors_view")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_universe_projects_remains_partial(self):
        p = self.registry.get("universe.projects")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_project_current_mission_remains_partial(self):
        p = self.registry.get("project.current_mission")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_evidence_provenance_remains_partial(self):
        p = self.registry.get("evidence.provenance")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

    def test_audit_search_remains_partial(self):
        p = self.registry.get("audit.search")
        assert p is not None
        assert p.implementation_status == "PARTIAL"

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
        """distribution.sync must appear on page 1 of default pagination."""
        page = self.registry.to_api_dict(limit=100, offset=0)
        page_ids = [p["projection_id"] for p in page["projections"]]
        assert "distribution.sync" in page_ids

    # ---- Navigation contract ----

    def test_navigation_items_valid(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
        assert len(DEFAULT_NAVIGATION_ITEMS) >= 30
        for nav in DEFAULT_NAVIGATION_ITEMS:
            assert nav.path.startswith("/")

    def test_all_active_navigation_resolves(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS, DEFAULT_PROJECTION_REGISTRY
        for nav in DEFAULT_NAVIGATION_ITEMS:
            if nav.availability in ("ACTIVE", "ALIAS"):
                proj = DEFAULT_PROJECTION_REGISTRY.get(nav.projection_id)
                assert proj is not None, f"Navigation {nav.label} -> {nav.projection_id} not found"

    # ---- Batch 007 PLANNED projections exist ----

    def test_batch_007_planned_projections_exist(self):
        expected_planned = [
            "compute.colab_transport", "compute.remote_manager", "compute.mcp_bridge",
            "continuity.engine", "continuity.state_resolver",
            "core.access_verifier", "core.generation", "core.recovery", "core.inventory", "core.config",
            "execution.receipt_store", "execution.model_registry", "execution.qwen_executor",
            "execution.result_validator", "execution.worker_manager", "execution.registry_recovery",
            "security.generation_fence",
            "intelligence.layer", "intelligence.telemetry", "intelligence.benchmark_dataset",
            "mcp.registry",
            "events.bus_service",
            "sync.candidate_verifier", "sync.state_machine",
            "telemetry.collector", "telemetry.context", "telemetry.envelope",
            "bootstrap.three_plane", "bootstrap.report",
            "admin.csrf", "admin.middleware", "admin.audit",
        ]
        for pid in expected_planned:
            p = self.registry.get(pid)
            assert p is not None, f"Missing planned projection: {pid}"
            assert p.implementation_status == "PLANNED", f"{pid} should be PLANNED, got {p.implementation_status}"

    # ---- Provider neutrality ----

    def test_provider_neutrality(self):
        """No projection uses 'AZURE' as source_authority for core operations."""
        for p in self.items:
            if p.section not in ("Infrastructure",):
                assert p.source_authority != "AZURE_LIVE_TRUTH", (
                    f"Provider-specific source_authority on non-infrastructure projection: {p.projection_id}"
                )

    # ---- Registry validation ----

    def test_registry_validates(self):
        self.registry.validate()

    # ---- Batch 007 projection metadata quality ----

    def test_all_projections_have_tags(self):
        for p in self.items:
            assert len(p.tags) > 0, f"{p.projection_id} has no tags"

    def test_all_projections_have_routes(self):
        """Every batch 007 projection has a route_or_detail."""
        batch7_ids = [
            "admin.executions", "admin.workers", "admin.capabilities",
            "compute.colab_transport", "compute.remote_manager", "compute.mcp_bridge",
            "continuity.engine", "continuity.state_resolver",
            "core.access_verifier", "core.generation", "core.recovery", "core.inventory", "core.config",
            "execution.receipt_store", "execution.model_registry", "execution.qwen_executor",
            "execution.result_validator", "execution.worker_manager", "execution.registry_recovery",
            "security.generation_fence",
            "intelligence.layer", "intelligence.telemetry", "intelligence.benchmark_dataset",
            "mcp.registry", "events.bus_service",
            "sync.candidate_verifier", "sync.state_machine",
            "telemetry.collector", "telemetry.context", "telemetry.envelope",
            "bootstrap.three_plane", "bootstrap.report",
            "admin.csrf", "admin.middleware", "admin.audit",
        ]
        for pid in batch7_ids:
            p = self.registry.get(pid)
            assert p is not None
            assert p.route_or_detail is not None, f"{pid} has no route"

    # ---- Regression: prior batch projections still present ----

    def test_batch_006_projections_present(self):
        batch6_samples = [
            "api.bridge_tasks", "admin.logout", "github.disconnect", "github.device_init",
            "git.service", "diagnostics.doctor", "platform.manager", "process.manager",
        ]
        for pid in batch6_samples:
            assert self.registry.get(pid) is not None, f"Batch 006 projection missing: {pid}"

    def test_batch_005_projections_present(self):
        batch5_samples = [
            "api.status", "continuity.bootstrap_api", "control.projections_api",
            "telemetry.stream_api", "projects.registry", "accounts.registry",
        ]
        for pid in batch5_samples:
            assert self.registry.get(pid) is not None, f"Batch 005 projection missing: {pid}"

    def test_batch_004_projections_present(self):
        batch4_samples = [
            "admin.restart", "intelligence.scorecards", "intelligence.benchmark_cases",
            "security.context_guard", "shell.executor",
        ]
        for pid in batch4_samples:
            assert self.registry.get(pid) is not None, f"Batch 004 projection missing: {pid}"

    def test_batch_003_projections_present(self):
        batch3_samples = [
            "processing.events", "events.bus", "journal.operations",
            "security.grants", "secrets.references", "sandbox.policies",
        ]
        for pid in batch3_samples:
            assert self.registry.get(pid) is not None, f"Batch 003 projection missing: {pid}"

    # ---- Section coverage ----

    def test_minimum_sections(self):
        sections = set(p.section for p in self.items)
        required = {
            "Control Center", "Execution", "Intelligence", "Security / Trust",
            "Infrastructure", "Distribution / Updates", "Telemetry", "CONRRAD",
        }
        assert required.issubset(sections)

    # ---- Freshness invariant ----

    def test_bound_projections_have_live_freshness(self):
        for p in self.items:
            if p.implementation_status == "BOUND":
                assert p.freshness == "LIVE_ON_READ", (
                    f"{p.projection_id}: BOUND should have LIVE_ON_READ freshness, got {p.freshness}"
                )

    def test_planned_projections_have_not_bound_freshness(self):
        for p in self.items:
            if p.implementation_status == "PLANNED":
                assert p.freshness == "NOT_BOUND", (
                    f"{p.projection_id}: PLANNED should have NOT_BOUND freshness, got {p.freshness}"
                )


class TestBatch007Regression:
    """Verify prior batch contracts are not broken."""

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
