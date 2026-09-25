"""Batch 016: Master Inventory Expansion test suite.

Validates the Projection Registry contract following Batch 016 expansion:
- Total definitions: 559 (+36 from Batch 015's 523)
- P0 expansion to 268 (up from 232), grounded in verified runtime source modules
- All 36 new definitions verified against their source authority and subsystem
- Regression floors from prior batches preserved
"""

import pytest
from runtime.admin.projections import (
    default_projection_registry,
    DEFAULT_NAVIGATION_ITEMS,
    DEFAULT_PROJECTION_REGISTRY,
    INITIAL_P0_VIEWPORT_TARGET,
    MASTER_INVENTORY_BOUNDARY,
    audit_navigation_contract,
)
from runtime.admin.routes import AdminRouter


BATCH_016_TOTAL = 559
BATCH_015_TOTAL = 523
BATCH_016_DELTA = BATCH_016_TOTAL - BATCH_015_TOTAL  # 36
BATCH_016_P0 = 268
BATCH_016_P1 = 206
BATCH_016_P2 = 85
BATCH_016_P3 = 0
BATCH_016_BOUND = 78
BATCH_016_PARTIAL = 9
BATCH_016_BLOCKED = 3
BATCH_016_PLANNED = 469


class TestBatch016MasterInventory:
    """Validates Batch 016 projection registry contract."""

    def setup_method(self):
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= BATCH_016_TOTAL

    def test_batch_016_delta(self):
        batch_016_items = [p for p in self.items if 837 <= p.sort_order <= 872]
        assert len(batch_016_items) == BATCH_016_DELTA

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    def test_p0_count(self):
        assert self.summary["by_priority"]["P0"] >= BATCH_016_P0

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] == BATCH_016_P1

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] == BATCH_016_P2

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == BATCH_016_P3

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] == BATCH_016_BOUND

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] == BATCH_016_PARTIAL

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == BATCH_016_BLOCKED

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] >= BATCH_016_PLANNED

    def test_batch016_new_definitions(self):
        """Verify all 36 Batch 016 projections exist with correct grounding."""
        expected = [
            ("core.runtime_state_machine", "Infrastructure", "P0", "RUNTIME_ENGINE"),
            ("core.runtime_config", "Infrastructure", "P0", "RUNTIME_CONFIG"),
            ("core.inventory_discovery", "Infrastructure", "P0", "INVENTORY_DISCOVERY"),
            ("core.generation_identity", "Runtime Identity", "P0", "RUNTIME_GENERATION"),
            ("execution.task_model", "Execution", "P0", "EXECUTION_MODELS"),
            ("execution.execution_result_model", "Execution", "P0", "EXECUTION_MODELS"),
            ("execution.execution_status_taxonomy", "Execution", "P0", "EXECUTION_MODELS"),
            ("execution.model_definition", "Execution", "P0", "EXECUTION_MODELS"),
            ("execution.model_capability_binding", "Execution", "P0", "EXECUTION_MODELS"),
            ("execution.hardware_profile", "Infrastructure", "P0", "EXECUTION_MODELS"),
            ("execution.model_performance_profile", "Intelligence", "P0", "EXECUTION_MODELS"),
            ("execution.tool_invocation_model", "Execution", "P0", "EXECUTION_ORCHESTRATOR"),
            ("execution.capability_definition", "Execution", "P0", "CAPABILITY_REGISTRY"),
            ("execution.model_registry_service", "Execution", "P0", "MODEL_REGISTRY"),
            ("security.grant_store", "Security / Trust", "P0", "AUTH_STORE"),
            ("security.grant_model", "Security / Trust", "P0", "AUTH_STORE"),
            ("security.context_guard_engine", "Security / Trust", "P0", "CONTEXT_GUARD"),
            ("security.active_context_lifecycle", "Security / Trust", "P0", "ACTIVE_CONTEXT"),
            ("session.lease_model", "Communication", "P0", "SESSION_LEASE"),
            ("session.status_taxonomy", "Communication", "P0", "SESSION_LEASE"),
            ("session.lifecycle_manager", "Communication", "P0", "SESSION_MANAGER"),
            ("continuity.reconciler_engine", "Continuity", "P0", "CONTINUITY_RECONCILER"),
            ("continuity.event_type_taxonomy", "Continuity", "P0", "CONTINUITY_EVENTS"),
            ("sync.service_engine", "Distribution / Updates", "P0", "SYNC_SERVICE"),
            ("sync.candidate_identity_model", "Distribution / Updates", "P0", "SYNC_MODELS"),
            ("sync.sync_state_machine", "Distribution / Updates", "P0", "SYNC_MODELS"),
            ("sync.sync_result_model", "Distribution / Updates", "P0", "SYNC_MODELS"),
            ("intelligence.capability_tier_taxonomy", "Intelligence", "P0", "INTELLIGENCE_MODELS"),
            ("intelligence.delegation_decision_model", "Intelligence", "P0", "INTELLIGENCE_MODELS"),
            ("intelligence.certification_status_model", "Intelligence", "P0", "INTELLIGENCE_MODELS"),
            ("intelligence.capability_assessment", "Intelligence", "P0", "INTELLIGENCE_MODELS"),
            ("intelligence.grading_result_model", "Intelligence", "P0", "GRADING_ENGINE"),
            ("intelligence.benchmark_store_service", "Intelligence", "P0", "BENCHMARK_STORE"),
            ("admin.sync_ui_injector", "Control Center", "P0", "SYNC_UI"),
            ("core.critical_access_report", "Security / Trust", "P0", "ACCESS_VERIFIER"),
            ("admin.audit_persistence", "Evidence / Provenance", "P0", "ADMIN_AUDIT"),
        ]

        assert len(expected) == BATCH_016_DELTA, (
            f"Expected {BATCH_016_DELTA} definitions, listed {len(expected)}"
        )

        for pid, section, priority, authority in expected:
            defn = self.registry.get(pid)
            assert defn is not None, f"Missing projection: {pid}"
            assert defn.section == section, f"{pid}: expected section={section}, got {defn.section}"
            assert defn.priority == priority, f"{pid}: expected priority={priority}, got {defn.priority}"
            assert defn.source_authority == authority, f"{pid}: expected authority={authority}, got {defn.source_authority}"
            assert defn.implementation_status == "PLANNED", f"{pid}: expected PLANNED, got {defn.implementation_status}"

    def test_zero_duplicate_projection_ids(self):
        ids = [item.projection_id for item in self.items]
        assert len(ids) == len(set(ids)), "Duplicate projection IDs detected"

    def test_batch016_sort_order_range(self):
        sort_orders = [item.sort_order for item in self.items]
        assert min(sort_orders) == 0
        assert max(sort_orders) >= 872

    def test_navigation_contract_integrity(self):
        assert len(DEFAULT_NAVIGATION_ITEMS) >= 33
        for nav in DEFAULT_NAVIGATION_ITEMS:
            if nav.availability in {"ACTIVE", "ALIAS"}:
                assert DEFAULT_PROJECTION_REGISTRY.get(nav.projection_id) is not None, (
                    f"Navigation item '{nav.label}' references unregistered projection: {nav.projection_id}"
                )

    def test_navigation_contract_is_operator_inspectable_and_valid(self):
        audit = audit_navigation_contract(
            DEFAULT_NAVIGATION_ITEMS,
            AdminRouter({})._get_routes,
        )
        assert audit["status"] == "VALID"
        assert audit["registered_projection_ids"] == {"valid": 18, "total": 18}
        assert audit["active_or_alias_destinations"] == 18
        assert audit["planned_destinations"] >= 15
        assert audit["dead_links"] == []
        assert audit["stale_aliases"] == []
        assert audit["duplicate_destinations"] == []
        assert audit["false_online_declarations"] == []

    def test_partial_surfaces_unchanged(self):
        partial = [item for item in self.items if item.implementation_status == "PARTIAL"]
        partial_ids = {item.projection_id for item in partial}
        expected_partial = {
            "admin.operations", "admin.receipts", "intelligence.executors_view",
            "conrrad.required_services", "project.current_mission", "project.current_task",
            "project.next_action", "project.blockers", "security.trust",
        }
        assert partial_ids == expected_partial

    def test_blocked_surfaces_unchanged(self):
        blocked = [item for item in self.items if item.implementation_status == "BLOCKED"]
        blocked_ids = {item.projection_id for item in blocked}
        expected_blocked = {"distribution.sync_stage", "distribution.activation", "distribution.rollback"}
        assert blocked_ids == expected_blocked

    def test_sync_separation_invariants(self):
        sync_def = self.registry.get("distribution.sync")
        assert sync_def is not None
        assert sync_def.implementation_status == "BOUND"

    def test_provider_neutrality(self):
        azure = self.registry.get("infrastructure.azure")
        assert azure is not None
        assert azure.priority == "P2"
        assert azure.implementation_status == "PLANNED"

    def test_freshness_invariants(self):
        for item in self.items:
            if item.implementation_status == "BOUND":
                assert item.freshness == "LIVE_ON_READ", f"{item.projection_id}: BOUND must have LIVE_ON_READ"
            if item.implementation_status == "PLANNED":
                assert item.freshness == "NOT_BOUND", f"{item.projection_id}: PLANNED must have NOT_BOUND"

    def test_registry_validates(self):
        self.registry.validate()


class TestBatch016Regression:
    def test_prior_batch_count_floors(self):
        registry = default_projection_registry()
        summary = registry.summary()
        assert summary["total_definitions"] >= BATCH_016_TOTAL
        assert summary["by_priority"]["P0"] >= BATCH_016_P0
        assert summary["by_implementation_status"]["BOUND"] >= BATCH_016_BOUND
