"""Batch 013: Master Inventory Expansion & Operational Grounding.

Test contract for the projection registry after Batch 013 additions.
Validates:
  - Total inventory count (434)
  - Batch 013 delta (+40 from 394)
  - P0 count expansion (145, up from 113 via evidence-backed operational grounding)
  - 40 new grounded operational depth definitions across subsystems:
    * Identity & Attestation (identity.hardware_fingerprint, identity.session_attestation)
    * Fabric & Node Health (fabric.admission_validator, fabric.node_heartbeat)
    * GitHub Integration (github.rate_limit_monitor, github.scope_attestation)
    * Core Engine & Subsystems (core.lifecycle_controller, core.subsystem_manifest)
    * Execution & Workers (execution.worker_supervisor, execution.policy_enforcer, execution.result_validator_service)
    * Capabilities & Intelligence (capability.gate_evaluator, intelligence.evaluation_pipeline, intelligence.model_telemetry)
    * Accounts & Projects (accounts.authorization_profile, projects.workspace_mapping)
    * Telemetry & Events (telemetry.trace_pipeline, telemetry.domain_router, events.subscription_manager, events.delivery_attestation)
    * Browser Automation (browser.submission_guard, browser.broker_lifecycle)
    * Continuity & Journal (continuity.reconciler_service, journal.integrity_verifier)
    * Security & Sandbox & Secrets (security.grant_lifecycle, sandbox.execution_boundary, secrets.lease_manager)
    * Sync & Updates (sync.state_evaluator, updater.channel_governor)
    * MCP & Tools (mcp.gateway_interceptor, tools.invocation_pipeline)
    * Diagnostics & Bootstrap (diagnostics.health_evaluator, bootstrap.plane_validator)
    * Filesystem & Git & Process & Shell (filesystem.boundary_guard, git.working_tree_monitor, process.supervisor_service, shell.effect_guard)
    * Compute & Orchestration & Workspace (compute.resource_monitor, orchestration.scheduler_engine, workspace.isolation_guard)
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


class TestBatch013MasterInventory:
    """Projection registry contract after Batch 013."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= 434

    def test_batch_013_delta(self):
        """Batch 012 had 394. Batch 013 adds 40."""
        assert self.summary["total_definitions"] >= 434

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        """P0 advanced from 113 to 145 via operational depth additions."""
        assert self.summary["by_priority"]["P0"] >= 145

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] >= 204

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
        assert self.summary["by_implementation_status"]["PLANNED"] >= 344

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Batch 013 New definitions audit ----

    def test_batch013_new_definitions_exist(self):
        expected_new_projections = [
            ("identity.hardware_fingerprint", "Runtime Identity", "P0", "RUNTIME_IDENTITY"),
            ("identity.session_attestation", "Runtime Identity", "P0", "RUNTIME_IDENTITY"),
            ("fabric.admission_validator", "Repository Fabric", "P0", "FABRIC_LIVE_TRUTH"),
            ("fabric.node_heartbeat", "Repository Fabric", "P0", "FABRIC_LIVE_TRUTH"),
            ("github.rate_limit_monitor", "GitHub", "P0", "GITHUB_AUTH"),
            ("github.scope_attestation", "GitHub", "P1", "GITHUB_AUTH"),
            ("core.lifecycle_controller", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
            ("core.subsystem_manifest", "Runtime Identity", "P0", "RUNTIME_CONFIG"),
            ("execution.worker_supervisor", "Execution", "P0", "RUNTIME_EXECUTION"),
            ("execution.policy_enforcer", "Execution", "P0", "RUNTIME_EXECUTION"),
            ("execution.result_validator_service", "Execution", "P1", "MODEL_VALIDATOR"),
            ("capability.gate_evaluator", "Intelligence", "P0", "CAPABILITY_GATE"),
            ("intelligence.evaluation_pipeline", "Intelligence", "P1", "GRADING_ENGINE"),
            ("intelligence.model_telemetry", "Intelligence", "P1", "INTELLIGENCE_TELEMETRY"),
            ("accounts.authorization_profile", "Accounts / Identities", "P0", "ACCOUNT_REGISTRY"),
            ("projects.workspace_mapping", "Projects / Workspaces", "P0", "PROJECT_REGISTRY"),
            ("telemetry.trace_pipeline", "Telemetry", "P1", "TRACE_CONTEXT"),
            ("telemetry.domain_router", "Telemetry", "P0", "TELEMETRY_ROUTER"),
            ("events.subscription_manager", "Telemetry", "P0", "EVENT_BUS"),
            ("events.delivery_attestation", "Telemetry", "P0", "EVENT_BUS"),
            ("browser.submission_guard", "Browser", "P0", "BROWSER_AUTH"),
            ("browser.broker_lifecycle", "Browser", "P0", "BROWSER_BROKER"),
            ("continuity.reconciler_service", "Continuity", "P0", "CONTINUITY_RECONCILER"),
            ("journal.integrity_verifier", "Evidence / Provenance", "P0", "OPERATION_JOURNAL"),
            ("security.grant_lifecycle", "Security / Trust", "P0", "AUTHORIZATION_STORE"),
            ("sandbox.execution_boundary", "Execution", "P0", "SANDBOX_MANAGER"),
            ("secrets.lease_manager", "Security / Trust", "P0", "SECRET_BROKER"),
            ("sync.state_evaluator", "Distribution / Updates", "P0", "SYNC_SERVICE"),
            ("updater.channel_governor", "Distribution / Updates", "P1", "UPDATE_MANAGER"),
            ("mcp.gateway_interceptor", "Infrastructure", "P0", "MCP_GATEWAY"),
            ("tools.invocation_pipeline", "Infrastructure", "P1", "TOOL_REGISTRY"),
            ("diagnostics.health_evaluator", "Security / Trust", "P0", "RUNTIME_DOCTOR"),
            ("bootstrap.plane_validator", "CONRRAD", "P0", "BOOTSTRAP_ENGINE"),
            ("filesystem.boundary_guard", "Infrastructure", "P0", "FILESYSTEM_SERVICE"),
            ("git.working_tree_monitor", "Infrastructure", "P0", "GIT_SERVICE"),
            ("process.supervisor_service", "Execution", "P0", "PROCESS_MANAGER"),
            ("shell.effect_guard", "Execution", "P0", "SHELL_EXECUTOR"),
            ("compute.resource_monitor", "Infrastructure", "P1", "COMPUTE_DISCOVERY"),
            ("orchestration.scheduler_engine", "Execution", "P0", "ORCHESTRATION_KERNEL"),
            ("workspace.isolation_guard", "Projects / Workspaces", "P0", "WORKSPACE_MANAGER"),
        ]
        assert len(expected_new_projections) == 40
        for pid, sec, prio, auth in expected_new_projections:
            p = self.registry.get(pid)
            assert p is not None, f"Missing Batch 013 projection: {pid}"
            assert p.section == sec, f"{pid} section mismatch: {p.section} != {sec}"
            assert p.priority == prio, f"{pid} priority mismatch: {p.priority} != {prio}"
            assert p.source_authority == auth, f"{pid} authority mismatch: {p.source_authority} != {auth}"
            assert p.implementation_status == "PLANNED", f"{pid} should be PLANNED"

    # ---- Duplicate checks ----

    def test_zero_duplicate_projection_ids(self):
        ids = [item.projection_id for item in self.items]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {len(ids) - len(set(ids))}"

    def test_batch013_sort_order_range(self):
        sort_orders = [item.sort_order for item in self.items]
        assert min(sort_orders) == 0
        assert max(sort_orders) >= 747

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


class TestBatch013Regression:
    """Verify prior batch contracts are preserved."""

    def test_prior_batch_count_floors(self):
        from runtime.admin.projections import default_projection_registry
        reg = default_projection_registry()
        summary = reg.summary()
        assert summary["total_definitions"] >= 434
        assert summary["by_priority"]["P0"] >= 145
        assert summary["by_implementation_status"]["BOUND"] >= 78
