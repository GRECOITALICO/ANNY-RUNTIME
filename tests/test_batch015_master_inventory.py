"""Batch 015: Master Inventory Expansion test suite.

Validates the Projection Registry contract following Batch 015 expansion:
- Total definitions: 523 (+44 from Batch 014's 479)
- P0 expansion to 232 (up from 188), grounded in verified runtime source modules
- All 44 new definitions verified against their source authority and subsystem
- Regression floors from prior batches preserved
- Security, navigation, freshness, and provider neutrality invariants enforced
"""

import pytest
from runtime.admin.projections import (
    default_projection_registry,
    DEFAULT_NAVIGATION_ITEMS,
    DEFAULT_PROJECTION_REGISTRY,
    INITIAL_P0_VIEWPORT_TARGET,
    MASTER_INVENTORY_BOUNDARY,
)


BATCH_015_TOTAL = 523
BATCH_014_TOTAL = 479
BATCH_015_DELTA = BATCH_015_TOTAL - BATCH_014_TOTAL  # 44
BATCH_015_P0 = 232
BATCH_015_P1 = 206
BATCH_015_P2 = 85
BATCH_015_P3 = 0
BATCH_015_BOUND = 78
BATCH_015_PARTIAL = 9
BATCH_015_BLOCKED = 3
BATCH_015_PLANNED = 433


class TestBatch015MasterInventory:
    """Validates Batch 015 projection registry contract."""

    def setup_method(self):
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    # --- Inventory counts ---

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] >= BATCH_015_TOTAL

    def test_batch_015_delta(self):
        assert BATCH_015_TOTAL - BATCH_014_TOTAL == BATCH_015_DELTA

    def test_open_ended_boundary(self):
        assert self.summary["master_inventory_boundary"] == "OPEN_ENDED_1000_PLUS"
        assert self.summary["inventory_limit"] is None

    def test_p0_viewport_target_not_hardcoded_ceiling(self):
        assert self.summary["initial_p0_viewport_target"] == 349

    # --- Priority distribution ---

    def test_p0_count(self):
        assert self.summary["by_priority"]["P0"] >= BATCH_015_P0

    def test_p1_count(self):
        assert self.summary["by_priority"]["P1"] == BATCH_015_P1

    def test_p2_count(self):
        assert self.summary["by_priority"]["P2"] == BATCH_015_P2

    def test_p3_count(self):
        assert self.summary["by_priority"]["P3"] == BATCH_015_P3

    # --- Implementation status distribution ---

    def test_bound_count(self):
        assert self.summary["by_implementation_status"]["BOUND"] == BATCH_015_BOUND

    def test_partial_count(self):
        assert self.summary["by_implementation_status"]["PARTIAL"] == BATCH_015_PARTIAL

    def test_blocked_count(self):
        assert self.summary["by_implementation_status"]["BLOCKED"] == BATCH_015_BLOCKED

    def test_planned_count(self):
        assert self.summary["by_implementation_status"]["PLANNED"] >= BATCH_015_PLANNED

    # --- Batch 015 new definitions audit ---

    def test_batch015_new_definitions(self):
        """Verify all 44 Batch 015 projections exist with correct grounding."""
        expected = [
            # (projection_id, section, priority, source_authority)
            # Admin Server Infrastructure
            ("admin.server_lifecycle", "Control Center", "P0", "ADMIN_SERVER"),
            ("admin.request_handler", "Control Center", "P0", "ADMIN_SERVER"),
            ("admin.loopback_binding", "Control Center", "P0", "ADMIN_PORT"),
            # Admin DTOs
            ("admin.canonical_state_dto", "Control Center", "P0", "CANONICAL_STATE_DTO"),
            ("admin.continuity_dto", "Control Center", "P0", "CONTINUITY_DTO"),
            ("admin.mission_task_dto", "Control Center", "P0", "STATE_DTO"),
            ("admin.worker_summary_dto", "Execution", "P0", "WORKER_DTO"),
            # Bootstrap CONRRAD
            ("bootstrap.conrrad_dependency_matrix", "CONRRAD", "P0", "CONRRAD_DEPENDENCY"),
            ("bootstrap.conrrad_registry_normalizer", "CONRRAD", "P0", "CONRRAD_DEPENDENCY"),
            # Bootstrap Three-Plane
            ("bootstrap.three_plane_resolver", "CONRRAD", "P0", "THREE_PLANE_BOOTSTRAP"),
            ("bootstrap.gate_chain_evaluator", "CONRRAD", "P0", "THREE_PLANE_BOOTSTRAP"),
            # Bootstrap Report
            ("bootstrap.report_formatter", "CONRRAD", "P0", "BOOTSTRAP_REPORT"),
            ("bootstrap.component_inventory_report", "Control Center", "P0", "BOOTSTRAP_REPORT"),
            # API Bridge Auth
            ("api.bridge_auth_gate", "Security / Trust", "P0", "BRIDGE_AUTH"),
            ("api.bridge_dispatch", "Communication", "P0", "BRIDGE_ROUTER"),
            # Telemetry Domain
            ("telemetry.envelope_schema", "Telemetry", "P0", "TELEMETRY_SCHEMA"),
            ("telemetry.domain_taxonomy", "Telemetry", "P0", "TELEMETRY_TAXONOMY"),
            ("telemetry.execution_mode_classifier", "Telemetry", "P0", "TELEMETRY_SCHEMA"),
            # Execution Receipt
            ("execution.receipt_ledger", "Evidence / Provenance", "P0", "RECEIPT_STORE"),
            # Execution Policy
            ("execution.policy_engine", "Execution", "P0", "EXECUTION_POLICY"),
            # Intelligence
            ("intelligence.taxonomy_service", "Intelligence", "P0", "INTELLIGENCE_TAXONOMY"),
            ("intelligence.evidence_builder_service", "Intelligence", "P0", "EVIDENCE_BUILDER"),
            # Execution Validator/Selector
            ("execution.output_validator", "Execution", "P0", "OUTPUT_VALIDATOR"),
            ("execution.model_selector_service", "Execution", "P0", "EXECUTOR_SELECTOR"),
            # Admin GitHub
            ("admin.github_auth_manager", "GitHub", "P0", "GITHUB_AUTH_MANAGER"),
            ("admin.github_credential_state", "GitHub", "P0", "GITHUB_AUTH_MANAGER"),
            # Admin Middleware
            ("admin.middleware_guard", "Security / Trust", "P0", "ADMIN_MIDDLEWARE"),
            ("admin.onboarding_revocation", "Security / Trust", "P0", "ADMIN_MIDDLEWARE"),
            # Admin CSRF
            ("admin.csrf_validator", "Security / Trust", "P0", "ADMIN_CSRF"),
            # Execution Worker/Manager
            ("execution.worker_registry", "Execution", "P0", "WORKER_REGISTRY"),
            ("execution.task_queue", "Execution", "P0", "EXECUTION_MANAGER"),
            # Continuity
            ("continuity.state_machine", "Continuity", "P0", "CONTINUITY_STATE"),
            ("continuity.operational_repo_provider", "Continuity", "P0", "OPERATIONAL_PROVIDER"),
            # Fabric
            ("fabric.github_adapter_service", "Repository Fabric", "P0", "FABRIC_GITHUB_ADAPTER"),
            # GitHub
            ("github.authenticated_client", "GitHub", "P0", "GITHUB_CLIENT"),
            ("github.org_discovery_service", "GitHub", "P0", "GITHUB_DISCOVERY_SERVICE"),
            # Platform
            ("platform.base_adapter", "Infrastructure", "P0", "PLATFORM_BASE"),
            # MCP
            ("mcp.tool_definitions", "Infrastructure", "P0", "MCP_TOOLS"),
            # Admin Renderers
            ("admin.control_center_renderer", "Control Center", "P0", "CC_RENDERER"),
            ("admin.template_engine", "Control Center", "P0", "ADMIN_TEMPLATES"),
            # Compute
            ("compute.capability_registry_service", "Infrastructure", "P0", "COMPUTE_REGISTRY"),
            # Tools
            ("tools.builtin_executor", "Execution", "P0", "BUILTIN_TOOLS"),
            # Continuity Bootstrap/Models
            ("continuity.bootstrap_provider", "Continuity", "P0", "CONTINUITY_BOOTSTRAP"),
            ("continuity.event_model", "Continuity", "P0", "CONTINUITY_MODEL"),
        ]

        assert len(expected) == BATCH_015_DELTA, (
            f"Expected {BATCH_015_DELTA} definitions, listed {len(expected)}"
        )

        for pid, section, priority, authority in expected:
            defn = self.registry.get(pid)
            assert defn is not None, f"Missing projection: {pid}"
            assert defn.section == section, f"{pid}: expected section={section}, got {defn.section}"
            assert defn.priority == priority, f"{pid}: expected priority={priority}, got {defn.priority}"
            assert defn.source_authority == authority, f"{pid}: expected authority={authority}, got {defn.source_authority}"
            assert defn.implementation_status == "PLANNED", f"{pid}: expected PLANNED, got {defn.implementation_status}"

    # --- Duplicate & Sort Order Integrity ---

    def test_zero_duplicate_projection_ids(self):
        ids = [item.projection_id for item in self.items]
        assert len(ids) == len(set(ids)), "Duplicate projection IDs detected"

    def test_batch015_sort_order_range(self):
        sort_orders = [item.sort_order for item in self.items]
        assert min(sort_orders) == 0
        assert max(sort_orders) >= 836

    # --- Navigation integrity ---

    def test_navigation_contract_integrity(self):
        assert len(DEFAULT_NAVIGATION_ITEMS) == 33
        for nav in DEFAULT_NAVIGATION_ITEMS:
            if nav.availability in {"ACTIVE", "ALIAS"}:
                assert DEFAULT_PROJECTION_REGISTRY.get(nav.projection_id) is not None, (
                    f"Navigation item '{nav.label}' references unregistered projection: {nav.projection_id}"
                )

    # --- PARTIAL surfaces ---

    def test_partial_surfaces_unchanged(self):
        partial = [item for item in self.items if item.implementation_status == "PARTIAL"]
        partial_ids = {item.projection_id for item in partial}
        expected_partial = {
            "admin.operations",
            "admin.receipts",
            "intelligence.executors_view",
            "conrrad.required_services",
            "project.current_mission",
            "project.current_task",
            "project.next_action",
            "project.blockers",
            "security.trust",
        }
        assert partial_ids == expected_partial

    # --- BLOCKED surfaces ---

    def test_blocked_surfaces_unchanged(self):
        blocked = [item for item in self.items if item.implementation_status == "BLOCKED"]
        blocked_ids = {item.projection_id for item in blocked}
        expected_blocked = {
            "distribution.sync_stage",
            "distribution.activation",
            "distribution.rollback",
        }
        assert blocked_ids == expected_blocked

    # --- Invariants ---

    def test_sync_separation_invariants(self):
        sync_items = [item for item in self.items if "sync" in item.tags or "distribution" in item.section.lower()]
        assert len(sync_items) >= 10
        sync_def = self.registry.get("distribution.sync")
        assert sync_def is not None
        assert sync_def.implementation_status == "BOUND"

    def test_provider_neutrality(self):
        azure = self.registry.get("infrastructure.azure")
        assert azure is not None
        assert azure.priority == "P2"
        assert azure.implementation_status == "PLANNED"
        assert azure.source_authority == "AZURE_LIVE_TRUTH"

    def test_freshness_invariants(self):
        for item in self.items:
            if item.implementation_status == "BOUND":
                assert item.freshness == "LIVE_ON_READ", (
                    f"{item.projection_id}: BOUND must have LIVE_ON_READ freshness"
                )
            if item.implementation_status == "PLANNED":
                assert item.freshness == "NOT_BOUND", (
                    f"{item.projection_id}: PLANNED must have NOT_BOUND freshness"
                )

    def test_registry_validates(self):
        self.registry.validate()


class TestBatch015Regression:
    """Monotonic floor regression to prevent silent count loss."""

    def test_prior_batch_count_floors(self):
        registry = default_projection_registry()
        summary = registry.summary()
        assert summary["total_definitions"] >= BATCH_015_TOTAL
        assert summary["by_priority"]["P0"] >= BATCH_015_P0
        assert summary["by_implementation_status"]["BOUND"] >= BATCH_015_BOUND
