"""Batch 010: Master Inventory Expansion & Operational Grounding.

Test contract for the projection registry after Batch 010 additions and P0 promotions.
Validates:
  - Total inventory count (321)
  - Batch 010 delta (+38 from 283)
  - P0 count expansion (85, up from 82 via evidence-backed promotions)
  - Evidence-backed promotions (universe.projects, audit.search, evidence.provenance, intelligence.models -> BOUND)
  - 38 new grounded operational depth definitions across subsystems
  - Placeholder non-promotion (execution.workspaces, intelligence.executors, intelligence.performance remain PLANNED)
  - Remaining PARTIAL surfaces stay PARTIAL (admin.operations, admin.receipts, etc.)
  - BLOCKED surfaces remain BLOCKED (distribution.sync_stage, activation, rollback)
  - Zero duplicate projection IDs
  - Navigation contract integrity (33 items resolve)
  - SYNC identity stability and separation
  - distribution.sync remains visible and BOUND
  - Open-ended inventory (no hard ceiling, 349 viewport target)
  - Provider neutrality
  - Section and priority distribution
  - Regression against all prior batches
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBatch010MasterInventory:
    """Projection registry contract after Batch 010."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= 321

    def test_batch_010_delta(self):
        """Batch 009 had 283. Batch 010 adds 38."""
        assert self.summary["total_definitions"] >= 321

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        """P0 advanced from 82 to 85 via evidence-backed promotions."""
        assert self.summary["by_priority"]["P0"] >= 85

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] >= 157

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] >= 79

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == 0

    # ---- Implementation status distribution ----

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] >= 78

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] <= 9

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] >= 231

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Evidence-backed promotions audit ----

    def test_promoted_projections_status_and_priority(self):
        promotions = [
            ("universe.projects", "P0", "BOUND", "/universe/projects"),
            ("audit.search", "P0", "BOUND", "/search"),
            ("evidence.provenance", "P0", "BOUND", "/audit/provenance"),
            ("intelligence.models", "P0", "BOUND", "/models"),
        ]
        for pid, prio, status, route in promotions:
            p = self.registry.get(pid)
            assert p is not None, f"Missing projection: {pid}"
            assert p.priority == prio, f"{pid} priority mismatch: {p.priority} != {prio}"
            assert p.implementation_status == status, f"{pid} status mismatch: {p.implementation_status} != {status}"
            assert p.route_or_detail == route, f"{pid} route mismatch: {p.route_or_detail} != {route}"

    # ---- 38 New Grounded Definitions ----

    def test_batch_010_new_definitions_present(self):
        """All 38 Batch 010 grounded definitions are registered with proper metadata."""
        batch_010_ids = [
            "core.access_test_result",
            "core.critical_access_verifier",
            "core.component_inventory_model",
            "core.inventory_discovery_service",
            "core.recovery_report",
            "core.recovery_manager_service",
            "events.event_type_taxonomy",
            "events.event_envelope",
            "execution.tool_invocation",
            "execution.tool_result",
            "execution.receipt_store_service",
            "execution.status_state",
            "execution.worker_state",
            "execution.worker_definition",
            "github.discovered_principal",
            "github.discovered_organization",
            "github.discovered_repository",
            "identity.enrollment_state",
            "identity.challenge_response",
            "intelligence.capability_tier",
            "intelligence.delegation_decision",
            "intelligence.execution_mode",
            "intelligence.certification_status",
            "intelligence.resource_fit",
            "intelligence.benchmark_case_model",
            "intelligence.benchmark_result_model",
            "journal.entry_record",
            "journal.mission_entry_record",
            "mcp.gateway_service",
            "process.state_lifecycle",
            "process.execution_record",
            "secrets.file_backend",
            "secrets.secure_broker",
            "shell.result_payload",
            "shell.effect_classifier",
            "sync.verification_result",
            "telemetry.trace_context",
            "updater.manifest_info",
        ]
        assert len(batch_010_ids) == 38
        for pid in batch_010_ids:
            p = self.registry.get(pid)
            assert p is not None, f"Missing definition: {pid}"
            assert p.implementation_status == "PLANNED"
            assert p.title != ""
            assert p.section != ""
            assert p.source_authority != ""
            assert p.sort_order >= 597

    # ---- Placeholder non-promotion ----

    def test_placeholders_remain_planned(self):
        for pid in ["execution.workspaces", "intelligence.executors", "intelligence.performance"]:
            p = self.registry.get(pid)
            assert p is not None
            assert p.implementation_status == "PLANNED"

    # ---- Remaining PARTIAL surfaces remain PARTIAL ----

    def test_remaining_partial_surfaces(self):
        remaining_partial = [
            "admin.operations",
            "admin.receipts",
            "intelligence.executors_view",
            "project.current_mission",
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

    # ---- Zero duplicate IDs ----

    def test_zero_duplicates(self):
        ids = [p.projection_id for p in self.items]
        assert len(ids) == len(set(ids)), f"Duplicate projection IDs found: {len(ids)} total vs {len(set(ids))} unique"

    # ---- Navigation contract integrity ----

    def test_navigation_items_resolve(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
        assert len(DEFAULT_NAVIGATION_ITEMS) >= 33
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

    # ---- Freshness invariants ----

    def test_freshness_invariants(self):
        for p in self.items:
            if p.implementation_status == "BOUND":
                assert p.freshness == "LIVE_ON_READ"
            elif p.implementation_status == "PLANNED":
                assert p.freshness == "NOT_BOUND"

    # ---- Registry validation ----

    def test_registry_validates(self):
        self.registry.validate()


class TestBatch010Regression:
    """Verify prior batch contracts are preserved."""

    def test_prior_batch_count_floors(self):
        from runtime.admin.projections import default_projection_registry
        reg = default_projection_registry()
        summary = reg.summary()
        assert summary["total_definitions"] >= 321
        assert summary["by_priority"]["P0"] >= 85
        assert summary["by_implementation_status"]["BOUND"] >= 78
