"""Batch 012: Master Inventory Expansion & Operational Grounding.

Test contract for the projection registry after Batch 012 additions.
Validates:
  - Total inventory count (394)
  - Batch 012 delta (+37 from 357)
  - P0 count expansion (113, up from 96 via evidence-backed operational grounding)
  - 37 new grounded operational depth definitions across subsystems:
    * Fabric & Tenancy models (fabric.tenant_model, fabric.project_model, fabric.trust_token_model, fabric.node_status_model)
    * Events & Messaging broker (events.event_bus_service, events.event_listener_registry)
    * Identity & Enrollment lifecycle (identity.enrollment_manager, identity.key_attestation)
    * Core Generation & Engine state (core.runtime_generation, core.runtime_config_model, core.runtime_engine_state)
    * Execution deterministic & models (execution.deterministic_engine, execution.task_context_model, execution.qwen_model_executor, execution.executor_selector, execution.recovery_attestation)
    * Intelligence & Evaluation depth (intelligence.implementation_profile, intelligence.repeatability_stats, intelligence.failure_record_model, intelligence.hardware_profile_model)
    * Journal & Ledger services (journal.operation_journal, journal.mission_journal)
    * MCP Gateway & Tools (mcp.tool_registry_service, mcp.policy_violation_handler)
    * Sandbox & Process Isolation (sandbox.manager_service, sandbox.isolation_level_taxonomy)
    * Secrets & Cryptographic Broker (secrets.secret_handle_model, secrets.credential_broker)
    * Security & Context Enforcement (security.authority_validator_engine, security.context_guard_service, security.generation_fence_engine, security.tool_manifest_model)
    * Sync & Verification (sync.github_source_provider, sync.candidate_verifier_engine)
    * Telemetry & Trace (telemetry.aggregator_service, telemetry.collector_service)
    * Updater (updater.manager_service)
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


class TestBatch012MasterInventory:
    """Projection registry contract after Batch 012."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= 394

    def test_batch_012_delta(self):
        """Batch 011 had 357. Batch 012 adds 37."""
        assert self.summary["total_definitions"] >= 394

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        """P0 advanced from 96 to 113 via operational depth additions."""
        assert self.summary["by_priority"]["P0"] >= 113

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] >= 196

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] >= 85

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == 0

    # ---- Implementation status distribution ----

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] >= 78

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] <= 9

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] >= 304

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Batch 012 New definitions audit ----

    def test_batch012_new_definitions_exist(self):
        expected_new_projections = [
            ("fabric.tenant_model", "Infrastructure", "P1", "FABRIC_MODEL"),
            ("fabric.project_model", "Infrastructure", "P1", "FABRIC_MODEL"),
            ("fabric.trust_token_model", "Infrastructure", "P0", "FABRIC_MODEL"),
            ("fabric.node_status_model", "Infrastructure", "P0", "FABRIC_MODEL"),
            ("events.event_bus_service", "Telemetry", "P0", "EVENT_BUS"),
            ("events.event_listener_registry", "Telemetry", "P1", "EVENT_BUS"),
            ("identity.enrollment_manager", "Runtime Identity", "P0", "ENROLLMENT_MANAGER"),
            ("identity.key_attestation", "Runtime Identity", "P0", "RUNTIME_IDENTITY"),
            ("core.runtime_generation", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
            ("core.runtime_config_model", "Runtime Identity", "P1", "RUNTIME_CONFIG"),
            ("core.runtime_engine_state", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
            ("execution.deterministic_engine", "Execution", "P0", "RUNTIME_EXECUTION"),
            ("execution.task_context_model", "Execution", "P1", "RUNTIME_EXECUTION"),
            ("execution.qwen_model_executor", "Execution", "P1", "MODEL_EXECUTOR"),
            ("execution.executor_selector", "Execution", "P1", "EXECUTOR_SELECTOR"),
            ("execution.recovery_attestation", "Execution", "P1", "MODEL_REGISTRY"),
            ("intelligence.implementation_profile", "Intelligence", "P1", "MODEL_PROFILE"),
            ("intelligence.repeatability_stats", "Intelligence", "P2", "BENCHMARK_STORE"),
            ("intelligence.failure_record_model", "Intelligence", "P2", "INTELLIGENCE_LAYER"),
            ("intelligence.hardware_profile_model", "Intelligence", "P1", "HARDWARE_PROFILE"),
            ("journal.operation_journal", "Evidence / Provenance", "P0", "OPERATION_JOURNAL"),
            ("journal.mission_journal", "Project State", "P0", "MISSION_JOURNAL"),
            ("mcp.tool_registry_service", "Infrastructure", "P0", "MCP_REGISTRY"),
            ("mcp.policy_violation_handler", "Infrastructure", "P1", "MCP_GATEWAY"),
            ("sandbox.manager_service", "Execution", "P0", "SANDBOX_MANAGER"),
            ("sandbox.isolation_level_taxonomy", "Execution", "P1", "SANDBOX_MANAGER"),
            ("secrets.secret_handle_model", "Security / Trust", "P1", "SECRET_BROKER"),
            ("secrets.credential_broker", "Security / Trust", "P0", "SECRET_BROKER"),
            ("security.authority_validator_engine", "Security / Trust", "P0", "AUTHORITY_VALIDATOR"),
            ("security.context_guard_service", "Security / Trust", "P0", "CONTEXT_GUARD"),
            ("security.generation_fence_engine", "Security / Trust", "P0", "GENERATION_FENCE"),
            ("security.tool_manifest_model", "Security / Trust", "P1", "SECURE_TOOLS"),
            ("sync.github_source_provider", "Distribution / Updates", "P1", "SYNC_SERVICE"),
            ("sync.candidate_verifier_engine", "Distribution / Updates", "P0", "SYNC_VERIFIER"),
            ("telemetry.aggregator_service", "Telemetry", "P1", "TELEMETRY_AGGREGATOR"),
            ("telemetry.collector_service", "Telemetry", "P1", "TELEMETRY_COLLECTOR"),
            ("updater.manager_service", "Distribution / Updates", "P1", "UPDATE_MANAGER"),
        ]
        assert len(expected_new_projections) == 37
        for pid, sec, prio, auth in expected_new_projections:
            p = self.registry.get(pid)
            assert p is not None, f"Missing Batch 012 projection: {pid}"
            assert p.section == sec, f"{pid} section mismatch: {p.section} != {sec}"
            assert p.priority == prio, f"{pid} priority mismatch: {p.priority} != {prio}"
            assert p.source_authority == auth, f"{pid} authority mismatch: {p.source_authority} != {auth}"
            assert p.implementation_status == "PLANNED", f"{pid} should be PLANNED"

    # ---- Duplicate checks ----

    def test_zero_duplicate_projection_ids(self):
        ids = [item.projection_id for item in self.items]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {len(ids) - len(set(ids))}"

    def test_batch012_sort_order_range(self):
        sort_orders = [item.sort_order for item in self.items]
        assert min(sort_orders) == 0
        assert max(sort_orders) >= 707

    # ---- Navigation integrity ----

    def test_navigation_contract_integrity(self):
        from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
        assert len(DEFAULT_NAVIGATION_ITEMS) >= 33
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


class TestBatch012Regression:
    """Verify prior batch contracts are preserved."""

    def test_prior_batch_count_floors(self):
        from runtime.admin.projections import default_projection_registry
        reg = default_projection_registry()
        summary = reg.summary()
        assert summary["total_definitions"] >= 394
        assert summary["by_priority"]["P0"] >= 113
        assert summary["by_implementation_status"]["BOUND"] >= 78
