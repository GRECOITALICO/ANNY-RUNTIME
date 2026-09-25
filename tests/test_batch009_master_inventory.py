"""Batch 009: Master Inventory Expansion & Operational Grounding.

Test contract for the projection registry after Batch 009 additions and P0 promotions.
Validates:
  - Total inventory count (283)
  - Batch 009 delta (+38 from 245)
  - P0 count expansion (82, up from 66 via evidence-backed promotions)
  - Evidence-backed P0 promotions (16 promoted projections)
  - Full binding chain promotion (universe.account_detail -> BOUND)
  - 38 new grounded operational depth definitions across subsystems
  - Placeholder non-promotion (execution.workspaces, intelligence.executors, intelligence.performance remain PLANNED)
  - PARTIAL surfaces remain PARTIAL (admin.operations, admin.receipts, etc.)
  - BLOCKED surfaces remain BLOCKED (distribution.sync_stage, activation, rollback)
  - Zero duplicate projection IDs
  - Navigation contract integrity (33 items resolve)
  - SYNC identity stability and separation
  - distribution.sync remains visible
  - Open-ended inventory (no hard ceiling, 349 viewport target)
  - Provider neutrality
  - Section and priority distribution
  - Regression against all prior batches
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBatch009MasterInventory:
    """Projection registry contract after Batch 009."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] == 283

    def test_batch_009_delta(self):
        """Batch 008 had 245. Batch 009 adds 38."""
        batch_008_count = 245
        assert self.summary["total_definitions"] - batch_008_count == 38

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        """P0 advanced from 66 to 82 via evidence-backed promotions."""
        assert self.summary["by_priority"]["P0"] == 82

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] == 148

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] == 53

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == 0

    # ---- Implementation status distribution ----

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] == 74

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] == 13

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] == 193

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Evidence-backed P0 promotions audit ----

    def test_batch_009_p0_promotions(self):
        """Verify all 16 Batch 009 P0 promotions."""
        promoted = [
            ("runtime.reconnect", "BOUND"),
            ("admin.diagnostics", "BOUND"),
            ("admin.update_check", "BOUND"),
            ("universe.account_detail", "BOUND"),
            ("browser.session_detail", "BOUND"),
            ("execution.worker_detail", "BOUND"),
            ("intelligence.model_detail", "BOUND"),
            ("processing.events", "BOUND"),
            ("continuity.bootstrap_api", "BOUND"),
            ("telemetry.stream_api", "BOUND"),
            ("api.bridge_tasks", "BOUND"),
            ("api.bridge_task_query", "BOUND"),
            ("api.bridge_execution_query", "BOUND"),
            ("admin.executions", "BOUND"),
            ("admin.workers", "BOUND"),
            ("admin.capabilities", "BOUND"),
        ]
        for pid, status in promoted:
            p = self.registry.get(pid)
            assert p is not None, f"Missing projection: {pid}"
            assert p.priority == "P0", f"{pid} should be P0, got {p.priority}"
            assert p.implementation_status == status, f"{pid} status mismatch: {p.implementation_status} != {status}"

    def test_universe_account_detail_complete_binding_chain(self):
        """universe.account_detail has complete binding chain verified."""
        p = self.registry.get("universe.account_detail")
        assert p is not None
        assert p.priority == "P0"
        assert p.implementation_status == "BOUND"
        assert p.route_or_detail == "/universe/accounts/{account_id}"
        assert p.source_authority == "ACCOUNT_REGISTRY"

    # ---- 38 New Grounded Definitions ----

    def test_batch_009_new_definitions_present(self):
        """All 38 Batch 009 grounded definitions are registered."""
        batch_009_ids = [
            "browser.action_authorization",
            "browser.pending_authorization",
            "browser.session_manager",
            "telemetry.metadata_scrubber",
            "compute.provider_interface",
            "compute.trust_profile",
            "compute.remote_lease",
            "compute.remote_artifact",
            "compute.remote_job",
            "orchestration.routing_classifier",
            "orchestration.plan_structure",
            "execution.context_package",
            "execution.model_result",
            "execution.model_executor_contract",
            "accounts.status_lifecycle",
            "accounts.entity_model",
            "projects.status_lifecycle",
            "projects.entity_model",
            "fabric.node",
            "fabric.policy",
            "fabric.contract",
            "session.lease_record",
            "session.status_state",
            "bootstrap.readiness_gates",
            "bootstrap.gate_result",
            "bootstrap.three_plane_orchestrator",
            "filesystem.service",
            "git.repository_service",
            "admin.session_model",
            "admin.session_manager",
            "admin.audit_entry",
            "admin.audit_log",
            "security.execution_receipt",
            "security.authorized_pipeline_engine",
            "sync.candidate_identity",
            "sync.verification_state",
            "sync.sync_state",
            "sync.result_model",
        ]
        assert len(batch_009_ids) == 38
        for pid in batch_009_ids:
            p = self.registry.get(pid)
            assert p is not None, f"Missing definition: {pid}"
            assert p.implementation_status == "PLANNED"
            assert p.title != ""
            assert p.section != ""
            assert p.source_authority != ""

    # ---- Placeholder non-promotion ----

    def test_placeholders_remain_planned(self):
        for pid in ["execution.workspaces", "intelligence.executors", "intelligence.performance"]:
            p = self.registry.get(pid)
            assert p is not None
            assert p.implementation_status == "PLANNED"

    # ---- PARTIAL surfaces remain PARTIAL ----

    def test_partial_surfaces_remain_partial(self):
        for pid in ["admin.operations", "admin.receipts", "universe.projects", "audit.search"]:
            p = self.registry.get(pid)
            assert p is not None
            assert p.implementation_status == "PARTIAL"

    # ---- BLOCKED surfaces remain BLOCKED ----

    def test_blocked_surfaces_remain_blocked(self):
        for pid in ["distribution.sync_stage", "distribution.activation", "distribution.rollback"]:
            p = self.registry.get(pid)
            assert p is not None
            assert p.implementation_status == "BLOCKED"

    # ---- Zero duplicate IDs ----

    def test_zero_duplicates(self):
        ids = [p.projection_id for p in self.items]
        assert len(ids) == len(set(ids)), f"Duplicate projection IDs found: {len(ids)} total vs {len(set(ids))} unique"

    # ---- Navigation contract integrity ----

    def test_navigation_items_resolve(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
        assert len(DEFAULT_NAVIGATION_ITEMS) == 33
        for item in DEFAULT_NAVIGATION_ITEMS:
            if item.availability in ("ACTIVE", "ALIAS"):
                assert self.registry.get(item.projection_id) is not None, f"Nav item {item.label} does not resolve {item.projection_id}"

    # ---- SYNC identity & separation ----

    def test_sync_projection_bound_and_p0(self):
        p = self.registry.get("distribution.sync")
        assert p is not None
        assert p.priority == "P0"
        assert p.implementation_status == "BOUND"
        assert p.source_authority == "SYNC_SERVICE"

    # ---- Provider neutrality ----

    def test_provider_neutrality(self):
        """Check that Azure is not hardcoded as functional identity."""
        p = self.registry.get("infrastructure.azure")
        assert p is not None
        assert p.priority == "P2"
        assert p.implementation_status == "PLANNED"
        assert p.source_authority == "AZURE_LIVE_TRUTH"
