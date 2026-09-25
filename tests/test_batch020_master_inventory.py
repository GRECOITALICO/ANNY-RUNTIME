"""Batch 020: ANNY-native Harness/IDE/catalog P0 tranche is registry-derived."""

from runtime.admin.projections import (
    DEFAULT_NAVIGATION_ITEMS,
    DEFAULT_PROJECTION_REGISTRY,
    INITIAL_P0_VIEWPORT_TARGET,
    MASTER_INVENTORY_BOUNDARY,
    audit_navigation_contract,
    default_projection_registry,
)
from runtime.admin.routes import AdminRouter


BATCH_016_TOTAL = 559
BATCH_020_DELTA = 40
BATCH_020_TOTAL = BATCH_016_TOTAL + BATCH_020_DELTA  # 599
BATCH_020_P0 = 308
BATCH_020_P1 = 206
BATCH_020_P2 = 85
BATCH_020_P3 = 0
BATCH_020_BOUND = 78
BATCH_020_PARTIAL = 9
BATCH_020_BLOCKED = 3
BATCH_020_PLANNED = 509

BATCH_020_EXPECTED = [
    ("runtime.anny_native_operating_plane", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
    ("runtime.execution_admission", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
    ("runtime.local_first_execution_boundary", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
    ("runtime.provider_neutrality_surface", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
    ("runtime.certification_chain_projection", "Runtime Identity", "P0", "RUNTIME_ENGINE"),
    ("runtime.truth_class_operator_legend", "Control Center", "P0", "PROJECTION_REGISTRY"),
    ("harness.operating_surface", "Harness", "P0", "HARNESS_REGISTRY"),
    ("harness.session_state", "Harness", "P0", "HARNESS_REGISTRY"),
    ("harness.capability_dispatch", "Harness", "P0", "HARNESS_REGISTRY"),
    ("harness.worker_handoff", "Harness", "P0", "HARNESS_REGISTRY"),
    ("harness.evidence_capture", "Harness", "P0", "HARNESS_REGISTRY"),
    ("harness.external_agent_nondependency", "Harness", "P0", "HARNESS_REGISTRY"),
    ("ide.operating_surface", "ANNY IDE", "P0", "IDE_REGISTRY"),
    ("ide.workspace_projection", "ANNY IDE", "P0", "IDE_REGISTRY"),
    ("ide.artifact_inspector", "ANNY IDE", "P0", "IDE_REGISTRY"),
    ("ide.execution_trace", "ANNY IDE", "P0", "IDE_REGISTRY"),
    ("ide.local_edit_boundary", "ANNY IDE", "P0", "IDE_REGISTRY"),
    ("ide.runtime_attached_session", "ANNY IDE", "P0", "IDE_REGISTRY"),
    ("catalog.universal_index", "Universal Capability Catalog", "P0", "CAPABILITY_CATALOG"),
    ("catalog.capability_discovery", "Universal Capability Catalog", "P0", "CAPABILITY_CATALOG"),
    ("catalog.capability_routing", "Universal Capability Catalog", "P0", "CAPABILITY_CATALOG"),
    ("catalog.capability_orchestration", "Universal Capability Catalog", "P0", "CAPABILITY_CATALOG"),
    ("catalog.capability_binding", "Universal Capability Catalog", "P0", "CAPABILITY_CATALOG"),
    ("catalog.external_construction_tool_exclusion", "Universal Capability Catalog", "P0", "CAPABILITY_CATALOG"),
    ("execution.deterministic_module_registry", "Execution", "P0", "RUNTIME_EXECUTION"),
    ("execution.deterministic_replay", "Execution", "P0", "RUNTIME_EXECUTION"),
    ("execution.runtime_context_surface", "Execution", "P0", "RUNTIME_EXECUTION"),
    ("intelligence.local_model_integration", "Intelligence", "P0", "RUNTIME_MODEL_REGISTRY"),
    ("intelligence.local_model_admission", "Intelligence", "P0", "RUNTIME_MODEL_REGISTRY"),
    ("intelligence.local_inference_boundary", "Intelligence", "P0", "RUNTIME_MODEL_REGISTRY"),
    ("execution.worker_delegation_board", "Execution", "P0", "WORKER_REGISTRY"),
    ("execution.delegated_worker_receipt", "Execution", "P0", "WORKER_REGISTRY"),
    ("execution.worker_authorization_boundary", "Execution", "P0", "WORKER_REGISTRY"),
    ("execution.anny_native_worker_path", "Execution", "P0", "WORKER_REGISTRY"),
    ("evidence.certification_chain_index", "Evidence / Provenance", "P0", "EVIDENCE_REGISTRY"),
    ("audit.operator_action_trail", "Evidence / Provenance", "P0", "AUDIT_STORE"),
    ("sync.governed_promotion_board", "Distribution / Updates", "P0", "SYNC_SERVICE"),
    ("control.harness_state_panel", "Control Center", "P0", "HARNESS_REGISTRY"),
    ("control.ide_state_panel", "Control Center", "P0", "IDE_REGISTRY"),
    ("control.catalog_state_panel", "Control Center", "P0", "CAPABILITY_CATALOG"),
]


class TestBatch020MasterInventory:
    def setup_method(self):
        self.registry = default_projection_registry()
        self.summary = self.registry.summary()
        self.items = self.registry.list()

    def test_total_projection_count(self):
        assert self.summary["total_definitions"] == BATCH_020_TOTAL

    def test_batch_020_delta_sort_order_range(self):
        batch_020_items = [p for p in self.items if 873 <= p.sort_order <= 912]
        assert len(batch_020_items) == BATCH_020_DELTA

    def test_open_ended_boundary_and_viewport_target(self):
        assert self.summary["master_inventory_boundary"] == MASTER_INVENTORY_BOUNDARY
        assert self.summary["inventory_limit"] is None
        assert self.summary["initial_p0_viewport_target"] == INITIAL_P0_VIEWPORT_TARGET == 349

    def test_priority_counts(self):
        assert self.summary["by_priority"]["P0"] == BATCH_020_P0
        assert self.summary["by_priority"]["P1"] == BATCH_020_P1
        assert self.summary["by_priority"]["P2"] == BATCH_020_P2
        assert self.summary["by_priority"]["P3"] == BATCH_020_P3

    def test_implementation_status_counts(self):
        assert self.summary["by_implementation_status"]["BOUND"] == BATCH_020_BOUND
        assert self.summary["by_implementation_status"]["PARTIAL"] == BATCH_020_PARTIAL
        assert self.summary["by_implementation_status"]["BLOCKED"] == BATCH_020_BLOCKED
        assert self.summary["by_implementation_status"]["PLANNED"] == BATCH_020_PLANNED

    def test_batch020_new_definitions_are_planned_unknown_and_not_bound(self):
        assert len(BATCH_020_EXPECTED) == BATCH_020_DELTA
        for pid, section, priority, authority in BATCH_020_EXPECTED:
            defn = self.registry.get(pid)
            assert defn is not None, f"Missing projection: {pid}"
            assert defn.section == section
            assert defn.priority == priority
            assert defn.source_authority == authority
            assert defn.implementation_status == "PLANNED"
            assert defn.current_status == "UNKNOWN"
            assert defn.truth_class == "UNKNOWN"
            assert defn.freshness == "NOT_BOUND"

    def test_zero_duplicate_projection_ids(self):
        ids = [item.projection_id for item in self.items]
        assert len(ids) == len(set(ids))

    def test_definitions_do_not_claim_live_or_certified_state(self):
        for pid, *_ in BATCH_020_EXPECTED:
            defn = self.registry.get(pid)
            assert defn.current_status not in {"ONLINE", "LIVE", "CERTIFIED"}
            assert defn.implementation_status != "BOUND"

    def test_navigation_contract_remains_valid_with_planned_anny_native_destinations(self):
        assert len(DEFAULT_NAVIGATION_ITEMS) >= 37
        planned_paths = {item.path for item in DEFAULT_NAVIGATION_ITEMS if item.availability == "PLANNED"}
        assert "/harness" in planned_paths
        assert "/ide" in planned_paths
        assert "/intelligence/catalog" in planned_paths
        assert "/execution/context" in planned_paths
        audit = audit_navigation_contract(
            DEFAULT_NAVIGATION_ITEMS,
            AdminRouter({})._get_routes,
        )
        assert audit["status"] == "VALID"
        assert audit["registered_projection_ids"] == {"valid": 18, "total": 18}
        assert audit["active_or_alias_destinations"] == 18
        assert audit["planned_destinations"] >= 19
        assert audit["dead_links"] == []
        assert audit["stale_aliases"] == []
        assert audit["duplicate_destinations"] == []
        assert audit["false_online_declarations"] == []

    def test_registry_validates(self):
        self.registry.validate()
        assert DEFAULT_PROJECTION_REGISTRY.summary()["total_definitions"] == BATCH_020_TOTAL
