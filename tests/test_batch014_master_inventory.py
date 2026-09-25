"""Batch 014: Master Inventory Expansion & Operational Grounding.

Test contract for the projection registry after Batch 014 additions.
Validates:
  - Total inventory count (479)
  - Batch 014 delta (+45 from 434)
  - P0 count expansion (188, up from 145 via evidence-backed operational grounding)
  - 45 new grounded operational depth definitions across subsystems:
    * Identity & Attestation (identity.enrollment_audit, identity.key_rotation)
    * Fabric & Mesh (fabric.topology_discovery, fabric.cross_repo_mesh)
    * GitHub Integration (github.app_installation, github.webhook_receiver)
    * Core Engine & Recovery (core.crash_recovery_supervisor, core.access_audit_matrix)
    * Execution & Limits (execution.limits_guard, execution.context_packager, execution.worker_health_monitor)
    * Capabilities & Intelligence (capability.tier_routing_engine, intelligence.benchmark_runner_service, intelligence.delegation_arbiter)
    * Accounts & Projects (accounts.credential_linkage, projects.lifecycle_supervisor)
    * Workspace & Quotas (workspace.quota_enforcer, workspace.ephemeral_cleaner)
    * Browser Automation (browser.traffic_interceptor, browser.session_pool_manager)
    * Telemetry & Events (telemetry.redaction_scrubber, telemetry.live_stream_broker, events.dead_letter_queue)
    * Continuity & Journal & Audit (continuity.corruption_detector, continuity.mutation_guard, journal.mission_ledger_service, audit.tamper_evident_seal)
    * Security & Sandbox & Secrets (security.pipeline_orchestrator, security.tool_registry_enforcer, sandbox.restricted_process_backend, secrets.crypto_key_store)
    * Sync & Updates (sync.verification_gate, updater.bundle_extractor)
    * MCP & Tools (mcp.authorization_gate, tools.capability_sandbox)
    * Diagnostics & Bootstrap (diagnostics.system_triage, bootstrap.gate_evaluator)
    * Filesystem & Git & Process & Shell (filesystem.path_sanitizer, git.repo_integrity_checker, process.signal_dispatcher, shell.command_sanitizer)
    * Compute & Orchestration & Platform (compute.remote_session_pool, orchestration.frontier_scheduler, platform.wsl2_bridge, platform.linux_kernel_monitor)
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


class TestBatch014MasterInventory:
    """Projection registry contract after Batch 014."""

    def setup_method(self):
        from runtime.admin.projections import default_projection_registry
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # ---- Inventory counts ----

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= 479

    def test_batch_014_delta(self):
        """Batch 014 added 45 items (sort_order 748..792)."""
        batch_014_items = [p for p in self.items if 748 <= p.sort_order <= 792]
        assert len(batch_014_items) == 45

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # ---- Priority distribution ----

    def test_p0_count(self):
        """P0 advanced from 145 to 188 via operational depth additions."""
        assert self.summary["by_priority"]["P0"] >= 188

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] == 206

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] == 85

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == 0

    # ---- Implementation status distribution ----

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] == 78

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] == 9

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] >= 389

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == 3

    # ---- Batch 014 New definitions audit ----

    def test_batch014_new_definitions_exist(self):
        expected_new_projections = [
            ("identity.enrollment_audit", "Runtime Identity", "P0", "ENROLLMENT_MANAGER"),
            ("identity.key_rotation", "Runtime Identity", "P0", "RUNTIME_IDENTITY"),
            ("fabric.topology_discovery", "Repository Fabric", "P0", "FABRIC_LIVE_TRUTH"),
            ("fabric.cross_repo_mesh", "Repository Fabric", "P0", "FABRIC_LIVE_TRUTH"),
            ("github.app_installation", "GitHub", "P0", "GITHUB_AUTH"),
            ("github.webhook_receiver", "GitHub", "P1", "GITHUB_AUTH"),
            ("core.crash_recovery_supervisor", "Runtime Identity", "P0", "RECOVERY_MANAGER"),
            ("core.access_audit_matrix", "Runtime Identity", "P0", "ACCESS_VERIFIER"),
            ("execution.limits_guard", "Execution", "P0", "RUNTIME_EXECUTION"),
            ("execution.context_packager", "Execution", "P0", "RUNTIME_EXECUTION"),
            ("execution.worker_health_monitor", "Execution", "P0", "RUNTIME_EXECUTION"),
            ("capability.tier_routing_engine", "Intelligence", "P0", "CAPABILITY_GATE"),
            ("intelligence.benchmark_runner_service", "Intelligence", "P0", "BENCHMARK_RUNNER"),
            ("intelligence.delegation_arbiter", "Intelligence", "P0", "DELEGATION_ARBITER"),
            ("accounts.credential_linkage", "Accounts / Identities", "P0", "ACCOUNT_REGISTRY"),
            ("projects.lifecycle_supervisor", "Projects / Workspaces", "P0", "PROJECT_REGISTRY"),
            ("workspace.quota_enforcer", "Projects / Workspaces", "P0", "WORKSPACE_MANAGER"),
            ("workspace.ephemeral_cleaner", "Projects / Workspaces", "P0", "WORKSPACE_MANAGER"),
            ("browser.traffic_interceptor", "Browser", "P0", "BROWSER_INTERCEPTOR"),
            ("browser.session_pool_manager", "Browser", "P0", "BROWSER_MANAGER"),
            ("telemetry.redaction_scrubber", "Telemetry", "P0", "TELEMETRY_SCRUBBER"),
            ("telemetry.live_stream_broker", "Telemetry", "P0", "TELEMETRY_STREAM"),
            ("events.dead_letter_queue", "Telemetry", "P0", "EVENT_BUS"),
            ("continuity.corruption_detector", "Continuity", "P0", "CONTINUITY_ENGINE"),
            ("continuity.mutation_guard", "Continuity", "P0", "CONTINUITY_MUTATION"),
            ("journal.mission_ledger_service", "Project State", "P0", "MISSION_JOURNAL"),
            ("audit.tamper_evident_seal", "Evidence / Provenance", "P0", "AUDIT_STORE"),
            ("security.pipeline_orchestrator", "Security / Trust", "P0", "AUTHORIZED_PIPELINE"),
            ("security.tool_registry_enforcer", "Security / Trust", "P0", "SECURE_TOOLS"),
            ("sandbox.restricted_process_backend", "Execution", "P0", "SANDBOX_MANAGER"),
            ("secrets.crypto_key_store", "Security / Trust", "P0", "SECRET_BACKEND"),
            ("sync.verification_gate", "Distribution / Updates", "P0", "SYNC_VERIFIER"),
            ("updater.bundle_extractor", "Distribution / Updates", "P0", "UPDATE_MANAGER"),
            ("mcp.authorization_gate", "Infrastructure", "P0", "MCP_GATEWAY"),
            ("tools.capability_sandbox", "Infrastructure", "P0", "TOOL_REGISTRY"),
            ("diagnostics.system_triage", "Security / Trust", "P0", "RUNTIME_DOCTOR"),
            ("bootstrap.gate_evaluator", "CONRRAD", "P0", "BOOTSTRAP_ENGINE"),
            ("filesystem.path_sanitizer", "Infrastructure", "P0", "FILESYSTEM_SERVICE"),
            ("git.repo_integrity_checker", "Infrastructure", "P0", "GIT_SERVICE"),
            ("process.signal_dispatcher", "Execution", "P0", "PROCESS_MANAGER"),
            ("shell.command_sanitizer", "Execution", "P0", "SHELL_EXECUTOR"),
            ("compute.remote_session_pool", "Infrastructure", "P0", "COMPUTE_MANAGER"),
            ("orchestration.frontier_scheduler", "Execution", "P0", "ORCHESTRATION_KERNEL"),
            ("platform.wsl2_bridge", "Infrastructure", "P1", "PLATFORM_ADAPTER"),
            ("platform.linux_kernel_monitor", "Infrastructure", "P0", "PLATFORM_ADAPTER"),
        ]
        assert len(expected_new_projections) == 45
        for pid, sec, prio, auth in expected_new_projections:
            p = self.registry.get(pid)
            assert p is not None, f"Missing Batch 014 projection: {pid}"
            assert p.section == sec, f"{pid} section mismatch: {p.section} != {sec}"
            assert p.priority == prio, f"{pid} priority mismatch: {p.priority} != {prio}"
            assert p.source_authority == auth, f"{pid} authority mismatch: {p.source_authority} != {auth}"
            assert p.implementation_status == "PLANNED", f"{pid} should be PLANNED"

    # ---- Duplicate checks ----

    def test_zero_duplicate_projection_ids(self):
        ids = [item.projection_id for item in self.items]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {len(ids) - len(set(ids))}"

    def test_batch014_sort_order_range(self):
        sort_orders = [item.sort_order for item in self.items]
        assert min(sort_orders) == 0
        assert max(sort_orders) >= 792

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


class TestBatch014Regression:
    """Verify prior batch contracts are preserved."""

    def test_prior_batch_count_floors(self):
        from runtime.admin.projections import default_projection_registry
        reg = default_projection_registry()
        summary = reg.summary()
        assert summary["total_definitions"] >= 479
        assert summary["by_priority"]["P0"] >= 188
        assert summary["by_implementation_status"]["BOUND"] >= 78
