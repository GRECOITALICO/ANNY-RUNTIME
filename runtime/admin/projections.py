"""Canonical Control Center projection registry.

This module defines the durable UI projection contract independently from the HTML
renderer. It is intentionally read-only at this stage: it describes what ANNY can
project and where the truth is expected to come from; it never mutates runtime state.

The registry is open-ended. The initial P0 viewport target of 349 is a prominence
target, not an inventory limit. New projections are expected to be added without
removing lower-priority definitions from the master registry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


REGISTRY_CONTRACT_VERSION = "1.0"
MASTER_INVENTORY_BOUNDARY = "OPEN_ENDED_1000_PLUS"
INITIAL_P0_VIEWPORT_TARGET = 349

VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
VALID_TRUTH_CLASSES = frozenset(
    {"FACT", "HYPOTHESIS", "UNKNOWN", "UNVERIFIED"}
)
VALID_VISIBILITY = frozenset({"VISIBLE", "CONDITIONAL", "HIDDEN"})
VALID_IMPLEMENTATION_STATES = frozenset(
    {"BOUND", "PARTIAL", "PLANNED", "BLOCKED", "NOT_IMPLEMENTED"}
)


@dataclass(frozen=True)
class ProjectionDefinition:
    """Static contract for one Control Center projection."""

    projection_id: str
    title: str
    section: str
    priority: str
    current_status: str
    truth_class: str
    source_authority: str
    freshness: str
    evidence_ref: Optional[str] = None
    failure_reason: Optional[str] = None
    dependencies: Tuple[str, ...] = field(default_factory=tuple)
    visibility_policy: str = "VISIBLE"
    route_or_detail: Optional[str] = None
    renderer: str = "control_center"
    sort_order: int = 0
    tags: Tuple[str, ...] = field(default_factory=tuple)
    implementation_status: str = "PLANNED"

    def __post_init__(self) -> None:
        if not self.projection_id or " " in self.projection_id:
            raise ValueError("projection_id must be a non-empty identifier")
        if self.priority not in VALID_PRIORITIES:
            raise ValueError(f"Unsupported priority: {self.priority}")
        if self.truth_class not in VALID_TRUTH_CLASSES:
            raise ValueError(f"Unsupported truth_class: {self.truth_class}")
        if self.visibility_policy not in VALID_VISIBILITY:
            raise ValueError(f"Unsupported visibility_policy: {self.visibility_policy}")
        if self.implementation_status not in VALID_IMPLEMENTATION_STATES:
            raise ValueError(
                f"Unsupported implementation_status: {self.implementation_status}"
            )
        if self.sort_order < 0:
            raise ValueError("sort_order must be >= 0")

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["dependencies"] = list(self.dependencies)
        data["tags"] = list(self.tags)
        return data


class ProjectionRegistry:
    """In-memory canonical registry for immutable projection definitions."""

    def __init__(self, definitions: Iterable[ProjectionDefinition] = ()) -> None:
        self._items: Dict[str, ProjectionDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ProjectionDefinition) -> None:
        """Register exactly one projection ID; duplicates are rejected."""
        if definition.projection_id in self._items:
            raise ValueError(f"Duplicate projection_id: {definition.projection_id}")
        self._items[definition.projection_id] = definition

    def get(self, projection_id: str) -> Optional[ProjectionDefinition]:
        return self._items.get(projection_id)

    def list(
        self,
        *,
        priority: Optional[str] = None,
        section: Optional[str] = None,
        implementation_status: Optional[str] = None,
        truth_class: Optional[str] = None,
        freshness: Optional[str] = None,
        tag: Optional[str] = None,
        q: Optional[str] = None,
        projection_id: Optional[str] = None,
    ) -> List[ProjectionDefinition]:
        items = list(self._items.values())
        if projection_id:
            items = [item for item in items if item.projection_id == projection_id]
        if priority:
            items = [item for item in items if item.priority == priority]
        if section:
            items = [item for item in items if item.section == section]
        if implementation_status:
            items = [
                item
                for item in items
                if item.implementation_status == implementation_status
            ]
        if truth_class:
            items = [item for item in items if item.truth_class == truth_class]
        if freshness:
            items = [item for item in items if item.freshness == freshness]
        if tag:
            normalized_tag = tag.strip().lower()
            items = [
                item for item in items
                if normalized_tag in {value.lower() for value in item.tags}
            ]
        if q:
            needle = q.strip().lower()
            if needle:
                items = [
                    item for item in items
                    if needle in item.projection_id.lower()
                    or needle in item.title.lower()
                    or needle in item.section.lower()
                    or needle in item.source_authority.lower()
                    or any(needle in value.lower() for value in item.tags)
                ]
        return sorted(items, key=lambda item: (item.sort_order, item.projection_id))

    def validate(self) -> None:
        """Validate registry-level invariants."""
        ids = [item.projection_id for item in self._items.values()]
        if len(ids) != len(set(ids)):
            raise AssertionError("Projection registry contains duplicate IDs")
        for item in self._items.values():
            item.__post_init__()

    def summary(self) -> Dict[str, object]:
        self.validate()
        items = list(self._items.values())
        by_priority = {p: sum(i.priority == p for i in items) for p in VALID_PRIORITIES}
        by_status = {
            state: sum(i.implementation_status == state for i in items)
            for state in VALID_IMPLEMENTATION_STATES
        }
        by_section: Dict[str, int] = {}
        by_freshness: Dict[str, int] = {}
        for item in items:
            by_section[item.section] = by_section.get(item.section, 0) + 1
            by_freshness[item.freshness] = by_freshness.get(item.freshness, 0) + 1
        return {
            "total_definitions": len(items),
            "by_priority": by_priority,
            "by_implementation_status": by_status,
            "by_section": dict(sorted(by_section.items())),
            "by_freshness": dict(sorted(by_freshness.items())),
            "initial_p0_viewport_target": INITIAL_P0_VIEWPORT_TARGET,
            "master_inventory_boundary": MASTER_INVENTORY_BOUNDARY,
            "inventory_limit": None,
        }

    def to_api_dict(
        self,
        *,
        priority: Optional[str] = None,
        section: Optional[str] = None,
        implementation_status: Optional[str] = None,
        truth_class: Optional[str] = None,
        freshness: Optional[str] = None,
        tag: Optional[str] = None,
        q: Optional[str] = None,
        projection_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Dict[str, object]:
        if limit is not None and (limit < 1 or limit > 200):
            raise ValueError("limit must be between 1 and 200")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        items = self.list(
            priority=priority,
            section=section,
            implementation_status=implementation_status,
            truth_class=truth_class,
            freshness=freshness,
            tag=tag,
            q=q,
            projection_id=projection_id,
        )
        total_filtered = len(items)
        if limit is None:
            page = items[offset:]
            has_more = False
        else:
            page = items[offset:offset + limit]
            has_more = offset + len(page) < total_filtered
        return {
            "contract_version": REGISTRY_CONTRACT_VERSION,
            "master_inventory_boundary": MASTER_INVENTORY_BOUNDARY,
            "inventory_limit": None,
            "initial_p0_viewport_target": INITIAL_P0_VIEWPORT_TARGET,
            "summary": self.summary(),
            "page": {
                "limit": limit if limit is not None else total_filtered,
                "offset": offset,
                "returned": len(page),
                "total_filtered": total_filtered,
                "has_more": has_more,
            },
            "filters": {
                "priority": priority,
                "section": section,
                "implementation_status": implementation_status,
                "truth_class": truth_class,
                "freshness": freshness,
                "tag": tag,
                "q": q,
                "projection_id": projection_id,
            },
            "projections": [item.to_dict() for item in page],
        }


def _p(
    projection_id: str,
    title: str,
    section: str,
    *,
    priority: str = "P0",
    source_authority: str = "RUNTIME",
    route_or_detail: Optional[str] = None,
    implementation_status: str = "BOUND",
    truth_class: str = "UNKNOWN",
    freshness: Optional[str] = None,
    evidence_ref: Optional[str] = None,
    failure_reason: Optional[str] = None,
    dependencies: Sequence[str] = (),
    visibility_policy: str = "VISIBLE",
    renderer: str = "control_center",
    sort_order: int = 0,
    tags: Sequence[str] = (),
) -> ProjectionDefinition:
    resolved_freshness = freshness or (
        "LIVE_ON_READ" if implementation_status == "BOUND" else "NOT_BOUND"
    )
    return ProjectionDefinition(
        projection_id=projection_id,
        title=title,
        section=section,
        priority=priority,
        current_status="UNKNOWN",
        truth_class=truth_class,
        source_authority=source_authority,
        freshness=resolved_freshness,
        evidence_ref=evidence_ref,
        failure_reason=failure_reason,
        dependencies=tuple(dependencies),
        visibility_policy=visibility_policy,
        route_or_detail=route_or_detail,
        renderer=renderer,
        sort_order=sort_order,
        tags=tuple(tags),
        implementation_status=implementation_status,
    )


def default_projection_registry() -> ProjectionRegistry:
    """Return the current master registry seed.

    This seed covers the already-observed Control Center and admin surfaces. It is
    deliberately much smaller than the 349-item initial P0 viewport target because
    definitions must be grounded in an existing or explicitly planned projection;
    counts are never invented merely to hit a target.
    """

    items = [
        _p("onboarding.github_connect", "GitHub connection onboarding", "Onboarding", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/", implementation_status="BOUND", sort_order=5, tags=("onboarding", "github")),
        _p("onboarding.device_flow", "GitHub Device Flow", "Onboarding", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/github/device/poll", implementation_status="BOUND", sort_order=6, tags=("onboarding", "device-flow")),
        _p("onboarding.access_token", "GitHub access token fallback", "Onboarding", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/github/token", implementation_status="BOUND", sort_order=7, tags=("onboarding", "fallback")),
        _p("onboarding.ready", "Ready state", "Onboarding", priority="P0", source_authority="RUNTIME", implementation_status="BOUND", route_or_detail="/", sort_order=8, tags=("ready",)),
        _p("onboarding.failure", "Failure state", "Onboarding", priority="P0", source_authority="RUNTIME", implementation_status="BOUND", route_or_detail="/", sort_order=9, tags=("failure",)),
        _p("fabric.setup", "Repository Fabric setup", "Repository Fabric", priority="P0", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/fabric/setup", implementation_status="BOUND", sort_order=72, tags=("fabric", "setup")),
        _p("runtime.reconnect", "Runtime reconnect", "Runtime Identity", priority="P0", source_authority="RUNTIME", implementation_status="BOUND", tags=("reconnect",)),
        _p("admin.operations", "Operations", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/operations", implementation_status="PARTIAL", failure_reason="No canonical Runtime operation registry is exposed to the admin renderer.", sort_order=205, tags=("operations",)),
        _p("admin.receipts", "Receipts", "Evidence / Provenance", priority="P1", source_authority="RECEIPT_STORE", route_or_detail="/receipts", implementation_status="PARTIAL", failure_reason="No canonical Runtime receipt registry is exposed to the admin renderer.", sort_order=185, tags=("receipts",)),
        _p("admin.doctor", "Runtime doctor", "Security / Trust", priority="P0", source_authority="RUNTIME", route_or_detail="/doctor", implementation_status="BOUND", sort_order=325, tags=("doctor", "diagnostics")),
        _p("admin.policies", "Policies", "Security / Trust", priority="P0", source_authority="POLICY_ENGINE", route_or_detail="/policies", implementation_status="BOUND", sort_order=326, tags=("policy",)),
        _p("admin.diagnostics", "Admin diagnostics", "Security / Trust", priority="P0", source_authority="RUNTIME", route_or_detail="/admin/diagnostics", implementation_status="BOUND", sort_order=327, tags=("diagnostics",)),
        _p("admin.update_check", "Admin update check", "Distribution / Updates", priority="P0", source_authority="SYNC_SERVICE", route_or_detail="/admin/update-check", implementation_status="BOUND", sort_order=375, tags=("updates", "check")),
        _p("universe.accounts", "Accounts", "Universe", priority="P0", source_authority="ACCOUNT_REGISTRY", route_or_detail="/universe/accounts", implementation_status="BOUND", sort_order=15, tags=("universe", "accounts")),
        _p("universe.account_detail", "Account detail", "Universe", priority="P0", source_authority="ACCOUNT_REGISTRY", route_or_detail="/universe/accounts/{account_id}", implementation_status="BOUND", tags=("universe", "accounts", "detail")),
        _p("universe.organization", "Organization", "Universe", priority="P0", source_authority="CANONICAL_STATE", route_or_detail="/universe/organization", implementation_status="BOUND", sort_order=20, tags=("universe", "organization")),
        _p("universe.projects", "Projects", "Universe", priority="P0", source_authority="PROJECT_REGISTRY", route_or_detail="/universe/projects", implementation_status="BOUND", sort_order=25, tags=("universe", "projects")),
        _p("universe.repositories", "Repositories", "Universe", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/universe/repositories", implementation_status="BOUND", sort_order=30, tags=("universe", "repositories")),
        _p("universe.resources", "Resources", "Universe", priority="P0", source_authority="RESOURCE_REGISTRY", route_or_detail="/universe/resources", implementation_status="BOUND", sort_order=35, tags=("universe", "resources")),
        _p("execution.missions", "Missions", "Execution", priority="P0", source_authority="CANONICAL_STATE", route_or_detail="/execution/missions", implementation_status="BOUND", sort_order=196, tags=("execution", "missions")),
        _p("execution.execution_runs", "Executions", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/executions", implementation_status="BOUND", sort_order=197, tags=("execution", "runs")),
        _p("execution.workspaces", "Workspaces", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/workspaces", implementation_status="PLANNED", sort_order=198, tags=("execution", "workspace")),
        _p("intelligence.executors_view", "Executors view", "Intelligence", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/executors", implementation_status="PARTIAL", failure_reason="Current executor view remains a static compatibility surface; no canonical executor inventory is exposed.", sort_order=255, tags=("intelligence", "executors")),
        _p("browser.session_detail", "Managed browser session detail", "Browser", priority="P0", source_authority="BROWSER_RUNTIME", route_or_detail="/browser/{session_id}", implementation_status="BOUND", sort_order=365, tags=("browser", "detail")),
        _p("audit.search", "Audit/search discovery", "Evidence / Provenance", priority="P0", source_authority="AUDIT_STORE", route_or_detail="/search", implementation_status="BOUND", sort_order=182, tags=("audit", "search")),
        _p("runtime.identity.state", "ANNY runtime state", "Runtime Identity", sort_order=10, tags=("header", "state")),
        _p("control.top_level_state", "Top-Level State panel", "Control Center", priority="P0", source_authority="RUNTIME", sort_order=1, tags=("panel", "shell")),
        _p("control.operational_snapshot", "Operational Snapshot panel", "Control Center", priority="P0", source_authority="RUNTIME", sort_order=2, tags=("panel",)),
        _p("control.bootstrap_verification", "Bootstrap Verification panel", "Control Center", priority="P0", source_authority="BOOTSTRAP_ENGINE", route_or_detail="/api/bootstrap/verify", sort_order=3, tags=("panel", "gates")),
        _p("control.truth_freshness", "Truth & Freshness panel", "Control Center", priority="P0", source_authority="RUNTIME_OBSERVATION", sort_order=3.5, tags=("panel", "truth", "freshness")),
        _p("control.runtime_health", "Runtime Health panel", "Control Center", priority="P0", source_authority="RUNTIME", sort_order=4, tags=("panel", "health")),
        _p("control.conrrad_mandatory_services", "CONRRAD Mandatory Services live truth", "Control Center", priority="P0", source_authority="CONRRAD_EXTERNAL_REGISTRY", sort_order=4.5, tags=("panel", "conrrad", "live-truth", "mandatory-services")),

        _p("control.repository_fabric", "Repository Fabric panel", "Control Center", priority="P0", source_authority="FABRIC_LIVE_TRUTH", sort_order=5, tags=("panel", "fabric")),
        _p("control.access_verification", "Access Verification panel", "Control Center", priority="P0", source_authority="RUNTIME_AUTH", sort_order=6, tags=("panel", "auth")),
        _p("control.current_contract", "Current Contract panel", "Control Center", priority="P0", source_authority="RUNTIME_CONTRACT", sort_order=7, tags=("panel", "contract")),
        _p("control.capability_inventory", "Capability Inventory panel", "Control Center", priority="P0", source_authority="RUNTIME_CAPABILITY_REGISTRY", sort_order=8, tags=("panel", "capabilities")),
        _p("control.tools", "Tools panel", "Control Center", priority="P0", source_authority="RUNTIME_TOOL_REGISTRY", sort_order=9, tags=("panel", "tools")),
        _p("control.models", "Models panel", "Control Center", priority="P0", source_authority="RUNTIME_MODEL_REGISTRY", sort_order=10, tags=("panel", "models")),
        _p("control.workers", "Workers panel", "Control Center", priority="P0", source_authority="RUNTIME_EXECUTION", sort_order=11, tags=("panel", "workers")),
        _p("control.connectors", "Connectors panel", "Control Center", priority="P0", source_authority="RUNTIME_MCP", sort_order=12, tags=("panel", "connectors")),
        _p("control.processing_matrix", "Processing Matrix panel", "Control Center", priority="P0", source_authority="TELEMETRY_AGGREGATOR", sort_order=13, tags=("panel", "processing")),
        _p("control.continuity", "Continuity panel", "Control Center", priority="P0", source_authority="CANONICAL_STATE", sort_order=14, tags=("panel", "continuity")),
        _p("runtime.health", "Runtime health", "Runtime Identity", route_or_detail="/health/live", sort_order=20, tags=("health",)),
        _p("runtime.version", "Runtime version", "Runtime Identity", sort_order=30, tags=("version",)),
        _p("runtime.readiness", "Runtime readiness", "Runtime Identity", route_or_detail="/health/ready", sort_order=40, tags=("readiness",)),
        _p("github.connection", "GitHub connection", "GitHub", source_authority="GITHUB_AUTH", route_or_detail="/github", sort_order=50, tags=("auth",)),
        _p("github.principal", "GitHub principal", "GitHub", source_authority="GITHUB_AUTH", route_or_detail="/github", sort_order=60, tags=("identity",)),
        _p("fabric.connection", "Repository Fabric connection", "Repository Fabric", route_or_detail="/fabric", sort_order=70, tags=("fabric",)),
        _p("conrrad.gate", "CONRRAD aggregate gate", "CONRRAD", source_authority="CONRRAD_LIVE_TRUTH", sort_order=80, tags=("gate", "conrrad")),
        _p("conrrad.required_services", "CONRRAD mandatory services", "CONRRAD", priority="P0", source_authority="CONRRAD_LIVE_TRUTH", implementation_status="PARTIAL", failure_reason="Main does not yet project all mandatory services from authoritative live truth.", sort_order=90, tags=("mandatory-services", "live-truth")),
        _p("bootstrap.gates", "Bootstrap verification gates", "CONRRAD", route_or_detail="/", sort_order=100, tags=("bootstrap", "gates")),
        _p("project.current_mission", "Current mission", "Project State", source_authority="CANONICAL_STATE", route_or_detail="/execution/missions", implementation_status="PARTIAL", sort_order=110, tags=("mission",)),
        _p("project.current_task", "Current task", "Project State", source_authority="CANONICAL_STATE", implementation_status="PARTIAL", sort_order=120, tags=("task",)),
        _p("project.next_action", "Next action", "Project State", source_authority="CANONICAL_STATE", implementation_status="PARTIAL", sort_order=130, tags=("next-action",)),
        _p("project.blockers", "Blockers", "Project State", source_authority="CANONICAL_STATE", implementation_status="PARTIAL", sort_order=140, tags=("blockers",)),
        _p("continuity.status", "Continuity timeline", "Continuity", source_authority="CONTINUITY_ENGINE", implementation_status="BOUND", route_or_detail="/continuity/timeline", sort_order=150, tags=("continuity", "timeline")),
        _p("continuity.recovery", "Continuity recovery", "Continuity", priority="P1", source_authority="CANONICAL_STATE", implementation_status="PLANNED", route_or_detail="/continuity/recovery", sort_order=160, tags=("recovery",)),
        _p("evidence.freshness", "Evidence freshness", "Evidence / Provenance", priority="P0", source_authority="EVIDENCE_REGISTRY", implementation_status="PLANNED", sort_order=170, tags=("evidence", "freshness")),
        _p("evidence.index", "Evidence index", "Evidence / Provenance", priority="P0", source_authority="CONTINUITY_ENGINE", route_or_detail="/audit/evidence", implementation_status="BOUND", sort_order=171, tags=("evidence", "index")),
        _p("audit.events", "Audit events", "Evidence / Provenance", priority="P0", source_authority="AUDIT_STORE", route_or_detail="/audit/events", implementation_status="BOUND", sort_order=181, tags=("audit", "events")),
        
        _p("evidence.provenance", "Evidence provenance", "Evidence / Provenance", priority="P0", source_authority="EVIDENCE_REGISTRY", implementation_status="BOUND", route_or_detail="/audit/provenance", sort_order=180, tags=("provenance",)),
        _p("execution.processing_matrix", "Processing matrix", "Execution", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/api/processing/matrix", sort_order=190, tags=("execution", "telemetry")),
        _p("execution.tasks", "Execution tasks", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/tasks", implementation_status="BOUND", sort_order=200, tags=("tasks",)),
        _p("execution.workers", "Execution workers", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/workers", implementation_status="BOUND", sort_order=210, tags=("workers",)),
        _p("execution.worker_detail", "Execution worker detail", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/workers/{worker_id}", implementation_status="BOUND", sort_order=211, tags=("workers", "detail")),
        _p("execution.results", "Execution results", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/results", implementation_status="PLANNED", sort_order=220, tags=("results",)),
        _p("intelligence.capabilities", "Intelligence capabilities", "Intelligence", priority="P0", route_or_detail="/intelligence/capabilities", sort_order=230, tags=("capabilities",)),
        _p("intelligence.models", "Intelligence models", "Intelligence", priority="P0", route_or_detail="/models", implementation_status="BOUND", sort_order=240, tags=("models",)),
        _p("intelligence.model_detail", "Intelligence model detail", "Intelligence", priority="P0", source_authority="RUNTIME_MODEL_REGISTRY", route_or_detail="/models/{model_id}", implementation_status="BOUND", sort_order=241, tags=("models", "detail")),
        _p("intelligence.executors", "Intelligence executors", "Intelligence", priority="P1", route_or_detail="/intelligence/executors", implementation_status="PLANNED", sort_order=250, tags=("executors",)),
        _p("intelligence.performance", "Intelligence performance", "Intelligence", priority="P2", route_or_detail="/intelligence/performance", implementation_status="PLANNED", sort_order=260, tags=("performance",)),
        _p("infrastructure.runtime", "Runtime topology", "Infrastructure", priority="P0", route_or_detail="/infrastructure/runtime", sort_order=270, tags=("topology",)),
        _p("infrastructure.github", "GitHub infrastructure", "Infrastructure", priority="P1", source_authority="GITHUB_AUTH", route_or_detail="/infrastructure/github", implementation_status="PLANNED", sort_order=280, tags=("github", "infrastructure")),
        _p("infrastructure.fabric", "Fabric infrastructure", "Infrastructure", priority="P1", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/infrastructure/fabric", implementation_status="PLANNED", sort_order=290, tags=("fabric", "infrastructure")),
        _p("infrastructure.mcp", "MCP infrastructure", "Infrastructure", priority="P2", source_authority="RUNTIME_MCP", route_or_detail="/infrastructure/mcp", implementation_status="PLANNED", sort_order=300, tags=("mcp",)),
        _p("infrastructure.azure", "Azure infrastructure", "Infrastructure", priority="P2", source_authority="AZURE_LIVE_TRUTH", route_or_detail="/infrastructure/azure", implementation_status="PLANNED", sort_order=310, tags=("azure",)),
        _p("security.trust", "Security and trust posture", "Security / Trust", source_authority="RUNTIME_SECURITY", priority="P0", implementation_status="PARTIAL", sort_order=320, tags=("security", "trust")),
        _p("communication.sessions", "Admin sessions", "Communication", priority="P0", source_authority="RUNTIME_AUTH", route_or_detail="/sessions", sort_order=330, tags=("sessions",)),
        _p("telemetry.live", "Live telemetry", "Telemetry", priority="P0", source_authority="TELEMETRY_STREAM", route_or_detail="/telemetry/live", sort_order=340, tags=("sse", "live")),
        _p("telemetry.timeline", "Telemetry timeline", "Telemetry", priority="P0", source_authority="TELEMETRY_STORE", route_or_detail="/telemetry/timeline", sort_order=350, tags=("timeline",)),
        _p("browser.dashboard", "Managed browser dashboard", "Browser", priority="P0", source_authority="BROWSER_RUNTIME", route_or_detail="/browser", sort_order=360, tags=("browser",)),
        _p("distribution.sync", "Governed SYNC state", "Distribution / Updates", priority="P0", source_authority="SYNC_SERVICE", implementation_status="BOUND", sort_order=370, tags=("sync", "updates")),
        _p("distribution.sync_stage", "SYNC stage capability", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", implementation_status="BLOCKED", failure_reason="Physical staging is not implemented; the backend now fails closed without mutating the verified candidate.", sort_order=380, tags=("sync", "stage")),
        _p("distribution.activation", "Activation capability", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", implementation_status="BLOCKED", failure_reason="Activation is intentionally fail-closed and not physically implemented.", sort_order=390, tags=("activation", "safe-fail-closed")),
        _p("distribution.rollback", "Rollback capability", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", implementation_status="BLOCKED", failure_reason="Physical rollback is not implemented; the backend now fails closed without mutating Runtime state.", sort_order=400, tags=("rollback", "safe-fail-closed")),
        
        # Batch 002: Master Inventory Expansion based on grounded reality
        _p("universe.project_detail", "Project detail", "Universe", priority="P2", source_authority="PROJECT_REGISTRY", route_or_detail="/universe/projects/{project_id}", implementation_status="PLANNED", sort_order=26, tags=("universe", "projects", "detail")),
        _p("execution.task_detail", "Execution task detail", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/tasks/{task_id}", implementation_status="PLANNED", sort_order=201, tags=("tasks", "detail")),
        _p("execution.context_detail", "Execution context detail", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/contexts/{execution_id}", implementation_status="PLANNED", sort_order=202, tags=("contexts", "detail")),
        _p("intelligence.model_bindings", "Model capability bindings", "Intelligence", priority="P1", source_authority="RUNTIME_MODEL_REGISTRY", route_or_detail="/models/bindings", implementation_status="PLANNED", sort_order=242, tags=("models", "bindings")),
        _p("intelligence.evaluations", "Model evaluation records", "Intelligence", priority="P1", source_authority="RUNTIME_MODEL_REGISTRY", route_or_detail="/intelligence/evaluations", implementation_status="PLANNED", sort_order=243, tags=("evaluations",)),
        _p("infrastructure.hardware_profiles", "Hardware profiles", "Infrastructure", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/infrastructure/hardware", implementation_status="PLANNED", sort_order=275, tags=("hardware", "profiles")),
        _p("mcp.tools", "MCP Tool definitions", "Infrastructure", priority="P1", source_authority="RUNTIME_MCP", route_or_detail="/mcp/tools", implementation_status="PLANNED", sort_order=301, tags=("mcp", "tools")),
        _p("mcp.tool_policies", "MCP Tool policies", "Infrastructure", priority="P1", source_authority="RUNTIME_MCP", route_or_detail="/mcp/policies", implementation_status="PLANNED", sort_order=302, tags=("mcp", "policies")),
        _p("security.tool_manifests", "Secure tool manifests", "Security / Trust", priority="P1", source_authority="RUNTIME_SECURITY", route_or_detail="/security/tools/manifests", implementation_status="PLANNED", sort_order=321, tags=("security", "tools", "manifests")),
        _p("tools.manifests", "Runtime tool manifests", "Execution", priority="P1", source_authority="RUNTIME_TOOL_REGISTRY", route_or_detail="/tools/manifests", implementation_status="PLANNED", sort_order=203, tags=("tools", "manifests")),

        # Batch 003: Master Inventory Expansion & Panel Binding
        _p("processing.events", "Processing events stream", "Telemetry", priority="P0", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/api/processing/events", implementation_status="BOUND", sort_order=410, tags=("telemetry", "events", "processing")),
        _p("events.bus", "Runtime event bus history", "Telemetry", priority="P1", source_authority="EVENT_BUS", route_or_detail="/api/events/bus", implementation_status="PLANNED", sort_order=411, tags=("events", "bus", "history")),
        _p("journal.operations", "Operation journal records", "Evidence / Provenance", priority="P1", source_authority="RUNTIME_JOURNAL", route_or_detail="/journal/operations", implementation_status="PLANNED", sort_order=412, tags=("journal", "operations", "provenance")),
        _p("journal.missions", "Mission journal history", "Project State", priority="P1", source_authority="RUNTIME_JOURNAL", route_or_detail="/journal/missions", implementation_status="PLANNED", sort_order=413, tags=("journal", "missions")),
        _p("security.grants", "Security authorization grants", "Security / Trust", priority="P1", source_authority="RUNTIME_SECURITY", route_or_detail="/security/grants", implementation_status="PLANNED", sort_order=414, tags=("security", "authorization", "grants")),
        _p("security.active_context", "Active security execution context", "Security / Trust", priority="P1", source_authority="RUNTIME_SECURITY", route_or_detail="/security/context", implementation_status="PLANNED", sort_order=415, tags=("security", "context")),
        _p("capability.gate_grants", "Capability gate active grants", "Security / Trust", priority="P1", source_authority="RUNTIME_CAPABILITY_GATE", route_or_detail="/capabilities/gate", implementation_status="PLANNED", sort_order=416, tags=("capabilities", "gate", "grants")),
        _p("secrets.references", "Encrypted secret references", "Security / Trust", priority="P1", source_authority="RUNTIME_SECRETS", route_or_detail="/secrets/references", implementation_status="PLANNED", sort_order=417, tags=("secrets", "encryption")),
        _p("execution.processes", "Subprocess execution monitor", "Execution", priority="P1", source_authority="RUNTIME_PROCESS_MANAGER", route_or_detail="/execution/processes", implementation_status="PLANNED", sort_order=418, tags=("execution", "processes", "subprocesses")),
        _p("workspace.detail", "Workspace instance detail", "Execution", priority="P2", source_authority="RUNTIME_WORKSPACE", route_or_detail="/workspaces/{workspace_id}", implementation_status="PLANNED", sort_order=419, tags=("workspaces", "detail")),
        _p("orchestration.routing_decisions", "Execution plan routing decisions", "Execution", priority="P1", source_authority="RUNTIME_ORCHESTRATOR", route_or_detail="/orchestration/routing", implementation_status="PLANNED", sort_order=420, tags=("orchestration", "routing", "decisions")),
        _p("orchestration.execution_plans", "Orchestration execution plans", "Execution", priority="P2", source_authority="RUNTIME_ORCHESTRATOR", route_or_detail="/orchestration/plans", implementation_status="PLANNED", sort_order=421, tags=("orchestration", "plans")),
        _p("sandbox.policies", "Process sandbox isolation policies", "Infrastructure", priority="P1", source_authority="RUNTIME_SANDBOX", route_or_detail="/sandbox/policies", implementation_status="PLANNED", sort_order=422, tags=("sandbox", "isolation", "policies")),
        _p("compute.remote_profiles", "Remote compute resource profiles", "Infrastructure", priority="P1", source_authority="RUNTIME_COMPUTE", route_or_detail="/compute/profiles", implementation_status="PLANNED", sort_order=423, tags=("compute", "profiles")),
        _p("compute.remote_sessions", "Remote compute lease sessions", "Infrastructure", priority="P2", source_authority="RUNTIME_COMPUTE", route_or_detail="/compute/sessions", implementation_status="PLANNED", sort_order=424, tags=("compute", "sessions", "leases")),
        _p("session.leases", "Active session leases", "Communication", priority="P2", source_authority="RUNTIME_SESSION", route_or_detail="/sessions/leases", implementation_status="PLANNED", sort_order=425, tags=("sessions", "leases")),
        _p("runtime.generation_fencing", "Runtime generation counter and fencing", "Runtime Identity", priority="P1", source_authority="RUNTIME_CORE", route_or_detail="/runtime/generation", implementation_status="PLANNED", sort_order=426, tags=("generation", "fencing", "safety")),
        _p("runtime.enrollment", "Instance enrollment lifecycle", "Runtime Identity", priority="P1", source_authority="RUNTIME_IDENTITY", route_or_detail="/identity/enrollment", implementation_status="PLANNED", sort_order=427, tags=("enrollment", "lifecycle")),
        _p("continuity.mutation_contract", "Repository mutation continuity contract", "Continuity", priority="P1", source_authority="RUNTIME_CONTINUITY", route_or_detail="/continuity/mutation", implementation_status="PLANNED", sort_order=428, tags=("continuity", "mutation", "contract")),
        _p("filesystem.workspace_service", "Scoped workspace filesystem service", "Infrastructure", priority="P2", source_authority="RUNTIME_FILESYSTEM", route_or_detail="/filesystem/workspace", implementation_status="PLANNED", sort_order=429, tags=("filesystem", "workspace")),

        # Batch 004: Real Endpoint Binding & Grounded Inventory Expansion
        _p("admin.restart", "Runtime restart action", "Security / Trust", priority="P0", source_authority="RUNTIME_ADMIN", route_or_detail="/admin/restart", implementation_status="BOUND", sort_order=329, tags=("admin", "lifecycle", "restart")),
        _p("intelligence.scorecards", "Benchmark certification scorecards", "Intelligence", priority="P1", source_authority="RUNTIME_BENCHMARK_STORE", route_or_detail="/intelligence/scorecards", implementation_status="PLANNED", sort_order=430, tags=("benchmarks", "scorecards", "intelligence")),
        _p("intelligence.benchmark_cases", "Benchmark test cases", "Intelligence", priority="P1", source_authority="RUNTIME_INTELLIGENCE", route_or_detail="/intelligence/benchmarks/cases", implementation_status="PLANNED", sort_order=431, tags=("benchmarks", "cases", "intelligence")),
        _p("intelligence.failure_records", "Capability execution failure records", "Intelligence", priority="P1", source_authority="RUNTIME_INTELLIGENCE", route_or_detail="/intelligence/failures", implementation_status="PLANNED", sort_order=432, tags=("failures", "intelligence", "diagnostics")),
        _p("intelligence.implementation_profiles", "Capability implementation profiles", "Intelligence", priority="P2", source_authority="RUNTIME_INTELLIGENCE", route_or_detail="/intelligence/implementations", implementation_status="PLANNED", sort_order=433, tags=("implementations", "profiles", "intelligence")),
        _p("intelligence.capability_taxonomy", "Local intelligence capability taxonomy", "Intelligence", priority="P1", source_authority="RUNTIME_INTELLIGENCE", route_or_detail="/intelligence/taxonomy", implementation_status="PLANNED", sort_order=434, tags=("taxonomy", "capabilities", "intelligence")),
        _p("security.context_guard", "Security isolation context guard", "Security / Trust", priority="P1", source_authority="RUNTIME_SECURITY", route_or_detail="/security/context-guard", implementation_status="PLANNED", sort_order=435, tags=("security", "isolation", "context-guard")),
        _p("security.execution_context", "Physical operation execution context", "Security / Trust", priority="P1", source_authority="RUNTIME_SECURITY", route_or_detail="/security/execution-context", implementation_status="PLANNED", sort_order=436, tags=("security", "context", "execution")),
        _p("security.authorized_pipeline", "Authorized execution 10-step pipeline", "Security / Trust", priority="P1", source_authority="RUNTIME_SECURITY", route_or_detail="/security/pipeline", implementation_status="PLANNED", sort_order=437, tags=("security", "pipeline", "execution")),
        _p("security.authority_validator", "Security authority and capability validator", "Security / Trust", priority="P1", source_authority="RUNTIME_SECURITY", route_or_detail="/security/authority-validator", implementation_status="PLANNED", sort_order=438, tags=("security", "authority", "validation")),
        _p("shell.executor", "Classified shell command executor", "Execution", priority="P2", source_authority="RUNTIME_SHELL", route_or_detail="/shell/executor", implementation_status="PLANNED", sort_order=439, tags=("shell", "execution", "effects")),

        # Batch 005: Control Center Live API Endpoint Binding & Grounded Subsystem Expansion
        _p("api.status", "Runtime operational status API", "Control Center", priority="P0", source_authority="RUNTIME_ROUTER", route_or_detail="/api/status", implementation_status="BOUND", sort_order=440, tags=("api", "status", "health")),
        _p("continuity.bootstrap_api", "Continuity bootstrap API", "Continuity", priority="P0", source_authority="CONTINUITY_ENGINE", route_or_detail="/api/v1/continuity/bootstrap", implementation_status="BOUND", sort_order=441, tags=("api", "continuity", "bootstrap")),
        _p("control.projections_api", "Control Center projection registry API", "Control Center", priority="P0", source_authority="PROJECTION_REGISTRY", route_or_detail="/api/control-center/projections", implementation_status="BOUND", sort_order=442, tags=("api", "projections", "control_center")),
        _p("telemetry.stream_api", "Telemetry event stream API", "Telemetry", priority="P0", source_authority="TELEMETRY_STREAM", route_or_detail="/api/v1/telemetry/stream", implementation_status="BOUND", sort_order=443, tags=("api", "telemetry", "stream", "sse")),
        _p("projects.registry", "Persistent project registry", "Projects / Workspaces", priority="P1", source_authority="PROJECT_REGISTRY", route_or_detail="/projects/registry", implementation_status="PLANNED", sort_order=444, tags=("projects", "registry", "storage")),
        _p("accounts.registry", "Persistent account registry", "Accounts / Identities", priority="P1", source_authority="ACCOUNT_REGISTRY", route_or_detail="/accounts/registry", implementation_status="PLANNED", sort_order=445, tags=("accounts", "registry", "github_principal")),
        _p("compute.runtime_capabilities", "Compute runtime capability observation registry", "Infrastructure", priority="P1", source_authority="COMPUTE_CAPABILITY_REGISTRY", route_or_detail="/compute/capabilities", implementation_status="PLANNED", sort_order=446, tags=("compute", "capabilities", "resources")),
        _p("compute.resource_discovery", "Compute local resource discovery service", "Infrastructure", priority="P2", source_authority="RESOURCE_DISCOVERY", route_or_detail="/compute/discovery", implementation_status="PLANNED", sort_order=447, tags=("compute", "discovery", "hardware")),
        _p("mcp.gateway", "MCP capability-validated tool execution gateway", "Infrastructure", priority="P1", source_authority="MCP_GATEWAY", route_or_detail="/mcp/gateway", implementation_status="PLANNED", sort_order=448, tags=("mcp", "gateway", "tools")),
        _p("tools.builtins", "Capability-gated built-in tool registry", "Execution", priority="P1", source_authority="TOOL_REGISTRY", route_or_detail="/tools/builtins", implementation_status="PLANNED", sort_order=449, tags=("tools", "builtins", "filesystem", "shell", "git")),
        _p("security.secure_tool_registry", "ExecutionContext-enforced tool execution registry", "Security / Trust", priority="P1", source_authority="SECURE_TOOL_REGISTRY", route_or_detail="/security/tool-registry", implementation_status="PLANNED", sort_order=450, tags=("security", "tools", "capabilities", "workspace")),
        _p("security.authorization_store", "Persistent security grant authorization store", "Security / Trust", priority="P1", source_authority="AUTHORIZATION_STORE", route_or_detail="/security/authorization-store", implementation_status="PLANNED", sort_order=451, tags=("security", "authorization", "grants", "generation")),
        _p("execution.manager", "Task execution queue and lifecycle manager", "Execution", priority="P1", source_authority="EXECUTION_MANAGER", route_or_detail="/execution/manager", implementation_status="PLANNED", sort_order=452, tags=("execution", "queue", "tasks", "history")),
        _p("execution.selector", "Capability-aware model executor selector", "Execution", priority="P1", source_authority="EXECUTOR_SELECTOR", route_or_detail="/execution/selector", implementation_status="PLANNED", sort_order=453, tags=("execution", "selector", "qwen", "deterministic")),
        _p("execution.runtime_policy", "Task execution runtime boundary policy", "Execution", priority="P1", source_authority="RUNTIME_POLICY", route_or_detail="/execution/policy", implementation_status="PLANNED", sort_order=454, tags=("execution", "policy", "limits", "domains")),
        _p("intelligence.benchmark_runner", "Deterministic benchmark runner execution engine", "Intelligence", priority="P1", source_authority="BENCHMARK_RUNNER", route_or_detail="/intelligence/benchmarks/runner", implementation_status="PLANNED", sort_order=455, tags=("intelligence", "benchmarks", "runner")),
        _p("intelligence.grading_engine", "Deterministic benchmark grading and scoring engine", "Intelligence", priority="P1", source_authority="GRADING_ENGINE", route_or_detail="/intelligence/grading", implementation_status="PLANNED", sort_order=456, tags=("intelligence", "grading", "evaluation")),
        _p("intelligence.evidence_builder", "Evaluation evidence and scorecard artifact builder", "Intelligence", priority="P1", source_authority="EVIDENCE_BUILDER", route_or_detail="/intelligence/evidence-builder", implementation_status="PLANNED", sort_order=457, tags=("intelligence", "evidence", "provenance")),
        _p("sync.package_verifier", "Cryptographic SHA256 sync package verifier", "Distribution / Updates", priority="P1", source_authority="SYNC_VERIFIER", route_or_detail="/distribution/sync/verifier", implementation_status="PLANNED", sort_order=458, tags=("sync", "verifier", "sha256", "signatures")),
        _p("sync.github_source", "GitHub release tag distribution sync source", "Distribution / Updates", priority="P1", source_authority="GITHUB_SYNC_SOURCE", route_or_detail="/distribution/sync/github-source", implementation_status="PLANNED", sort_order=459, tags=("sync", "github", "releases")),
        _p("telemetry.aggregator", "Telemetry matrix event aggregator", "Telemetry", priority="P1", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/telemetry/aggregator", implementation_status="PLANNED", sort_order=460, tags=("telemetry", "aggregator", "metrics")),
        _p("browser.broker_server", "Automated browser broker server", "Browser", priority="P2", source_authority="BROWSER_BROKER", route_or_detail="/browser/broker", implementation_status="PLANNED", sort_order=461, tags=("browser", "broker", "automation")),

        # Batch 006: Functional Projection Expansion & Operational Plane Grounding
        _p("api.bridge_tasks", "ChatGPT/Luna external bridge task creation", "Control Center", priority="P0", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge/tasks", implementation_status="BOUND", sort_order=462, tags=("api", "bridge", "tasks")),
        _p("api.bridge_task_query", "External bridge task status query", "Control Center", priority="P0", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge/tasks/{task_id}", implementation_status="BOUND", sort_order=463, tags=("api", "bridge", "tasks", "query")),
        _p("api.bridge_execution_query", "External bridge execution result query", "Control Center", priority="P0", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge/executions/{execution_id}", implementation_status="BOUND", sort_order=464, tags=("api", "bridge", "executions", "query")),
        _p("admin.logout", "Admin session termination", "Security / Trust", priority="P0", source_authority="RUNTIME_ADMIN", route_or_detail="/logout", implementation_status="BOUND", sort_order=465, tags=("admin", "auth", "session", "logout")),
        _p("github.disconnect", "GitHub principal disconnect action", "GitHub", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/github/disconnect", implementation_status="BOUND", sort_order=466, tags=("github", "auth", "disconnect")),
        _p("github.device_init", "GitHub OAuth device code flow initialization", "GitHub", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/github/device/init", implementation_status="BOUND", sort_order=467, tags=("github", "auth", "device_flow", "init")),
        _p("git.service", "Local repository git operations service", "Infrastructure", priority="P1", source_authority="GIT_SERVICE", route_or_detail="/git/service", implementation_status="PLANNED", sort_order=468, tags=("git", "service", "vcs")),
        _p("diagnostics.doctor", "Runtime diagnostic doctor service", "Control Center", priority="P1", source_authority="RUNTIME_DOCTOR", route_or_detail="/diagnostics/doctor", implementation_status="PLANNED", sort_order=469, tags=("diagnostics", "doctor", "health")),
        _p("platform.manager", "OS and runtime host platform manager", "Infrastructure", priority="P2", source_authority="PLATFORM_MANAGER", route_or_detail="/platform/manager", implementation_status="PLANNED", sort_order=470, tags=("platform", "os", "linux", "wsl2")),
        _p("process.manager", "Subprocess lifecycle supervisor", "Execution", priority="P1", source_authority="PROCESS_MANAGER", route_or_detail="/process/manager", implementation_status="PLANNED", sort_order=471, tags=("process", "manager", "subprocesses")),
        _p("updater.manager", "Release bundle and update lifecycle manager", "Distribution / Updates", priority="P1", source_authority="UPDATE_MANAGER", route_or_detail="/updater/manager", implementation_status="PLANNED", sort_order=472, tags=("updater", "releases", "packages")),
        _p("fabric.github_adapter", "GitHub repository fabric resource adapter", "Repository Fabric", priority="P1", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/adapters/github", implementation_status="PLANNED", sort_order=473, tags=("fabric", "github", "adapter")),
        _p("identity.enrollment", "Runtime machine enrollment manager", "Runtime Identity", priority="P1", source_authority="ENROLLMENT_MANAGER", route_or_detail="/identity/enrollment-manager", implementation_status="PLANNED", sort_order=474, tags=("identity", "enrollment", "machine_id")),
        _p("identity.runtime_identity", "Hardware fingerprint and key identity", "Runtime Identity", priority="P1", source_authority="RUNTIME_IDENTITY", route_or_detail="/identity/fingerprint", implementation_status="PLANNED", sort_order=475, tags=("identity", "fingerprint", "keys")),
        _p("journal.operation_store", "Durable operation journal storage", "Evidence / Provenance", priority="P1", source_authority="OPERATION_JOURNAL", route_or_detail="/journal/store", implementation_status="PLANNED", sort_order=476, tags=("journal", "store", "integrity")),
        _p("journal.mission_store", "Canonical mission history journal storage", "Project State", priority="P1", source_authority="MISSION_JOURNAL", route_or_detail="/journal/missions/store", implementation_status="PLANNED", sort_order=477, tags=("journal", "missions", "history")),
        _p("orchestration.kernel", "Stepwise plan execution kernel", "Execution", priority="P1", source_authority="ORCHESTRATION_KERNEL", route_or_detail="/orchestration/kernel", implementation_status="PLANNED", sort_order=478, tags=("orchestration", "kernel", "execution")),
        _p("orchestration.frontier", "Plan execution frontier scheduler", "Execution", priority="P2", source_authority="EXECUTION_FRONTIER", route_or_detail="/orchestration/frontier", implementation_status="PLANNED", sort_order=479, tags=("orchestration", "frontier", "steps")),
        _p("sandbox.manager", "Bounded execution sandbox supervisor", "Infrastructure", priority="P1", source_authority="SANDBOX_MANAGER", route_or_detail="/sandbox/manager", implementation_status="PLANNED", sort_order=480, tags=("sandbox", "manager", "isolation")),
        _p("sandbox.backend", "Low-level bubblewrap/chroot sandbox backend", "Infrastructure", priority="P2", source_authority="SANDBOX_BACKEND", route_or_detail="/sandbox/backend", implementation_status="PLANNED", sort_order=481, tags=("sandbox", "backend", "bwrap")),
        _p("secrets.backend", "Encrypted file secret storage backend", "Security / Trust", priority="P1", source_authority="SECRET_BACKEND", route_or_detail="/secrets/backend", implementation_status="PLANNED", sort_order=482, tags=("secrets", "backend", "storage")),
        _p("secrets.broker", "Scoped secret lease broker", "Security / Trust", priority="P1", source_authority="SECRET_BROKER", route_or_detail="/secrets/broker", implementation_status="PLANNED", sort_order=483, tags=("secrets", "broker", "leases")),
        _p("session.manager", "Interactive session lifecycle manager", "Communication", priority="P1", source_authority="SESSION_MANAGER", route_or_detail="/sessions/manager", implementation_status="PLANNED", sort_order=484, tags=("session", "manager", "lifecycles")),
        _p("workspace.ephemeral", "Ephemeral isolation workspace manager", "Execution", priority="P1", source_authority="EPHEMERAL_WORKSPACE", route_or_detail="/workspaces/ephemeral", implementation_status="PLANNED", sort_order=485, tags=("workspace", "ephemeral", "isolation")),

        # Batch 007: Functional Projection Deepening & Control Center Operational Grounding
        # --- BOUND: verified complete binding chain (route + handler + renderer + data source) ---
        _p("admin.executions", "Execution list compatibility surface", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/executions", implementation_status="BOUND", sort_order=486, tags=("execution", "compatibility", "admin")),
        _p("admin.workers", "Worker list compatibility surface", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/workers", implementation_status="BOUND", sort_order=487, tags=("workers", "compatibility", "admin")),
        _p("admin.capabilities", "Capability list compatibility surface", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/capabilities", implementation_status="BOUND", sort_order=488, tags=("capabilities", "compatibility", "admin")),

        # --- PLANNED: grounded in existing source classes/modules verified in source audit ---
        # Compute subsystem (runtime/compute/)
        _p("compute.colab_transport", "Colab remote compute transport layer", "Infrastructure", priority="P2", source_authority="COMPUTE_TRANSPORT", route_or_detail="/compute/colab/transport", implementation_status="PLANNED", sort_order=489, tags=("compute", "colab", "transport")),
        _p("compute.remote_manager", "Remote compute session lifecycle manager", "Infrastructure", priority="P1", source_authority="COMPUTE_REMOTE_MANAGER", route_or_detail="/compute/remote/manager", implementation_status="PLANNED", sort_order=490, tags=("compute", "remote", "sessions", "lifecycle")),
        _p("compute.mcp_bridge", "Colab synchronous MCP execution bridge", "Infrastructure", priority="P2", source_authority="COMPUTE_MCP_BRIDGE", route_or_detail="/compute/mcp-bridge", implementation_status="PLANNED", sort_order=491, tags=("compute", "mcp", "bridge", "colab")),

        # Continuity subsystem (runtime/continuity/)
        _p("continuity.engine", "Continuity state machine engine", "Continuity", priority="P1", source_authority="CONTINUITY_ENGINE", route_or_detail="/continuity/engine", implementation_status="PLANNED", sort_order=492, tags=("continuity", "engine", "state")),
        _p("continuity.state_resolver", "Bootstrap continuity state resolver", "Continuity", priority="P1", source_authority="CONTINUITY_STATE", route_or_detail="/continuity/state", implementation_status="PLANNED", sort_order=493, tags=("continuity", "state", "resolver")),

        # Core subsystem (runtime/core/)
        _p("core.access_verifier", "Critical access path verifier", "Security / Trust", priority="P1", source_authority="CORE_ACCESS_VERIFIER", route_or_detail="/core/access-verifier", implementation_status="PLANNED", sort_order=494, tags=("core", "access", "verification", "security")),
        _p("core.generation", "Runtime generation counter and stale fence", "Runtime Identity", priority="P1", source_authority="CORE_GENERATION", route_or_detail="/core/generation", implementation_status="PLANNED", sort_order=495, tags=("core", "generation", "fencing")),
        _p("core.recovery", "Runtime recovery manager", "Runtime Identity", priority="P1", source_authority="CORE_RECOVERY", route_or_detail="/core/recovery", implementation_status="PLANNED", sort_order=496, tags=("core", "recovery", "restart")),
        _p("core.inventory", "Bootstrap component inventory discovery", "Control Center", priority="P1", source_authority="CORE_INVENTORY", route_or_detail="/core/inventory", implementation_status="PLANNED", sort_order=497, tags=("core", "inventory", "bootstrap", "discovery")),
        _p("core.config", "Runtime configuration state", "Runtime Identity", priority="P1", source_authority="CORE_CONFIG", route_or_detail="/core/config", implementation_status="PLANNED", sort_order=498, tags=("core", "config", "runtime")),

        # Execution subsystem deepening (runtime/execution/)
        _p("execution.receipt_store", "Execution receipt persistent store", "Evidence / Provenance", priority="P1", source_authority="EXECUTION_RECEIPT_STORE", route_or_detail="/execution/receipts/store", implementation_status="PLANNED", sort_order=499, tags=("execution", "receipts", "store", "integrity")),
        _p("execution.model_registry", "Model definition and binding registry", "Intelligence", priority="P1", source_authority="EXECUTION_MODEL_REGISTRY", route_or_detail="/execution/model-registry", implementation_status="PLANNED", sort_order=500, tags=("execution", "models", "registry")),
        _p("execution.qwen_executor", "Qwen model executor implementation", "Intelligence", priority="P2", source_authority="QWEN_EXECUTOR", route_or_detail="/execution/executors/qwen", implementation_status="PLANNED", sort_order=501, tags=("execution", "qwen", "executor")),
        _p("execution.result_validator", "Model output result validator", "Intelligence", priority="P1", source_authority="RESULT_VALIDATOR", route_or_detail="/execution/validator", implementation_status="PLANNED", sort_order=502, tags=("execution", "validation", "output")),
        _p("execution.worker_manager", "Worker registration and lifecycle manager", "Execution", priority="P1", source_authority="WORKER_MANAGER", route_or_detail="/execution/worker-manager", implementation_status="PLANNED", sort_order=503, tags=("execution", "workers", "manager")),
        _p("execution.registry_recovery", "Registry crash recovery and attestation", "Execution", priority="P1", source_authority="REGISTRY_RECOVERY", route_or_detail="/execution/registry/recovery", implementation_status="PLANNED", sort_order=504, tags=("execution", "registry", "recovery", "attestation")),

        # Security subsystem deepening (runtime/security/)
        _p("security.generation_fence", "Generation-fenced concurrent write protection", "Security / Trust", priority="P1", source_authority="SECURITY_GENERATION_FENCE", route_or_detail="/security/generation-fence", implementation_status="PLANNED", sort_order=505, tags=("security", "generation", "fencing", "concurrency")),

        # Intelligence subsystem deepening (runtime/intelligence/)
        _p("intelligence.layer", "Local intelligence orchestration layer", "Intelligence", priority="P1", source_authority="INTELLIGENCE_LAYER", route_or_detail="/intelligence/layer", implementation_status="PLANNED", sort_order=506, tags=("intelligence", "layer", "orchestration")),
        _p("intelligence.telemetry", "Intelligence execution telemetry collector", "Telemetry", priority="P1", source_authority="INTELLIGENCE_TELEMETRY", route_or_detail="/intelligence/telemetry", implementation_status="PLANNED", sort_order=507, tags=("intelligence", "telemetry", "metrics")),
        _p("intelligence.benchmark_dataset", "Benchmark test dataset repository", "Intelligence", priority="P2", source_authority="BENCHMARK_DATASET", route_or_detail="/intelligence/benchmarks/dataset", implementation_status="PLANNED", sort_order=508, tags=("intelligence", "benchmarks", "dataset")),

        # MCP subsystem deepening (runtime/mcp/)
        _p("mcp.registry", "MCP tool definition registry", "Infrastructure", priority="P1", source_authority="MCP_TOOL_REGISTRY", route_or_detail="/mcp/registry", implementation_status="PLANNED", sort_order=509, tags=("mcp", "registry", "tools")),

        # Events subsystem (runtime/events/)
        _p("events.bus_service", "Runtime event publication and subscription bus", "Telemetry", priority="P1", source_authority="EVENT_BUS_SERVICE", route_or_detail="/events/bus-service", implementation_status="PLANNED", sort_order=510, tags=("events", "bus", "publish", "subscribe")),

        # Sync subsystem deepening (runtime/sync/)
        _p("sync.candidate_verifier", "Sync candidate cryptographic verifier", "Distribution / Updates", priority="P1", source_authority="SYNC_CANDIDATE_VERIFIER", route_or_detail="/sync/candidate-verifier", implementation_status="PLANNED", sort_order=511, tags=("sync", "verifier", "candidate", "sha256")),
        _p("sync.state_machine", "Sync lifecycle state machine", "Distribution / Updates", priority="P1", source_authority="SYNC_STATE_MACHINE", route_or_detail="/sync/state-machine", implementation_status="PLANNED", sort_order=512, tags=("sync", "state", "lifecycle")),

        # Telemetry subsystem deepening (runtime/telemetry/)
        _p("telemetry.collector", "Telemetry event collector and store", "Telemetry", priority="P1", source_authority="TELEMETRY_COLLECTOR", route_or_detail="/telemetry/collector", implementation_status="PLANNED", sort_order=513, tags=("telemetry", "collector", "store")),
        _p("telemetry.context", "Distributed trace context propagation", "Telemetry", priority="P2", source_authority="TELEMETRY_CONTEXT", route_or_detail="/telemetry/context", implementation_status="PLANNED", sort_order=514, tags=("telemetry", "tracing", "context")),
        _p("telemetry.envelope", "Telemetry event envelope and routing", "Telemetry", priority="P2", source_authority="TELEMETRY_ENVELOPE", route_or_detail="/telemetry/envelope", implementation_status="PLANNED", sort_order=515, tags=("telemetry", "envelope", "routing")),

        # Bootstrap subsystem deepening (runtime/bootstrap/)
        _p("bootstrap.three_plane", "Three-plane bootstrap verification engine", "CONRRAD", priority="P1", source_authority="BOOTSTRAP_THREE_PLANE", route_or_detail="/bootstrap/three-plane", implementation_status="PLANNED", sort_order=516, tags=("bootstrap", "three_plane", "verification")),
        _p("bootstrap.report", "Bootstrap report and component inventory", "CONRRAD", priority="P1", source_authority="BOOTSTRAP_REPORT", route_or_detail="/bootstrap/report", implementation_status="PLANNED", sort_order=517, tags=("bootstrap", "report", "inventory")),

        # Admin subsystem deepening (runtime/admin/)
        _p("admin.csrf", "CSRF token validation middleware", "Security / Trust", priority="P1", source_authority="ADMIN_CSRF", route_or_detail="/admin/csrf", implementation_status="PLANNED", sort_order=518, tags=("admin", "csrf", "security")),
        _p("admin.middleware", "Admin request authentication middleware", "Security / Trust", priority="P1", source_authority="ADMIN_MIDDLEWARE", route_or_detail="/admin/middleware", implementation_status="PLANNED", sort_order=519, tags=("admin", "middleware", "auth")),
        _p("admin.audit", "Admin operation audit trail", "Evidence / Provenance", priority="P1", source_authority="ADMIN_AUDIT", route_or_detail="/admin/audit", implementation_status="PLANNED", sort_order=520, tags=("admin", "audit", "operations")),

        # Batch 008: Master Inventory P0 Coverage & Operational Depth
        # Execution subsystem depth (runtime/execution/)
        _p("execution.deterministic_executor", "Deterministic tool executor", "Execution", priority="P1", source_authority="DETERMINISTIC_EXECUTOR", route_or_detail="/execution/deterministic-executor", implementation_status="PLANNED", sort_order=521, tags=("execution", "deterministic", "sandbox")),
        _p("execution.orchestrator", "Multi-step tool execution orchestrator", "Execution", priority="P1", source_authority="EXECUTION_ORCHESTRATOR", route_or_detail="/execution/orchestrator", implementation_status="PLANNED", sort_order=522, tags=("execution", "orchestrator", "tools")),
        _p("execution.task_context", "Task execution context manager", "Execution", priority="P2", source_authority="TASK_CONTEXT_MANAGER", route_or_detail="/execution/task-context", implementation_status="PLANNED", sort_order=523, tags=("execution", "context", "tasks")),
        _p("execution.capability_registry", "Executor capability registry", "Intelligence", priority="P1", source_authority="CAPABILITY_REGISTRY", route_or_detail="/execution/capability-registry", implementation_status="PLANNED", sort_order=524, tags=("execution", "capabilities", "registry")),

        # Capability gate subsystem depth (runtime/capability/)
        _p("capability.gate", "Runtime capability gate evaluator", "Security / Trust", priority="P1", source_authority="CAPABILITY_GATE", route_or_detail="/capability/gate", implementation_status="PLANNED", sort_order=525, tags=("capability", "gate", "security")),
        _p("capability.decision_log", "Capability authorization decision log", "Evidence / Provenance", priority="P2", source_authority="CAPABILITY_GATE", route_or_detail="/capability/decisions", implementation_status="PLANNED", sort_order=526, tags=("capability", "decisions", "audit")),

        # Continuity subsystem depth (runtime/continuity/)
        _p("continuity.reconciler", "Canonical runtime reconciler", "Continuity", priority="P1", source_authority="CONTINUITY_RECONCILER", route_or_detail="/continuity/reconciler", implementation_status="PLANNED", sort_order=527, tags=("continuity", "reconciliation", "canonical")),
        _p("continuity.operational_repo", "Operational repository provider", "Continuity", priority="P1", source_authority="OPERATIONAL_REPO_PROVIDER", route_or_detail="/continuity/operational-repo", implementation_status="PLANNED", sort_order=528, tags=("continuity", "operational", "git")),
        _p("continuity.event_stream", "Continuity event stream classifier", "Continuity", priority="P2", source_authority="CONTINUITY_EVENTS", route_or_detail="/continuity/event-stream", implementation_status="PLANNED", sort_order=529, tags=("continuity", "events", "stream")),
        _p("continuity.mutation_contract_engine", "Repository mutation continuity contract engine", "Continuity", priority="P1", source_authority="MUTATION_CONTRACT", route_or_detail="/continuity/mutation-contract", implementation_status="PLANNED", sort_order=530, tags=("continuity", "mutation", "contract")),

        # Core subsystem depth (runtime/core/)
        _p("core.runtime_engine", "Core runtime execution engine", "Control Center", priority="P1", source_authority="CORE_ENGINE", route_or_detail="/core/engine", implementation_status="PLANNED", sort_order=531, tags=("core", "engine", "runtime")),
        _p("core.runtime_state", "Runtime state lifecycle machine", "Runtime Identity", priority="P1", source_authority="CORE_ENGINE", route_or_detail="/core/state", implementation_status="PLANNED", sort_order=532, tags=("core", "state", "lifecycle")),
        _p("core.bootstrap_inventory", "Bootstrap component discovery inventory", "Control Center", priority="P2", source_authority="CORE_INVENTORY", route_or_detail="/core/bootstrap-inventory", implementation_status="PLANNED", sort_order=533, tags=("core", "inventory", "bootstrap")),

        # Repository Fabric subsystem depth (runtime/fabric/)
        _p("fabric.tenant", "Repository Fabric tenant configuration", "Repository Fabric", priority="P2", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/tenant", implementation_status="PLANNED", sort_order=534, tags=("fabric", "tenant", "config")),
        _p("fabric.project", "Repository Fabric project binding", "Repository Fabric", priority="P2", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/project", implementation_status="PLANNED", sort_order=535, tags=("fabric", "project", "binding")),
        _p("fabric.trust_token", "Repository Fabric cryptographic trust token", "Repository Fabric", priority="P1", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/trust-token", implementation_status="PLANNED", sort_order=536, tags=("fabric", "trust", "token")),
        _p("fabric.health_probe", "Repository Fabric connectivity health probe", "Repository Fabric", priority="P1", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/health-probe", implementation_status="PLANNED", sort_order=537, tags=("fabric", "health", "probe")),
        _p("fabric.provenance_store", "Fabric operation provenance store", "Evidence / Provenance", priority="P1", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/provenance/store", implementation_status="PLANNED", sort_order=538, tags=("fabric", "provenance", "store")),

        # GitHub subsystem depth (runtime/github/)
        _p("github.client", "GitHub REST API authenticated client", "GitHub", priority="P1", source_authority="GITHUB_CLIENT", route_or_detail="/github/client", implementation_status="PLANNED", sort_order=539, tags=("github", "client", "api")),
        _p("github.discovery_service", "GitHub organization and repository discovery service", "GitHub", priority="P1", source_authority="GITHUB_DISCOVERY", route_or_detail="/github/discovery", implementation_status="PLANNED", sort_order=540, tags=("github", "discovery", "repos")),

        # Platform adapter subsystem depth (runtime/platform/)
        _p("platform.linux_adapter", "Linux OS host abstraction adapter", "Infrastructure", priority="P2", source_authority="PLATFORM_ADAPTER", route_or_detail="/platform/linux", implementation_status="PLANNED", sort_order=541, tags=("platform", "linux", "os")),
        _p("platform.wsl2_adapter", "WSL2 environment host adapter", "Infrastructure", priority="P2", source_authority="PLATFORM_ADAPTER", route_or_detail="/platform/wsl2", implementation_status="PLANNED", sort_order=542, tags=("platform", "wsl2", "windows")),

        # Sandbox subsystem depth (runtime/sandbox/)
        _p("sandbox.isolation_policy", "Process isolation policy evaluator", "Infrastructure", priority="P1", source_authority="SANDBOX_POLICY", route_or_detail="/sandbox/isolation-policy", implementation_status="PLANNED", sort_order=543, tags=("sandbox", "isolation", "policy")),
        _p("sandbox.isolation_level", "Sandbox execution isolation level classifier", "Infrastructure", priority="P2", source_authority="SANDBOX_POLICY", route_or_detail="/sandbox/isolation-level", implementation_status="PLANNED", sort_order=544, tags=("sandbox", "isolation", "levels")),
        _p("sandbox.workspace_backend", "Workspace directory filesystem sandbox backend", "Infrastructure", priority="P2", source_authority="SANDBOX_BACKEND", route_or_detail="/sandbox/workspace-backend", implementation_status="PLANNED", sort_order=545, tags=("sandbox", "workspace", "filesystem")),
        _p("sandbox.restricted_process", "Restricted process bubblewrap execution backend", "Infrastructure", priority="P2", source_authority="SANDBOX_BACKEND", route_or_detail="/sandbox/restricted-process", implementation_status="PLANNED", sort_order=546, tags=("sandbox", "process", "bwrap")),

        # Workspace subsystem depth (runtime/workspace/)
        _p("workspace.manager", "Persistent workspace lifecycle manager", "Execution", priority="P1", source_authority="WORKSPACE_MANAGER", route_or_detail="/workspace/manager", implementation_status="PLANNED", sort_order=547, tags=("workspace", "manager", "lifecycle")),
        _p("workspace.lifecycle_state", "Workspace operational state tracker", "Execution", priority="P2", source_authority="WORKSPACE_MANAGER", route_or_detail="/workspace/state", implementation_status="PLANNED", sort_order=548, tags=("workspace", "state", "lifecycle")),

        # Tool registry subsystem depth (runtime/tools/)
        _p("tools.registry_service", "Built-in tool capability gate registry", "Execution", priority="P1", source_authority="TOOL_REGISTRY", route_or_detail="/tools/registry-service", implementation_status="PLANNED", sort_order=549, tags=("tools", "registry", "builtins")),
        _p("tools.manifest_store", "Tool manifest descriptor store", "Execution", priority="P2", source_authority="TOOL_REGISTRY", route_or_detail="/tools/manifest-store", implementation_status="PLANNED", sort_order=550, tags=("tools", "manifests", "descriptors")),

        # Diagnostics subsystem depth (runtime/diagnostics/)
        _p("diagnostics.runtime_doctor", "Runtime diagnostic doctor engine", "Control Center", priority="P1", source_authority="RUNTIME_DOCTOR", route_or_detail="/diagnostics/runtime-doctor", implementation_status="PLANNED", sort_order=551, tags=("diagnostics", "doctor", "checks")),
        _p("diagnostics.check_suite", "Subsystem diagnostic check suite", "Control Center", priority="P2", source_authority="RUNTIME_DOCTOR", route_or_detail="/diagnostics/check-suite", implementation_status="PLANNED", sort_order=552, tags=("diagnostics", "checks", "subsystems")),

        # Journal subsystem depth (runtime/journal/)
        _p("journal.append_stream", "Operation journal append stream", "Evidence / Provenance", priority="P1", source_authority="OPERATION_JOURNAL", route_or_detail="/journal/append-stream", implementation_status="PLANNED", sort_order=553, tags=("journal", "append", "stream")),
        _p("journal.mission_log", "Mission history journal ledger", "Project State", priority="P1", source_authority="MISSION_JOURNAL", route_or_detail="/journal/mission-log", implementation_status="PLANNED", sort_order=554, tags=("journal", "missions", "ledger")),

        # Security subsystem depth (runtime/security/)
        _p("security.active_context_manager", "Active security context state manager", "Security / Trust", priority="P1", source_authority="SECURITY_CONTEXT", route_or_detail="/security/active-context-manager", implementation_status="PLANNED", sort_order=555, tags=("security", "context", "active")),
        _p("security.authority_validator_service", "Cross-subsystem authority validation service", "Security / Trust", priority="P1", source_authority="AUTHORITY_VALIDATOR", route_or_detail="/security/authority-validator-service", implementation_status="PLANNED", sort_order=556, tags=("security", "authority", "validation")),

        # Compute subsystem depth (runtime/compute/)
        _p("compute.resource_discovery_service", "Compute hardware resource discovery service", "Infrastructure", priority="P1", source_authority="COMPUTE_DISCOVERY", route_or_detail="/compute/resource-discovery", implementation_status="PLANNED", sort_order=557, tags=("compute", "hardware", "discovery")),

        # Intelligence subsystem depth (runtime/intelligence/)
        _p("intelligence.grading_service", "Benchmark scoring and grading engine service", "Intelligence", priority="P1", source_authority="GRADING_ENGINE", route_or_detail="/intelligence/grading-service", implementation_status="PLANNED", sort_order=558, tags=("intelligence", "grading", "scoring")),

        # Batch 009: Master Inventory Expansion & Operational Grounding
        # Browser automation & security gates (runtime/browser/)
        _p("browser.action_authorization", "Browser action submission authorization gate", "Browser", priority="P1", source_authority="BROWSER_AUTHORIZATION", route_or_detail="/browser/authorization", implementation_status="PLANNED", sort_order=559, tags=("browser", "authorization", "gate")),
        _p("browser.pending_authorization", "Pending browser action authorization queue", "Browser", priority="P2", source_authority="BROWSER_AUTHORIZATION", route_or_detail="/browser/authorization/pending", implementation_status="PLANNED", sort_order=560, tags=("browser", "authorization", "queue")),
        _p("browser.session_manager", "Browser automation session manager", "Browser", priority="P1", source_authority="BROWSER_RUNTIME", route_or_detail="/browser/sessions", implementation_status="PLANNED", sort_order=561, tags=("browser", "manager", "sessions")),

        # Telemetry credential scrubber (runtime/telemetry/scrubber.py)
        _p("telemetry.metadata_scrubber", "Telemetry credential and secret redaction scrubber", "Telemetry", priority="P1", source_authority="TELEMETRY_SCRUBBER", route_or_detail="/telemetry/scrubber", implementation_status="PLANNED", sort_order=562, tags=("telemetry", "scrubber", "security", "redaction")),

        # Compute subsystem models & contracts (runtime/compute/)
        _p("compute.provider_interface", "Remote compute provider abstraction contract", "Infrastructure", priority="P2", source_authority="COMPUTE_PROVIDER", route_or_detail="/compute/provider-interface", implementation_status="PLANNED", sort_order=563, tags=("compute", "provider", "contract")),
        _p("compute.trust_profile", "Remote compute trust profile specification", "Infrastructure", priority="P2", source_authority="COMPUTE_PROVIDER", route_or_detail="/compute/trust-profile", implementation_status="PLANNED", sort_order=564, tags=("compute", "trust", "profile")),
        _p("compute.remote_lease", "Remote compute lease lifecycle record", "Infrastructure", priority="P1", source_authority="COMPUTE_PROVIDER", route_or_detail="/compute/remote/lease", implementation_status="PLANNED", sort_order=565, tags=("compute", "lease", "lifecycle")),
        _p("compute.remote_artifact", "Remote compute job artifact store", "Evidence / Provenance", priority="P2", source_authority="COMPUTE_PROVIDER", route_or_detail="/compute/remote/artifacts", implementation_status="PLANNED", sort_order=566, tags=("compute", "artifacts", "provenance")),
        _p("compute.remote_job", "Remote compute job execution descriptor", "Infrastructure", priority="P1", source_authority="COMPUTE_PROVIDER", route_or_detail="/compute/remote/job", implementation_status="PLANNED", sort_order=567, tags=("compute", "job", "execution")),

        # Orchestration plan models & routing (runtime/orchestration/plan.py)
        _p("orchestration.routing_classifier", "Plan execution routing classifier", "Execution", priority="P1", source_authority="RUNTIME_ORCHESTRATOR", route_or_detail="/orchestration/routing-classifier", implementation_status="PLANNED", sort_order=568, tags=("orchestration", "routing", "classification")),
        _p("orchestration.plan_structure", "Orchestration execution plan model", "Execution", priority="P2", source_authority="RUNTIME_ORCHESTRATOR", route_or_detail="/orchestration/plan-structure", implementation_status="PLANNED", sort_order=569, tags=("orchestration", "plan", "steps")),

        # Execution interfaces & context packaging (runtime/execution/interfaces.py)
        _p("execution.context_package", "Sealed task execution context package", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/context-package", implementation_status="PLANNED", sort_order=570, tags=("execution", "context", "package")),
        _p("execution.model_result", "Structured model execution result payload", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/model-result", implementation_status="PLANNED", sort_order=571, tags=("execution", "result", "metrics")),
        _p("execution.model_executor_contract", "Model executor abstraction contract", "Intelligence", priority="P1", source_authority="MODEL_EXECUTOR", route_or_detail="/execution/executor-contract", implementation_status="PLANNED", sort_order=572, tags=("execution", "model", "executor", "contract")),

        # Accounts subsystem entities & status (runtime/accounts/models.py)
        _p("accounts.status_lifecycle", "Account status lifecycle state machine", "Accounts / Identities", priority="P1", source_authority="ACCOUNT_REGISTRY", route_or_detail="/accounts/status", implementation_status="PLANNED", sort_order=573, tags=("accounts", "status", "lifecycle")),
        _p("accounts.entity_model", "Account entity descriptor schema", "Accounts / Identities", priority="P2", source_authority="ACCOUNT_REGISTRY", route_or_detail="/accounts/entity", implementation_status="PLANNED", sort_order=574, tags=("accounts", "model", "schema")),

        # Projects subsystem entities & status (runtime/projects/models.py)
        _p("projects.status_lifecycle", "Project lifecycle state tracker", "Projects / Workspaces", priority="P1", source_authority="PROJECT_REGISTRY", route_or_detail="/projects/status", implementation_status="PLANNED", sort_order=575, tags=("projects", "status", "lifecycle")),
        _p("projects.entity_model", "Project entity descriptor schema", "Projects / Workspaces", priority="P2", source_authority="PROJECT_REGISTRY", route_or_detail="/projects/entity", implementation_status="PLANNED", sort_order=576, tags=("projects", "model", "schema")),

        # Repository Fabric models & contracts (runtime/fabric/models.py)
        _p("fabric.node", "Repository Fabric node topology descriptor", "Repository Fabric", priority="P2", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/node", implementation_status="PLANNED", sort_order=577, tags=("fabric", "node", "topology")),
        _p("fabric.policy", "Repository Fabric access governance policy", "Repository Fabric", priority="P1", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/policy", implementation_status="PLANNED", sort_order=578, tags=("fabric", "policy", "governance")),
        _p("fabric.contract", "Repository Fabric binding contract schema", "Repository Fabric", priority="P1", source_authority="FABRIC_ADAPTER", route_or_detail="/fabric/contract", implementation_status="PLANNED", sort_order=579, tags=("fabric", "contract", "binding")),

        # Session lease models (runtime/session/lease.py)
        _p("session.lease_record", "Interactive session lease descriptor", "Communication", priority="P2", source_authority="SESSION_LEASE", route_or_detail="/sessions/lease-record", implementation_status="PLANNED", sort_order=580, tags=("session", "lease", "heartbeat")),
        _p("session.status_state", "Session lease status state machine", "Communication", priority="P2", source_authority="SESSION_LEASE", route_or_detail="/sessions/status-state", implementation_status="PLANNED", sort_order=581, tags=("session", "status", "lifecycle")),

        # Bootstrap gates & orchestrator (runtime/bootstrap/)
        _p("bootstrap.readiness_gates", "Bootstrap readiness gate evaluator", "CONRRAD", priority="P1", source_authority="BOOTSTRAP_GATES", route_or_detail="/bootstrap/gates", implementation_status="PLANNED", sort_order=582, tags=("bootstrap", "readiness", "gates")),
        _p("bootstrap.gate_result", "Bootstrap gate evaluation result schema", "CONRRAD", priority="P2", source_authority="BOOTSTRAP_GATES", route_or_detail="/bootstrap/gate-result", implementation_status="PLANNED", sort_order=583, tags=("bootstrap", "result", "schema")),
        _p("bootstrap.three_plane_orchestrator", "Three-plane bootstrap lifecycle orchestrator", "CONRRAD", priority="P1", source_authority="THREE_PLANE_BOOTSTRAP", route_or_detail="/bootstrap/orchestrator", implementation_status="PLANNED", sort_order=584, tags=("bootstrap", "three_plane", "orchestration")),

        # Filesystem & Git services (runtime/filesystem/, runtime/git/)
        _p("filesystem.service", "Scoped filesystem security operations service", "Infrastructure", priority="P1", source_authority="FILESYSTEM_SERVICE", route_or_detail="/filesystem/service", implementation_status="PLANNED", sort_order=585, tags=("filesystem", "service", "security")),
        _p("git.repository_service", "Governed git repository operations service", "Infrastructure", priority="P1", source_authority="GIT_SERVICE", route_or_detail="/git/repository-service", implementation_status="PLANNED", sort_order=586, tags=("git", "repository", "service")),

        # Admin session & audit models (runtime/admin/)
        _p("admin.session_model", "Admin interactive session model", "Communication", priority="P2", source_authority="ADMIN_SESSION", route_or_detail="/admin/session-model", implementation_status="PLANNED", sort_order=587, tags=("admin", "session", "model")),
        _p("admin.session_manager", "Admin interactive session manager", "Communication", priority="P1", source_authority="ADMIN_SESSION", route_or_detail="/admin/session-manager", implementation_status="PLANNED", sort_order=588, tags=("admin", "session", "manager")),
        _p("admin.audit_entry", "Admin audit event ledger entry", "Evidence / Provenance", priority="P2", source_authority="ADMIN_AUDIT", route_or_detail="/admin/audit-entry", implementation_status="PLANNED", sort_order=589, tags=("admin", "audit", "entry")),
        _p("admin.audit_log", "Admin audit event log manager", "Evidence / Provenance", priority="P1", source_authority="ADMIN_AUDIT", route_or_detail="/admin/audit-log", implementation_status="PLANNED", sort_order=590, tags=("admin", "audit", "log")),

        # Security execution receipt & pipeline (runtime/security/pipeline.py)
        _p("security.execution_receipt", "Physical execution receipt security descriptor", "Evidence / Provenance", priority="P1", source_authority="SECURITY_PIPELINE", route_or_detail="/security/receipt", implementation_status="PLANNED", sort_order=591, tags=("security", "receipt", "provenance")),
        _p("security.authorized_pipeline_engine", "10-step authorized execution pipeline engine", "Security / Trust", priority="P1", source_authority="SECURITY_PIPELINE", route_or_detail="/security/pipeline-engine", implementation_status="PLANNED", sort_order=592, tags=("security", "pipeline", "execution")),

        # Governed Sync models & verifier state (runtime/sync/models.py)
        _p("sync.candidate_identity", "Sync candidate cryptographic identity", "Distribution / Updates", priority="P1", source_authority="SYNC_MODELS", route_or_detail="/sync/candidate-identity", implementation_status="PLANNED", sort_order=593, tags=("sync", "candidate", "identity")),
        _p("sync.verification_state", "Sync candidate verification state machine", "Distribution / Updates", priority="P1", source_authority="SYNC_MODELS", route_or_detail="/sync/verification-state", implementation_status="PLANNED", sort_order=594, tags=("sync", "verification", "state")),
        _p("sync.sync_state", "Governed sync state machine status", "Distribution / Updates", priority="P1", source_authority="SYNC_MODELS", route_or_detail="/sync/state-status", implementation_status="PLANNED", sort_order=595, tags=("sync", "state", "governance")),
        _p("sync.result_model", "Governed sync execution result record", "Distribution / Updates", priority="P1", source_authority="SYNC_MODELS", route_or_detail="/sync/result-record", implementation_status="PLANNED", sort_order=596, tags=("sync", "result", "record")),

        # Batch 010: Master Inventory Expansion & Subsystem Grounding
        # Core subsystem depth (runtime/core/)
        _p("core.access_test_result", "Access verification test result schema", "Security / Trust", priority="P2", source_authority="CORE_ACCESS_VERIFIER", route_or_detail="/core/access-tests", implementation_status="PLANNED", sort_order=597, tags=("core", "access", "schema")),
        _p("core.critical_access_verifier", "Critical access path verification engine", "Security / Trust", priority="P1", source_authority="CORE_ACCESS_VERIFIER", route_or_detail="/core/critical-access", implementation_status="PLANNED", sort_order=598, tags=("core", "access", "verifier")),
        _p("core.component_inventory_model", "Component inventory descriptor schema", "Control Center", priority="P2", source_authority="CORE_INVENTORY", route_or_detail="/core/component-inventory", implementation_status="PLANNED", sort_order=599, tags=("core", "inventory", "components")),
        _p("core.inventory_discovery_service", "Runtime component inventory discovery scanner", "Control Center", priority="P1", source_authority="CORE_INVENTORY", route_or_detail="/core/inventory-discovery", implementation_status="PLANNED", sort_order=600, tags=("core", "discovery", "scanner")),
        _p("core.recovery_report", "Runtime crash recovery report descriptor", "Runtime Identity", priority="P2", source_authority="CORE_RECOVERY", route_or_detail="/core/recovery-report", implementation_status="PLANNED", sort_order=601, tags=("core", "recovery", "report")),
        _p("core.recovery_manager_service", "Runtime crash recovery lifecycle supervisor", "Runtime Identity", priority="P1", source_authority="CORE_RECOVERY", route_or_detail="/core/recovery-service", implementation_status="PLANNED", sort_order=602, tags=("core", "recovery", "manager")),

        # Event bus taxonomy & envelopes (runtime/events/bus.py)
        _p("events.event_type_taxonomy", "Runtime event taxonomy classifier", "Telemetry", priority="P2", source_authority="EVENT_BUS", route_or_detail="/events/types", implementation_status="PLANNED", sort_order=603, tags=("events", "taxonomy", "types")),
        _p("events.event_envelope", "Canonical runtime event envelope record", "Telemetry", priority="P2", source_authority="EVENT_BUS", route_or_detail="/events/envelope", implementation_status="PLANNED", sort_order=604, tags=("events", "envelope", "record")),

        # Execution tool invocation & receipts (runtime/execution/)
        _p("execution.tool_invocation", "Deterministic tool invocation descriptor", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/tool-invocation", implementation_status="PLANNED", sort_order=605, tags=("execution", "tools", "invocation")),
        _p("execution.tool_result", "Deterministic tool execution result payload", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/tool-result", implementation_status="PLANNED", sort_order=606, tags=("execution", "tools", "result")),
        _p("execution.receipt_store_service", "Execution receipt persistent ledger store", "Evidence / Provenance", priority="P1", source_authority="RECEIPT_STORE", route_or_detail="/execution/receipts/store-service", implementation_status="PLANNED", sort_order=607, tags=("execution", "receipts", "store")),
        _p("execution.status_state", "Task execution status state machine", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/status-state", implementation_status="PLANNED", sort_order=608, tags=("execution", "status", "lifecycle")),
        _p("execution.worker_state", "Worker operational state tracker", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/worker-state", implementation_status="PLANNED", sort_order=609, tags=("execution", "workers", "state")),
        _p("execution.worker_definition", "Worker capability and profile definition schema", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/worker-definition", implementation_status="PLANNED", sort_order=610, tags=("execution", "workers", "schema")),

        # GitHub discovery topology (runtime/github/discovery.py)
        _p("github.discovered_principal", "GitHub authenticated principal identity record", "GitHub", priority="P2", source_authority="GITHUB_DISCOVERY", route_or_detail="/github/discovered-principal", implementation_status="PLANNED", sort_order=611, tags=("github", "principal", "discovery")),
        _p("github.discovered_organization", "GitHub organization topology descriptor", "GitHub", priority="P2", source_authority="GITHUB_DISCOVERY", route_or_detail="/github/discovered-organization", implementation_status="PLANNED", sort_order=612, tags=("github", "organization", "discovery")),
        _p("github.discovered_repository", "GitHub repository resource descriptor", "GitHub", priority="P2", source_authority="GITHUB_DISCOVERY", route_or_detail="/github/discovered-repository", implementation_status="PLANNED", sort_order=613, tags=("github", "repository", "discovery")),

        # Machine enrollment protocols (runtime/identity/enrollment.py)
        _p("identity.enrollment_state", "Machine enrollment state machine", "Runtime Identity", priority="P2", source_authority="ENROLLMENT_MANAGER", route_or_detail="/identity/enrollment-state", implementation_status="PLANNED", sort_order=614, tags=("identity", "enrollment", "state")),
        _p("identity.challenge_response", "Cryptographic machine enrollment challenge protocol", "Runtime Identity", priority="P1", source_authority="ENROLLMENT_MANAGER", route_or_detail="/identity/challenge-response", implementation_status="PLANNED", sort_order=615, tags=("identity", "challenge", "crypto")),

        # Intelligence models & certification (runtime/intelligence/models.py)
        _p("intelligence.capability_tier", "Intelligence capability tier taxonomy", "Intelligence", priority="P2", source_authority="INTELLIGENCE_LAYER", route_or_detail="/intelligence/capability-tier", implementation_status="PLANNED", sort_order=616, tags=("intelligence", "tier", "taxonomy")),
        _p("intelligence.delegation_decision", "Model delegation decision record", "Intelligence", priority="P2", source_authority="INTELLIGENCE_LAYER", route_or_detail="/intelligence/delegation-decision", implementation_status="PLANNED", sort_order=617, tags=("intelligence", "delegation", "routing")),
        _p("intelligence.execution_mode", "Intelligence execution mode classifier", "Intelligence", priority="P2", source_authority="INTELLIGENCE_LAYER", route_or_detail="/intelligence/execution-mode", implementation_status="PLANNED", sort_order=618, tags=("intelligence", "mode", "classifier")),
        _p("intelligence.certification_status", "Benchmark certification status state machine", "Intelligence", priority="P1", source_authority="BENCHMARK_STORE", route_or_detail="/intelligence/certification-status", implementation_status="PLANNED", sort_order=619, tags=("intelligence", "certification", "status")),
        _p("intelligence.resource_fit", "Model hardware resource compatibility fit", "Intelligence", priority="P2", source_authority="INTELLIGENCE_LAYER", route_or_detail="/intelligence/resource-fit", implementation_status="PLANNED", sort_order=620, tags=("intelligence", "hardware", "compatibility")),
        _p("intelligence.benchmark_case_model", "Benchmark evaluation case specification", "Intelligence", priority="P2", source_authority="BENCHMARK_STORE", route_or_detail="/intelligence/benchmark-case-model", implementation_status="PLANNED", sort_order=621, tags=("intelligence", "benchmarks", "case")),
        _p("intelligence.benchmark_result_model", "Benchmark evaluation execution result record", "Intelligence", priority="P2", source_authority="BENCHMARK_STORE", route_or_detail="/intelligence/benchmark-result-model", implementation_status="PLANNED", sort_order=622, tags=("intelligence", "benchmarks", "result")),

        # Journal ledger entry models (runtime/journal/)
        _p("journal.entry_record", "Cryptographic operation journal entry record", "Evidence / Provenance", priority="P2", source_authority="OPERATION_JOURNAL", route_or_detail="/journal/entry-record", implementation_status="PLANNED", sort_order=623, tags=("journal", "entry", "crypto")),
        _p("journal.mission_entry_record", "Mission journal ledger entry record", "Project State", priority="P2", source_authority="MISSION_JOURNAL", route_or_detail="/journal/mission-entry-record", implementation_status="PLANNED", sort_order=624, tags=("journal", "mission", "entry")),

        # MCP gateway service (runtime/mcp/gateway.py)
        _p("mcp.gateway_service", "Capability-validated MCP tool execution gateway service", "Infrastructure", priority="P1", source_authority="MCP_GATEWAY", route_or_detail="/mcp/gateway-service", implementation_status="PLANNED", sort_order=625, tags=("mcp", "gateway", "tools")),

        # Process management records (runtime/process/manager.py)
        _p("process.state_lifecycle", "Subprocess state machine lifecycle tracker", "Execution", priority="P2", source_authority="PROCESS_MANAGER", route_or_detail="/process/state-lifecycle", implementation_status="PLANNED", sort_order=626, tags=("process", "state", "lifecycle")),
        _p("process.execution_record", "Supervised subprocess execution record", "Execution", priority="P2", source_authority="PROCESS_MANAGER", route_or_detail="/process/execution-record", implementation_status="PLANNED", sort_order=627, tags=("process", "record", "pid")),

        # Secrets backend & broker (runtime/secrets/backend.py)
        _p("secrets.file_backend", "Local encrypted file secret store backend", "Security / Trust", priority="P1", source_authority="SECRET_BACKEND", route_or_detail="/secrets/file-backend", implementation_status="PLANNED", sort_order=628, tags=("secrets", "encryption", "backend")),
        _p("secrets.secure_broker", "Lease-scoped credential broker service", "Security / Trust", priority="P1", source_authority="SECRET_BROKER", route_or_detail="/secrets/secure-broker", implementation_status="PLANNED", sort_order=629, tags=("secrets", "broker", "leases")),

        # Shell command classification (runtime/shell/executor.py)
        _p("shell.result_payload", "Classified shell command output result payload", "Execution", priority="P2", source_authority="RUNTIME_SHELL", route_or_detail="/shell/result-payload", implementation_status="PLANNED", sort_order=630, tags=("shell", "result", "payload")),
        _p("shell.effect_classifier", "Shell execution side-effect classifier", "Execution", priority="P1", source_authority="RUNTIME_SHELL", route_or_detail="/shell/effect-classifier", implementation_status="PLANNED", sort_order=631, tags=("shell", "effect", "classifier")),

        # Sync verification result (runtime/sync/verifier.py)
        _p("sync.verification_result", "Cryptographic sync package verification result record", "Distribution / Updates", priority="P1", source_authority="SYNC_VERIFIER", route_or_detail="/sync/verification-result", implementation_status="PLANNED", sort_order=632, tags=("sync", "verifier", "sha256")),

        # Telemetry trace context (runtime/telemetry/context.py)
        _p("telemetry.trace_context", "Distributed telemetry trace context propagator", "Telemetry", priority="P2", source_authority="TELEMETRY_CONTEXT", route_or_detail="/telemetry/trace-context", implementation_status="PLANNED", sort_order=633, tags=("telemetry", "tracing", "context")),

        # Updater distribution manifest (runtime/updater/manager.py)
        _p("updater.manifest_info", "Release bundle distribution update manifest", "Distribution / Updates", priority="P1", source_authority="UPDATE_MANAGER", route_or_detail="/updater/info", implementation_status="PLANNED", sort_order=634, tags=("updater", "manifest", "bundle")),

        # Batch 011: Master Inventory Expansion & Subsystem Grounding
        # Repository Fabric & Git service depth (runtime/git/service.py)
        _p("git.status", "Git repository working tree status", "Repository Fabric", priority="P0", source_authority="RUNTIME_GIT", route_or_detail="/git/status", implementation_status="PLANNED", sort_order=635, tags=("git", "status", "repository")),
        _p("git.branch_info", "Git branch metadata and tracking reference", "Repository Fabric", priority="P0", source_authority="RUNTIME_GIT", route_or_detail="/git/branch-info", implementation_status="PLANNED", sort_order=636, tags=("git", "branch", "metadata")),
        _p("git.diff_summary", "Git working tree diff summary", "Repository Fabric", priority="P1", source_authority="RUNTIME_GIT", route_or_detail="/git/diff-summary", implementation_status="PLANNED", sort_order=637, tags=("git", "diff", "working-tree")),

        # Workspace & Projects lifecycle (runtime/workspace/, runtime/projects/)
        _p("workspace.state", "Workspace lifecycle state machine", "Projects / Workspaces", priority="P0", source_authority="WORKSPACE_MANAGER", route_or_detail="/workspace/state", implementation_status="PLANNED", sort_order=638, tags=("workspace", "state", "lifecycle")),
        _p("workspace.ephemeral_manager", "Ephemeral workspace allocation manager", "Projects / Workspaces", priority="P1", source_authority="WORKSPACE_MANAGER", route_or_detail="/workspace/ephemeral", implementation_status="PLANNED", sort_order=639, tags=("workspace", "ephemeral", "provisioner")),
        _p("projects.project_status", "Project lifecycle status model", "Projects / Workspaces", priority="P1", source_authority="PROJECT_REGISTRY", route_or_detail="/projects/status-model", implementation_status="PLANNED", sort_order=640, tags=("projects", "status", "lifecycle")),

        # Session & Communication coordination (runtime/session/, runtime/api/bridge.py)
        _p("session.lease", "Session lease coordinator", "Communication", priority="P1", source_authority="SESSION_MANAGER", route_or_detail="/session/lease", implementation_status="PLANNED", sort_order=641, tags=("session", "lease", "coordinator")),
        _p("api.bridge_router", "ChatGPT/Luna bridge API router", "Communication", priority="P1", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge", implementation_status="PLANNED", sort_order=642, tags=("bridge", "api", "router")),

        # Sandbox & Isolation contracts (runtime/sandbox/)
        _p("sandbox.restricted_backend", "Restricted process sandbox execution backend", "Execution", priority="P1", source_authority="SANDBOX_MANAGER", route_or_detail="/sandbox/restricted-backend", implementation_status="PLANNED", sort_order=643, tags=("sandbox", "restricted", "process")),
        _p("sandbox.isolation_contract", "Sandbox isolation policy enforcement contract", "Execution", priority="P0", source_authority="SANDBOX_MANAGER", route_or_detail="/sandbox/isolation-contract", implementation_status="PLANNED", sort_order=644, tags=("sandbox", "isolation", "contract")),

        # Remote Compute infrastructure & Colab transport (runtime/compute/)
        _p("compute.colab_provider", "Colab compute execution provider", "Infrastructure", priority="P1", source_authority="COMPUTE_PROVIDER", route_or_detail="/compute/colab-provider", implementation_status="PLANNED", sort_order=645, tags=("compute", "colab", "provider")),
        _p("compute.cli_transport", "CLI Colab transport bridge", "Infrastructure", priority="P1", source_authority="COMPUTE_TRANSPORT", route_or_detail="/compute/cli-transport", implementation_status="PLANNED", sort_order=646, tags=("compute", "colab", "cli")),
        _p("compute.browser_transport", "Browser Colab transport bridge", "Infrastructure", priority="P1", source_authority="COMPUTE_TRANSPORT", route_or_detail="/compute/browser-transport", implementation_status="PLANNED", sort_order=647, tags=("compute", "colab", "browser")),
        _p("compute.lease_model", "Remote compute lease allocation model", "Infrastructure", priority="P1", source_authority="COMPUTE_MODEL", route_or_detail="/compute/lease-model", implementation_status="PLANNED", sort_order=648, tags=("compute", "lease", "model")),
        _p("compute.trust_profile_model", "Compute trust profile policy descriptor", "Infrastructure", priority="P0", source_authority="COMPUTE_POLICY", route_or_detail="/compute/trust-profile", implementation_status="PLANNED", sort_order=649, tags=("compute", "trust", "profile")),

        # Capability gate decisions (runtime/capability/gate.py)
        _p("capability.gate_engine", "Capability gate decision engine", "Execution", priority="P0", source_authority="CAPABILITY_GATE", route_or_detail="/capability/gate-engine", implementation_status="PLANNED", sort_order=650, tags=("capability", "gate", "decision")),
        _p("capability.decision_model", "Capability evaluation decision model", "Execution", priority="P1", source_authority="CAPABILITY_GATE", route_or_detail="/capability/decision-model", implementation_status="PLANNED", sort_order=651, tags=("capability", "decision", "model")),

        # Execution evaluation & models (runtime/execution/models.py)
        _p("execution.evaluation_record", "Execution evaluation benchmark record model", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/evaluation-record", implementation_status="PLANNED", sort_order=652, tags=("execution", "evaluation", "record")),

        # Intelligence benchmark & layer depth (runtime/intelligence/)
        _p("intelligence.benchmark_store", "Benchmark artifact repository store", "Intelligence", priority="P1", source_authority="BENCHMARK_STORE", route_or_detail="/intelligence/benchmark-store", implementation_status="PLANNED", sort_order=653, tags=("intelligence", "benchmark", "store")),
        _p("intelligence.local_layer", "Local intelligence inference layer engine", "Intelligence", priority="P0", source_authority="LOCAL_INTELLIGENCE", route_or_detail="/intelligence/local-layer", implementation_status="PLANNED", sort_order=654, tags=("intelligence", "local", "layer")),
        _p("intelligence.scorecard_model", "Benchmark scorecard assessment model", "Intelligence", priority="P1", source_authority="BENCHMARK_SCORECARD", route_or_detail="/intelligence/scorecard-model", implementation_status="PLANNED", sort_order=655, tags=("intelligence", "scorecard", "benchmark")),
        _p("intelligence.candidate_profile", "Implementation candidate capability profile", "Intelligence", priority="P1", source_authority="MODEL_PROFILE", route_or_detail="/intelligence/candidate-profile", implementation_status="PLANNED", sort_order=656, tags=("intelligence", "candidate", "profile")),
        _p("intelligence.assessment_request", "Capability assessment request model", "Intelligence", priority="P2", source_authority="INTELLIGENCE_MODEL", route_or_detail="/intelligence/assessment-request", implementation_status="PLANNED", sort_order=657, tags=("intelligence", "assessment", "request")),
        _p("intelligence.assessment_response", "Capability assessment response model", "Intelligence", priority="P2", source_authority="INTELLIGENCE_MODEL", route_or_detail="/intelligence/assessment-response", implementation_status="PLANNED", sort_order=658, tags=("intelligence", "assessment", "response")),
        _p("intelligence.grading_result", "Model evaluation grading result descriptor", "Intelligence", priority="P2", source_authority="GRADING_ENGINE", route_or_detail="/intelligence/grading-result", implementation_status="PLANNED", sort_order=659, tags=("intelligence", "grading", "result")),

        # Security context & boundaries (runtime/security/)
        _p("security.active_context_mgr", "Active security context boundary manager", "Security / Trust", priority="P0", source_authority="CONTEXT_MANAGER", route_or_detail="/security/active-context-mgr", implementation_status="PLANNED", sort_order=660, tags=("security", "context", "boundary")),
        _p("security.execution_context_model", "Security execution context descriptor model", "Security / Trust", priority="P1", source_authority="SECURITY_MODEL", route_or_detail="/security/execution-context-model", implementation_status="PLANNED", sort_order=661, tags=("security", "execution", "context")),

        # Continuity operational provider & records (runtime/continuity/)
        _p("continuity.operational_provider", "Operational repository provider service", "Continuity", priority="P0", source_authority="OPERATIONAL_PROVIDER", route_or_detail="/continuity/operational-provider", implementation_status="PLANNED", sort_order=662, tags=("continuity", "operational", "provider")),
        _p("continuity.event_record_model", "Continuity event history record model", "Continuity", priority="P1", source_authority="CONTINUITY_MODEL", route_or_detail="/continuity/event-record-model", implementation_status="PLANNED", sort_order=663, tags=("continuity", "event", "record")),

        # Fabric admission, models & contracts (runtime/fabric/)
        _p("fabric.admission_result", "Fabric node admission evaluation result model", "Infrastructure", priority="P1", source_authority="FABRIC_MODEL", route_or_detail="/fabric/admission-result", implementation_status="PLANNED", sort_order=664, tags=("fabric", "admission", "result")),
        _p("fabric.provenance_model", "Fabric provenance entry audit model", "Infrastructure", priority="P0", source_authority="FABRIC_MODEL", route_or_detail="/fabric/provenance-model", implementation_status="PLANNED", sort_order=665, tags=("fabric", "provenance", "audit")),
        _p("fabric.health_model", "Fabric cluster health assessment result model", "Infrastructure", priority="P0", source_authority="FABRIC_MODEL", route_or_detail="/fabric/health-model", implementation_status="PLANNED", sort_order=666, tags=("fabric", "health", "result")),
        _p("fabric.policy_model", "Fabric governance policy descriptor model", "Infrastructure", priority="P1", source_authority="FABRIC_MODEL", route_or_detail="/fabric/policy-model", implementation_status="PLANNED", sort_order=667, tags=("fabric", "policy", "governance")),
        _p("fabric.contract_model", "Fabric bilateral contract descriptor model", "Infrastructure", priority="P1", source_authority="FABRIC_MODEL", route_or_detail="/fabric/contract-model", implementation_status="PLANNED", sort_order=668, tags=("fabric", "contract", "descriptor")),

        # Diagnostics & Updater depth (runtime/diagnostics/, runtime/updater/)
        _p("diagnostics.diagnostic_check", "Diagnostic health check descriptor model", "Infrastructure", priority="P1", source_authority="RUNTIME_DOCTOR", route_or_detail="/diagnostics/check-model", implementation_status="PLANNED", sort_order=669, tags=("diagnostics", "health", "check")),
        _p("updater.channel_state", "Update channel governance state model", "Distribution / Updates", priority="P1", source_authority="UPDATE_MANAGER", route_or_detail="/updater/channel-state", implementation_status="PLANNED", sort_order=670, tags=("updater", "channel", "governance")),

        # Batch 012: Master Inventory Expansion & Subsystem Grounding
        # Fabric & Tenancy models (runtime/fabric/models.py)
        _p("fabric.tenant_model", "Fabric tenant identity and governance model", "Infrastructure", priority="P1", source_authority="FABRIC_MODEL", route_or_detail="/fabric/tenant-model", implementation_status="PLANNED", sort_order=671, tags=("fabric", "tenant", "governance")),
        _p("fabric.project_model", "Fabric project workspace model", "Infrastructure", priority="P1", source_authority="FABRIC_MODEL", route_or_detail="/fabric/project-model", implementation_status="PLANNED", sort_order=672, tags=("fabric", "project", "workspace")),
        _p("fabric.trust_token_model", "Fabric bilateral trust token model", "Infrastructure", priority="P0", source_authority="FABRIC_MODEL", route_or_detail="/fabric/trust-token", implementation_status="PLANNED", sort_order=673, tags=("fabric", "trust", "token")),
        _p("fabric.node_status_model", "Fabric node cluster status descriptor", "Infrastructure", priority="P0", source_authority="FABRIC_MODEL", route_or_detail="/fabric/node-status", implementation_status="PLANNED", sort_order=674, tags=("fabric", "node", "status")),

        # Events & Messaging broker (runtime/events/bus.py)
        _p("events.event_bus_service", "Runtime central event bus broker service", "Telemetry", priority="P0", source_authority="EVENT_BUS", route_or_detail="/events/bus-service", implementation_status="PLANNED", sort_order=675, tags=("events", "bus", "broker")),
        _p("events.event_listener_registry", "Event subscription and listener registry", "Telemetry", priority="P1", source_authority="EVENT_BUS", route_or_detail="/events/listeners", implementation_status="PLANNED", sort_order=676, tags=("events", "listeners", "registry")),

        # Identity & Enrollment lifecycle (runtime/identity/)
        _p("identity.enrollment_manager", "Machine enrollment lifecycle supervisor", "Runtime Identity", priority="P0", source_authority="ENROLLMENT_MANAGER", route_or_detail="/identity/enrollment-manager", implementation_status="PLANNED", sort_order=677, tags=("identity", "enrollment", "supervisor")),
        _p("identity.key_attestation", "Cryptographic identity key attestation provider", "Runtime Identity", priority="P0", source_authority="RUNTIME_IDENTITY", route_or_detail="/identity/key-attestation", implementation_status="PLANNED", sort_order=678, tags=("identity", "crypto", "attestation")),

        # Core Generation & Engine state (runtime/core/)
        _p("core.runtime_generation", "Runtime generational epoch state coordinator", "Runtime Identity", priority="P0", source_authority="RUNTIME_ENGINE", route_or_detail="/core/generation", implementation_status="PLANNED", sort_order=679, tags=("core", "generation", "epoch")),
        _p("core.runtime_config_model", "Runtime configuration schema descriptor", "Runtime Identity", priority="P1", source_authority="RUNTIME_CONFIG", route_or_detail="/core/config-model", implementation_status="PLANNED", sort_order=680, tags=("core", "config", "schema")),
        _p("core.runtime_engine_state", "Runtime execution engine state machine", "Runtime Identity", priority="P0", source_authority="RUNTIME_ENGINE", route_or_detail="/core/engine-state", implementation_status="PLANNED", sort_order=681, tags=("core", "engine", "state")),

        # Execution deterministic & models (runtime/execution/)
        _p("execution.deterministic_engine", "Deterministic tool execution supervisor engine", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/deterministic-engine", implementation_status="PLANNED", sort_order=682, tags=("execution", "deterministic", "engine")),
        _p("execution.task_context_model", "Task execution contextual descriptor", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/task-context", implementation_status="PLANNED", sort_order=683, tags=("execution", "task", "context")),
        _p("execution.qwen_model_executor", "Qwen localized model execution driver", "Execution", priority="P1", source_authority="MODEL_EXECUTOR", route_or_detail="/execution/qwen-executor", implementation_status="PLANNED", sort_order=684, tags=("execution", "model", "qwen")),
        _p("execution.executor_selector", "Dynamic executor capability selector", "Execution", priority="P1", source_authority="EXECUTOR_SELECTOR", route_or_detail="/execution/executor-selector", implementation_status="PLANNED", sort_order=685, tags=("execution", "selector", "capability")),
        _p("execution.recovery_attestation", "Model registry recovery attestation model", "Execution", priority="P1", source_authority="MODEL_REGISTRY", route_or_detail="/execution/recovery-attestation", implementation_status="PLANNED", sort_order=686, tags=("execution", "recovery", "attestation")),

        # Intelligence & Evaluation depth (runtime/intelligence/)
        _p("intelligence.implementation_profile", "Model implementation capability profile schema", "Intelligence", priority="P1", source_authority="MODEL_PROFILE", route_or_detail="/intelligence/implementation-profile", implementation_status="PLANNED", sort_order=687, tags=("intelligence", "profile", "model")),
        _p("intelligence.repeatability_stats", "Benchmark execution repeatability statistics", "Intelligence", priority="P2", source_authority="BENCHMARK_STORE", route_or_detail="/intelligence/repeatability-stats", implementation_status="PLANNED", sort_order=688, tags=("intelligence", "benchmark", "stats")),
        _p("intelligence.failure_record_model", "Intelligence execution failure record schema", "Intelligence", priority="P2", source_authority="INTELLIGENCE_LAYER", route_or_detail="/intelligence/failure-record", implementation_status="PLANNED", sort_order=689, tags=("intelligence", "failure", "record")),
        _p("intelligence.hardware_profile_model", "Intelligence hardware compute profile descriptor", "Intelligence", priority="P1", source_authority="HARDWARE_PROFILE", route_or_detail="/intelligence/hardware-profile", implementation_status="PLANNED", sort_order=690, tags=("intelligence", "hardware", "profile")),

        # Journal & Ledger services (runtime/journal/)
        _p("journal.operation_journal", "Cryptographic operation journal ledger service", "Evidence / Provenance", priority="P0", source_authority="OPERATION_JOURNAL", route_or_detail="/journal/operation-service", implementation_status="PLANNED", sort_order=691, tags=("journal", "operation", "crypto")),
        _p("journal.mission_journal", "Mission lifecycle audit journal service", "Project State", priority="P0", source_authority="MISSION_JOURNAL", route_or_detail="/journal/mission-service", implementation_status="PLANNED", sort_order=692, tags=("journal", "mission", "audit")),

        # MCP Gateway & Tools (runtime/mcp/)
        _p("mcp.tool_registry_service", "MCP registered tool catalog service", "Infrastructure", priority="P0", source_authority="MCP_REGISTRY", route_or_detail="/mcp/tool-registry-service", implementation_status="PLANNED", sort_order=693, tags=("mcp", "tools", "registry")),
        _p("mcp.policy_violation_handler", "MCP capability policy violation trap handler", "Infrastructure", priority="P1", source_authority="MCP_GATEWAY", route_or_detail="/mcp/policy-violation", implementation_status="PLANNED", sort_order=694, tags=("mcp", "policy", "violation")),

        # Sandbox & Process Isolation (runtime/sandbox/)
        _p("sandbox.manager_service", "Sandbox execution lifecycle manager service", "Execution", priority="P0", source_authority="SANDBOX_MANAGER", route_or_detail="/sandbox/manager-service", implementation_status="PLANNED", sort_order=695, tags=("sandbox", "manager", "isolation")),
        _p("sandbox.isolation_level_taxonomy", "Sandbox isolation level taxonomy model", "Execution", priority="P1", source_authority="SANDBOX_MANAGER", route_or_detail="/sandbox/isolation-levels", implementation_status="PLANNED", sort_order=696, tags=("sandbox", "isolation", "taxonomy")),

        # Secrets & Cryptographic Broker (runtime/secrets/)
        _p("secrets.secret_handle_model", "Lease-bound secret reference handle model", "Security / Trust", priority="P1", source_authority="SECRET_BROKER", route_or_detail="/secrets/secret-handle", implementation_status="PLANNED", sort_order=697, tags=("secrets", "handle", "lease")),
        _p("secrets.credential_broker", "Account credential lease broker service", "Security / Trust", priority="P0", source_authority="SECRET_BROKER", route_or_detail="/secrets/credential-broker", implementation_status="PLANNED", sort_order=698, tags=("secrets", "credential", "broker")),

        # Security & Context Enforcement (runtime/security/)
        _p("security.authority_validator_engine", "Authority validation rules engine", "Security / Trust", priority="P0", source_authority="AUTHORITY_VALIDATOR", route_or_detail="/security/authority-validator", implementation_status="PLANNED", sort_order=699, tags=("security", "authority", "validator")),
        _p("security.context_guard_service", "Context boundary guard inspection service", "Security / Trust", priority="P0", source_authority="CONTEXT_GUARD", route_or_detail="/security/context-guard", implementation_status="PLANNED", sort_order=700, tags=("security", "context", "guard")),
        _p("security.generation_fence_engine", "Generational boundary fence enforcer", "Security / Trust", priority="P0", source_authority="GENERATION_FENCE", route_or_detail="/security/generation-fence", implementation_status="PLANNED", sort_order=701, tags=("security", "generation", "fence")),
        _p("security.tool_manifest_model", "Secure tool manifest policy descriptor model", "Security / Trust", priority="P1", source_authority="SECURE_TOOLS", route_or_detail="/security/tool-manifest", implementation_status="PLANNED", sort_order=702, tags=("security", "tools", "manifest")),

        # Sync & Verification (runtime/sync/)
        _p("sync.github_source_provider", "GitHub release distribution source provider", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", route_or_detail="/sync/github-source", implementation_status="PLANNED", sort_order=703, tags=("sync", "github", "source")),
        _p("sync.candidate_verifier_engine", "Sync release candidate cryptographic verifier", "Distribution / Updates", priority="P0", source_authority="SYNC_VERIFIER", route_or_detail="/sync/candidate-verifier", implementation_status="PLANNED", sort_order=704, tags=("sync", "verifier", "crypto")),

        # Telemetry & Trace (runtime/telemetry/)
        _p("telemetry.aggregator_service", "Telemetry metrics aggregation pipeline", "Telemetry", priority="P1", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/telemetry/aggregator-service", implementation_status="PLANNED", sort_order=705, tags=("telemetry", "aggregator", "metrics")),
        _p("telemetry.collector_service", "Real-time telemetry event collector service", "Telemetry", priority="P1", source_authority="TELEMETRY_COLLECTOR", route_or_detail="/telemetry/collector-service", implementation_status="PLANNED", sort_order=706, tags=("telemetry", "collector", "events")),

        # Updater (runtime/updater/)
        _p("updater.manager_service", "Release bundle update supervisor service", "Distribution / Updates", priority="P1", source_authority="UPDATE_MANAGER", route_or_detail="/updater/manager-service", implementation_status="PLANNED", sort_order=707, tags=("updater", "manager", "bundle")),

        # Batch 013: Identity & Attestation (runtime/identity/)
        _p("identity.hardware_fingerprint", "Hardware platform machine fingerprint descriptor", "Runtime Identity", priority="P0", source_authority="RUNTIME_IDENTITY", route_or_detail="/identity/fingerprint", implementation_status="PLANNED", sort_order=708, tags=("identity", "hardware", "fingerprint")),
        _p("identity.session_attestation", "Active identity session cryptographic attestation", "Runtime Identity", priority="P0", source_authority="RUNTIME_IDENTITY", route_or_detail="/identity/session-attestation", implementation_status="PLANNED", sort_order=709, tags=("identity", "session", "attestation")),

        # Batch 013: Fabric & Node Health (runtime/fabric/)
        _p("fabric.admission_validator", "Fabric admission token and authorization validator", "Repository Fabric", priority="P0", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/fabric/admission-validator", implementation_status="PLANNED", sort_order=710, tags=("fabric", "admission", "validator")),
        _p("fabric.node_heartbeat", "Repository Fabric node live heartbeat monitor", "Repository Fabric", priority="P0", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/fabric/node-heartbeat", implementation_status="PLANNED", sort_order=711, tags=("fabric", "node", "heartbeat")),

        # Batch 013: GitHub Integration (runtime/github/)
        _p("github.rate_limit_monitor", "GitHub API rate limit and quota monitoring surface", "GitHub", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/github/rate-limits", implementation_status="PLANNED", sort_order=712, tags=("github", "rate-limits", "quota")),
        _p("github.scope_attestation", "OAuth and installation token scope verification attestation", "GitHub", priority="P1", source_authority="GITHUB_AUTH", route_or_detail="/github/scopes", implementation_status="PLANNED", sort_order=713, tags=("github", "scopes", "attestation")),

        # Batch 013: Core Engine & Subsystems (runtime/core/)
        _p("core.lifecycle_controller", "Runtime core lifecycle phase controller", "Runtime Identity", priority="P0", source_authority="RUNTIME_ENGINE", route_or_detail="/core/lifecycle", implementation_status="PLANNED", sort_order=714, tags=("core", "lifecycle", "state")),
        _p("core.subsystem_manifest", "Registered subsystem dependency manifest and status", "Runtime Identity", priority="P0", source_authority="RUNTIME_CONFIG", route_or_detail="/core/subsystem-manifest", implementation_status="PLANNED", sort_order=715, tags=("core", "subsystem", "manifest")),

        # Batch 013: Execution & Workers (runtime/execution/)
        _p("execution.worker_supervisor", "Supervised worker execution pool state and health", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/worker-supervisor", implementation_status="PLANNED", sort_order=716, tags=("execution", "worker", "supervisor")),
        _p("execution.policy_enforcer", "Active runtime execution policy constraint enforcer", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/policy-enforcer", implementation_status="PLANNED", sort_order=717, tags=("execution", "policy", "enforcer")),
        _p("execution.result_validator_service", "Model output validation and conformance evaluation service", "Execution", priority="P1", source_authority="MODEL_VALIDATOR", route_or_detail="/execution/result-validator-service", implementation_status="PLANNED", sort_order=718, tags=("execution", "validator", "conformance")),

        # Batch 013: Capabilities & Intelligence (runtime/capability/, runtime/intelligence/)
        _p("capability.gate_evaluator", "Dynamic capability gate policy evaluator service", "Intelligence", priority="P0", source_authority="CAPABILITY_GATE", route_or_detail="/capability/gate-evaluator", implementation_status="PLANNED", sort_order=719, tags=("capability", "gate", "evaluator")),
        _p("intelligence.evaluation_pipeline", "Automated intelligence grading and evaluation pipeline", "Intelligence", priority="P1", source_authority="GRADING_ENGINE", route_or_detail="/intelligence/evaluation-pipeline", implementation_status="PLANNED", sort_order=720, tags=("intelligence", "grading", "evaluation")),
        _p("intelligence.model_telemetry", "Inference and model latency telemetry tracking", "Intelligence", priority="P1", source_authority="INTELLIGENCE_TELEMETRY", route_or_detail="/intelligence/model-telemetry", implementation_status="PLANNED", sort_order=721, tags=("intelligence", "telemetry", "latency")),

        # Batch 013: Accounts & Projects (runtime/accounts/, runtime/projects/)
        _p("accounts.authorization_profile", "Account authorization role and security profile descriptor", "Accounts / Identities", priority="P0", source_authority="ACCOUNT_REGISTRY", route_or_detail="/accounts/auth-profile", implementation_status="PLANNED", sort_order=722, tags=("accounts", "auth", "profile")),
        _p("projects.workspace_mapping", "Project to workspace filesystem binding mapping", "Projects / Workspaces", priority="P0", source_authority="PROJECT_REGISTRY", route_or_detail="/projects/workspace-mapping", implementation_status="PLANNED", sort_order=723, tags=("projects", "workspace", "mapping")),

        # Batch 013: Telemetry & Events (runtime/telemetry/, runtime/events/)
        _p("telemetry.trace_pipeline", "Distributed trace context propagation and span pipeline", "Telemetry", priority="P1", source_authority="TRACE_CONTEXT", route_or_detail="/telemetry/trace-pipeline", implementation_status="PLANNED", sort_order=724, tags=("telemetry", "trace", "spans")),
        _p("telemetry.domain_router", "Domain-classified telemetry routing and filtering engine", "Telemetry", priority="P0", source_authority="TELEMETRY_ROUTER", route_or_detail="/telemetry/domain-router", implementation_status="PLANNED", sort_order=725, tags=("telemetry", "domain", "routing")),
        _p("events.subscription_manager", "Event subscription topic and filter dispatcher", "Telemetry", priority="P0", source_authority="EVENT_BUS", route_or_detail="/events/subscription-manager", implementation_status="PLANNED", sort_order=726, tags=("events", "subscription", "dispatcher")),
        _p("events.delivery_attestation", "Critical event delivery receipt and acknowledgement attestation", "Telemetry", priority="P0", source_authority="EVENT_BUS", route_or_detail="/events/delivery-attestation", implementation_status="PLANNED", sort_order=727, tags=("events", "delivery", "receipt")),

        # Batch 013: Browser Automation (runtime/browser/)
        _p("browser.submission_guard", "Managed browser submission authorization security guard", "Browser", priority="P0", source_authority="BROWSER_AUTH", route_or_detail="/browser/submission-guard", implementation_status="PLANNED", sort_order=728, tags=("browser", "authorization", "guard")),
        _p("browser.broker_lifecycle", "Browser automation broker service lifecycle monitor", "Browser", priority="P0", source_authority="BROWSER_BROKER", route_or_detail="/browser/broker-lifecycle", implementation_status="PLANNED", sort_order=729, tags=("browser", "broker", "lifecycle")),

        # Batch 013: Continuity & Journal (runtime/continuity/, runtime/journal/)
        _p("continuity.reconciler_service", "Canonical continuity reconciler execution engine", "Continuity", priority="P0", source_authority="CONTINUITY_RECONCILER", route_or_detail="/continuity/reconciler-service", implementation_status="PLANNED", sort_order=730, tags=("continuity", "reconciler", "engine")),
        _p("journal.integrity_verifier", "Cryptographic ledger hash-chain integrity verification service", "Evidence / Provenance", priority="P0", source_authority="OPERATION_JOURNAL", route_or_detail="/journal/integrity-verifier", implementation_status="PLANNED", sort_order=731, tags=("journal", "integrity", "crypto")),

        # Batch 013: Security & Sandbox & Secrets (runtime/security/, runtime/sandbox/, runtime/secrets/)
        _p("security.grant_lifecycle", "Security authorization grant lifecycle and expiration manager", "Security / Trust", priority="P0", source_authority="AUTHORIZATION_STORE", route_or_detail="/security/grant-lifecycle", implementation_status="PLANNED", sort_order=732, tags=("security", "grants", "lifecycle")),
        _p("sandbox.execution_boundary", "Active process sandbox isolation boundary monitor", "Execution", priority="P0", source_authority="SANDBOX_MANAGER", route_or_detail="/sandbox/execution-boundary", implementation_status="PLANNED", sort_order=733, tags=("sandbox", "isolation", "boundary")),
        _p("secrets.lease_manager", "Credential secret lease allocation and revocation supervisor", "Security / Trust", priority="P0", source_authority="SECRET_BROKER", route_or_detail="/secrets/lease-manager", implementation_status="PLANNED", sort_order=734, tags=("secrets", "lease", "revocation")),

        # Batch 013: Sync & Updates (runtime/sync/, runtime/updater/)
        _p("sync.state_evaluator", "Release sync candidate state and attestation evaluator", "Distribution / Updates", priority="P0", source_authority="SYNC_SERVICE", route_or_detail="/sync/state-evaluator", implementation_status="PLANNED", sort_order=735, tags=("sync", "state", "evaluator")),
        _p("updater.channel_governor", "Release update channel policy governor and version fence", "Distribution / Updates", priority="P1", source_authority="UPDATE_MANAGER", route_or_detail="/updater/channel-governor", implementation_status="PLANNED", sort_order=736, tags=("updater", "channel", "policy")),

        # Batch 013: MCP & Tools (runtime/mcp/, runtime/tools/)
        _p("mcp.gateway_interceptor", "MCP capability gate execution policy interceptor service", "Infrastructure", priority="P0", source_authority="MCP_GATEWAY", route_or_detail="/mcp/gateway-interceptor", implementation_status="PLANNED", sort_order=737, tags=("mcp", "gateway", "interceptor")),
        _p("tools.invocation_pipeline", "Tool invocation validation and execution pipeline", "Infrastructure", priority="P1", source_authority="TOOL_REGISTRY", route_or_detail="/tools/invocation-pipeline", implementation_status="PLANNED", sort_order=738, tags=("tools", "invocation", "pipeline")),

        # Batch 013: Diagnostics & Bootstrap (runtime/diagnostics/, runtime/bootstrap/)
        _p("diagnostics.health_evaluator", "Diagnostic system health assessment evaluator engine", "Security / Trust", priority="P0", source_authority="RUNTIME_DOCTOR", route_or_detail="/diagnostics/health-evaluator", implementation_status="PLANNED", sort_order=739, tags=("diagnostics", "health", "evaluator")),
        _p("bootstrap.plane_validator", "Three-plane bootstrap dependency and readiness gate validator", "CONRRAD", priority="P0", source_authority="BOOTSTRAP_ENGINE", route_or_detail="/bootstrap/plane-validator", implementation_status="PLANNED", sort_order=740, tags=("bootstrap", "planes", "readiness")),

        # Batch 013: Filesystem & Git & Process & Shell (runtime/filesystem/, runtime/git/, runtime/process/, runtime/shell/)
        _p("filesystem.boundary_guard", "Filesystem sandbox path boundary enforcer service", "Infrastructure", priority="P0", source_authority="FILESYSTEM_SERVICE", route_or_detail="/filesystem/boundary-guard", implementation_status="PLANNED", sort_order=741, tags=("filesystem", "boundary", "sandbox")),
        _p("git.working_tree_monitor", "Git repository working tree dirty state and index monitor", "Infrastructure", priority="P0", source_authority="GIT_SERVICE", route_or_detail="/git/working-tree-monitor", implementation_status="PLANNED", sort_order=742, tags=("git", "working-tree", "status")),
        _p("process.supervisor_service", "Active process tree supervisor and resource monitor", "Execution", priority="P0", source_authority="PROCESS_MANAGER", route_or_detail="/process/supervisor-service", implementation_status="PLANNED", sort_order=743, tags=("process", "supervisor", "monitor")),
        _p("shell.effect_guard", "Classified shell command execution side-effect guard", "Execution", priority="P0", source_authority="SHELL_EXECUTOR", route_or_detail="/shell/effect-guard", implementation_status="PLANNED", sort_order=744, tags=("shell", "effect", "guard")),

        # Batch 013: Compute & Orchestration & Workspace (runtime/compute/, runtime/orchestration/, runtime/workspace/)
        _p("compute.resource_monitor", "Remote and local compute hardware resource capacity monitor", "Infrastructure", priority="P1", source_authority="COMPUTE_DISCOVERY", route_or_detail="/compute/resource-monitor", implementation_status="PLANNED", sort_order=745, tags=("compute", "resource", "capacity")),
        _p("orchestration.scheduler_engine", "Stepwise plan frontier task scheduler engine", "Execution", priority="P0", source_authority="ORCHESTRATION_KERNEL", route_or_detail="/orchestration/scheduler-engine", implementation_status="PLANNED", sort_order=746, tags=("orchestration", "scheduler", "frontier")),
        _p("workspace.isolation_guard", "Active workspace directory isolation and sandbox guard", "Projects / Workspaces", priority="P0", source_authority="WORKSPACE_MANAGER", route_or_detail="/workspace/isolation-guard", implementation_status="PLANNED", sort_order=747, tags=("workspace", "isolation", "sandbox")),

        # Batch 014: Identity & Attestation (runtime/identity/)
        _p("identity.enrollment_audit", "Machine enrollment audit trail and attestation log", "Runtime Identity", priority="P0", source_authority="ENROLLMENT_MANAGER", route_or_detail="/identity/enrollment-audit", implementation_status="PLANNED", sort_order=748, tags=("identity", "enrollment", "audit")),
        _p("identity.key_rotation", "Runtime asymmetric key pair rotation lifecycle", "Runtime Identity", priority="P0", source_authority="RUNTIME_IDENTITY", route_or_detail="/identity/key-rotation", implementation_status="PLANNED", sort_order=749, tags=("identity", "key", "rotation")),

        # Batch 014: Fabric & Mesh (runtime/fabric/)
        _p("fabric.topology_discovery", "Dynamic repository fabric topology discovery service", "Repository Fabric", priority="P0", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/fabric/topology-discovery", implementation_status="PLANNED", sort_order=750, tags=("fabric", "topology", "discovery")),
        _p("fabric.cross_repo_mesh", "Multi-repository fabric synchronization mesh monitor", "Repository Fabric", priority="P0", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/fabric/cross-repo-mesh", implementation_status="PLANNED", sort_order=751, tags=("fabric", "mesh", "sync")),

        # Batch 014: GitHub Integration (runtime/github/)
        _p("github.app_installation", "GitHub App installation state and repository access tokens", "GitHub", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/github/installations", implementation_status="PLANNED", sort_order=752, tags=("github", "app", "installation")),
        _p("github.webhook_receiver", "GitHub event webhook receiver and signature verifier", "GitHub", priority="P1", source_authority="GITHUB_AUTH", route_or_detail="/github/webhook-receiver", implementation_status="PLANNED", sort_order=753, tags=("github", "webhook", "verifier")),

        # Batch 014: Core Engine & Recovery (runtime/core/)
        _p("core.crash_recovery_supervisor", "Automated core crash recovery supervisor and report generator", "Runtime Identity", priority="P0", source_authority="RECOVERY_MANAGER", route_or_detail="/core/crash-recovery", implementation_status="PLANNED", sort_order=754, tags=("core", "recovery", "crash")),
        _p("core.access_audit_matrix", "Critical filesystem and network access verification matrix", "Runtime Identity", priority="P0", source_authority="ACCESS_VERIFIER", route_or_detail="/core/access-matrix", implementation_status="PLANNED", sort_order=755, tags=("core", "access", "verifier")),

        # Batch 014: Execution & Limits (runtime/execution/)
        _p("execution.limits_guard", "Deterministic executor resource and execution limits guard", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/limits-guard", implementation_status="PLANNED", sort_order=756, tags=("execution", "limits", "guard")),
        _p("execution.context_packager", "Model execution context package assembler and serializer", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/context-packager", implementation_status="PLANNED", sort_order=757, tags=("execution", "context", "packager")),
        _p("execution.worker_health_monitor", "Real-time worker thread and process health monitor", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/worker-health", implementation_status="PLANNED", sort_order=758, tags=("execution", "worker", "health")),

        # Batch 014: Capabilities & Intelligence (runtime/capability/, runtime/intelligence/)
        _p("capability.tier_routing_engine", "Model capability tier evaluation and workload routing engine", "Intelligence", priority="P0", source_authority="CAPABILITY_GATE", route_or_detail="/capability/tier-routing", implementation_status="PLANNED", sort_order=759, tags=("capability", "tier", "routing")),
        _p("intelligence.benchmark_runner_service", "Automated model capability benchmark execution runner service", "Intelligence", priority="P0", source_authority="BENCHMARK_RUNNER", route_or_detail="/intelligence/benchmark-runner-service", implementation_status="PLANNED", sort_order=760, tags=("intelligence", "benchmark", "runner")),
        _p("intelligence.delegation_arbiter", "Subagent and model delegation decision arbiter", "Intelligence", priority="P0", source_authority="DELEGATION_ARBITER", route_or_detail="/intelligence/delegation-arbiter", implementation_status="PLANNED", sort_order=761, tags=("intelligence", "delegation", "arbiter")),

        # Batch 014: Accounts & Projects (runtime/accounts/, runtime/projects/)
        _p("accounts.credential_linkage", "Multi-account identity credential binding and linkage monitor", "Accounts / Identities", priority="P0", source_authority="ACCOUNT_REGISTRY", route_or_detail="/accounts/credential-linkage", implementation_status="PLANNED", sort_order=762, tags=("accounts", "credentials", "linkage")),
        _p("projects.lifecycle_supervisor", "Project creation, activation, and archiving lifecycle supervisor", "Projects / Workspaces", priority="P0", source_authority="PROJECT_REGISTRY", route_or_detail="/projects/lifecycle-supervisor", implementation_status="PLANNED", sort_order=763, tags=("projects", "lifecycle", "supervisor")),

        # Batch 014: Workspace & Quotas (runtime/workspace/)
        _p("workspace.quota_enforcer", "Workspace disk space quota and file count boundary enforcer", "Projects / Workspaces", priority="P0", source_authority="WORKSPACE_MANAGER", route_or_detail="/workspace/quota-enforcer", implementation_status="PLANNED", sort_order=764, tags=("workspace", "quota", "limits")),
        _p("workspace.ephemeral_cleaner", "Ephemeral workspace automated TTL cleanup and teardown service", "Projects / Workspaces", priority="P0", source_authority="WORKSPACE_MANAGER", route_or_detail="/workspace/ephemeral-cleaner", implementation_status="PLANNED", sort_order=765, tags=("workspace", "ephemeral", "cleanup")),

        # Batch 014: Browser Automation (runtime/browser/)
        _p("browser.traffic_interceptor", "Managed browser network request and response security interceptor", "Browser", priority="P0", source_authority="BROWSER_INTERCEPTOR", route_or_detail="/browser/traffic-interceptor", implementation_status="PLANNED", sort_order=766, tags=("browser", "network", "interceptor")),
        _p("browser.session_pool_manager", "Browser instance lifecycle pooling and resource manager", "Browser", priority="P0", source_authority="BROWSER_MANAGER", route_or_detail="/browser/session-pool", implementation_status="PLANNED", sort_order=767, tags=("browser", "session", "pool")),

        # Batch 014: Telemetry & Events (runtime/telemetry/, runtime/events/)
        _p("telemetry.redaction_scrubber", "Sensitive token and secret PII telemetry redaction scrubber", "Telemetry", priority="P0", source_authority="TELEMETRY_SCRUBBER", route_or_detail="/telemetry/redaction-scrubber", implementation_status="PLANNED", sort_order=768, tags=("telemetry", "redaction", "pii")),
        _p("telemetry.live_stream_broker", "Real-time websocket telemetry streaming broadcast broker", "Telemetry", priority="P0", source_authority="TELEMETRY_STREAM", route_or_detail="/telemetry/live-stream-broker", implementation_status="PLANNED", sort_order=769, tags=("telemetry", "stream", "websocket")),
        _p("events.dead_letter_queue", "Undelivered event dead-letter queue and retry supervisor", "Telemetry", priority="P0", source_authority="EVENT_BUS", route_or_detail="/events/dead-letter-queue", implementation_status="PLANNED", sort_order=770, tags=("events", "dlq", "retry")),

        # Batch 014: Continuity & Journal & Audit (runtime/continuity/, runtime/journal/)
        _p("continuity.corruption_detector", "Continuity state corruption severity analyzer and recovery trigger", "Continuity", priority="P0", source_authority="CONTINUITY_ENGINE", route_or_detail="/continuity/corruption-detector", implementation_status="PLANNED", sort_order=771, tags=("continuity", "corruption", "detector")),
        _p("continuity.mutation_guard", "Repository mutation contract violation enforcement guard", "Continuity", priority="P0", source_authority="CONTINUITY_MUTATION", route_or_detail="/continuity/mutation-guard", implementation_status="PLANNED", sort_order=772, tags=("continuity", "mutation", "guard")),
        _p("journal.mission_ledger_service", "Durable mission lifecycle transition ledger and audit service", "Project State", priority="P0", source_authority="MISSION_JOURNAL", route_or_detail="/journal/mission-ledger", implementation_status="PLANNED", sort_order=773, tags=("journal", "mission", "ledger")),
        _p("audit.tamper_evident_seal", "Cryptographic evidence seal and hash-chain verification anchor", "Evidence / Provenance", priority="P0", source_authority="AUDIT_STORE", route_or_detail="/audit/tamper-seal", implementation_status="PLANNED", sort_order=774, tags=("audit", "evidence", "crypto")),

        # Batch 014: Security & Sandbox & Secrets (runtime/security/, runtime/sandbox/, runtime/secrets/)
        _p("security.pipeline_orchestrator", "10-step authorized execution pipeline orchestrator and enforcer", "Security / Trust", priority="P0", source_authority="AUTHORIZED_PIPELINE", route_or_detail="/security/pipeline-orchestrator", implementation_status="PLANNED", sort_order=775, tags=("security", "pipeline", "orchestrator")),
        _p("security.tool_registry_enforcer", "ExecutionContext-enforced tool execution registry validator", "Security / Trust", priority="P0", source_authority="SECURE_TOOLS", route_or_detail="/security/tool-registry-enforcer", implementation_status="PLANNED", sort_order=776, tags=("security", "tools", "validator")),
        _p("sandbox.restricted_process_backend", "Bubblewrap restricted subprocess containment backend supervisor", "Execution", priority="P0", source_authority="SANDBOX_MANAGER", route_or_detail="/sandbox/restricted-backend", implementation_status="PLANNED", sort_order=777, tags=("sandbox", "process", "bubblewrap")),
        _p("secrets.crypto_key_store", "Encrypted master key and credential storage backend", "Security / Trust", priority="P0", source_authority="SECRET_BACKEND", route_or_detail="/secrets/crypto-store", implementation_status="PLANNED", sort_order=778, tags=("secrets", "crypto", "store")),

        # Batch 014: Sync & Updates (runtime/sync/, runtime/updater/)
        _p("sync.verification_gate", "Cryptographic release signature and hash verification gate", "Distribution / Updates", priority="P0", source_authority="SYNC_VERIFIER", route_or_detail="/sync/verification-gate", implementation_status="PLANNED", sort_order=779, tags=("sync", "verification", "gate")),
        _p("updater.bundle_extractor", "Release distribution bundle unpacking and checksum verifier", "Distribution / Updates", priority="P0", source_authority="UPDATE_MANAGER", route_or_detail="/updater/bundle-extractor", implementation_status="PLANNED", sort_order=780, tags=("updater", "bundle", "checksum")),

        # Batch 014: MCP & Tools (runtime/mcp/, runtime/tools/)
        _p("mcp.authorization_gate", "MCP tool capability authorization and access decision gate", "Infrastructure", priority="P0", source_authority="MCP_GATEWAY", route_or_detail="/mcp/authorization-gate", implementation_status="PLANNED", sort_order=781, tags=("mcp", "authorization", "gate")),
        _p("tools.capability_sandbox", "Runtime tool execution isolation and privilege boundary sandbox", "Infrastructure", priority="P0", source_authority="TOOL_REGISTRY", route_or_detail="/tools/capability-sandbox", implementation_status="PLANNED", sort_order=782, tags=("tools", "sandbox", "isolation")),

        # Batch 014: Diagnostics & Bootstrap (runtime/diagnostics/, runtime/bootstrap/)
        _p("diagnostics.system_triage", "Automated subsystem failure triage and repair recommendation engine", "Security / Trust", priority="P0", source_authority="RUNTIME_DOCTOR", route_or_detail="/diagnostics/system-triage", implementation_status="PLANNED", sort_order=783, tags=("diagnostics", "triage", "repair")),
        _p("bootstrap.gate_evaluator", "Bootstrap readiness gate dependency evaluation and report service", "CONRRAD", priority="P0", source_authority="BOOTSTRAP_ENGINE", route_or_detail="/bootstrap/gate-evaluator", implementation_status="PLANNED", sort_order=784, tags=("bootstrap", "readiness", "gates")),

        # Batch 014: Filesystem & Git & Process & Shell (runtime/filesystem/, runtime/git/, runtime/process/, runtime/shell/)
        _p("filesystem.path_sanitizer", "Filesystem path traversal prevention and path canonicalization service", "Infrastructure", priority="P0", source_authority="FILESYSTEM_SERVICE", route_or_detail="/filesystem/path-sanitizer", implementation_status="PLANNED", sort_order=785, tags=("filesystem", "sanitizer", "security")),
        _p("git.repo_integrity_checker", "Local git repository object database and reference integrity checker", "Infrastructure", priority="P0", source_authority="GIT_SERVICE", route_or_detail="/git/repo-integrity", implementation_status="PLANNED", sort_order=786, tags=("git", "integrity", "fsck")),
        _p("process.signal_dispatcher", "Subprocess POSIX signal dispatch and graceful termination coordinator", "Execution", priority="P0", source_authority="PROCESS_MANAGER", route_or_detail="/process/signal-dispatcher", implementation_status="PLANNED", sort_order=787, tags=("process", "signals", "termination")),
        _p("shell.command_sanitizer", "Shell invocation argument validation and injection prevention service", "Execution", priority="P0", source_authority="SHELL_EXECUTOR", route_or_detail="/shell/command-sanitizer", implementation_status="PLANNED", sort_order=788, tags=("shell", "sanitizer", "injection")),

        # Batch 014: Compute & Orchestration & Platform (runtime/compute/, runtime/orchestration/, runtime/platform/)
        _p("compute.remote_session_pool", "Remote compute provider session pool allocation supervisor", "Infrastructure", priority="P0", source_authority="COMPUTE_MANAGER", route_or_detail="/compute/remote-session-pool", implementation_status="PLANNED", sort_order=789, tags=("compute", "session", "pool")),
        _p("orchestration.frontier_scheduler", "Dynamic task dependency frontier schedule and concurrency limiter", "Execution", priority="P0", source_authority="ORCHESTRATION_KERNEL", route_or_detail="/orchestration/frontier-scheduler", implementation_status="PLANNED", sort_order=790, tags=("orchestration", "frontier", "scheduler")),
        _p("platform.wsl2_bridge", "WSL2 environment interoperability and filesystem bridge", "Infrastructure", priority="P1", source_authority="PLATFORM_ADAPTER", route_or_detail="/platform/wsl2-bridge", implementation_status="PLANNED", sort_order=791, tags=("platform", "wsl2", "bridge")),
        _p("platform.linux_kernel_monitor", "Linux OS cgroup, namespace, and resource boundary monitor", "Infrastructure", priority="P0", source_authority="PLATFORM_ADAPTER", route_or_detail="/platform/linux-kernel-monitor", implementation_status="PLANNED", sort_order=792, tags=("platform", "linux", "cgroups")),

        # Batch 015: Admin Server Infrastructure (runtime/admin/server.py)
        _p("admin.server_lifecycle", "Admin HTTP server lifecycle and dual-stack binding supervisor", "Control Center", priority="P0", source_authority="ADMIN_SERVER", route_or_detail="/admin/server-lifecycle", implementation_status="PLANNED", sort_order=793, tags=("admin", "server", "lifecycle")),
        _p("admin.request_handler", "Admin HTTP request dispatch and security header enforcement handler", "Control Center", priority="P0", source_authority="ADMIN_SERVER", route_or_detail="/admin/request-handler", implementation_status="PLANNED", sort_order=794, tags=("admin", "request", "handler")),
        _p("admin.loopback_binding", "Dual-stack IPv4/IPv6 loopback server socket binding and port selection", "Control Center", priority="P0", source_authority="ADMIN_PORT", route_or_detail="/admin/loopback-binding", implementation_status="PLANNED", sort_order=795, tags=("admin", "loopback", "port")),

        # Batch 015: Admin Data Transfer Objects (runtime/admin/dto.py)
        _p("admin.canonical_state_dto", "Canonical operational state projection data transfer object", "Control Center", priority="P0", source_authority="CANONICAL_STATE_DTO", route_or_detail="/admin/dto/canonical-state", implementation_status="PLANNED", sort_order=796, tags=("admin", "dto", "canonical")),
        _p("admin.continuity_dto", "Continuity timeline and checkpoint data transfer object", "Control Center", priority="P0", source_authority="CONTINUITY_DTO", route_or_detail="/admin/dto/continuity", implementation_status="PLANNED", sort_order=797, tags=("admin", "dto", "continuity")),
        _p("admin.mission_task_dto", "Mission, task, next-action, and blocker projection data transfer objects", "Control Center", priority="P0", source_authority="STATE_DTO", route_or_detail="/admin/dto/mission-task", implementation_status="PLANNED", sort_order=798, tags=("admin", "dto", "mission", "task")),
        _p("admin.worker_summary_dto", "L2 worker summary and operational snapshot data transfer object", "Execution", priority="P0", source_authority="WORKER_DTO", route_or_detail="/admin/dto/worker-summary", implementation_status="PLANNED", sort_order=799, tags=("admin", "dto", "worker", "summary")),

        # Batch 015: Bootstrap CONRRAD Integration (runtime/bootstrap/conrrad.py)
        _p("bootstrap.conrrad_dependency_matrix", "CONRRAD mandatory dependency matrix normalization and completeness evaluator", "CONRRAD", priority="P0", source_authority="CONRRAD_DEPENDENCY", route_or_detail="/bootstrap/conrrad-matrix", implementation_status="PLANNED", sort_order=800, tags=("bootstrap", "conrrad", "dependencies")),
        _p("bootstrap.conrrad_registry_normalizer", "CONRRAD dependency registry record normalizer and validator", "CONRRAD", priority="P0", source_authority="CONRRAD_DEPENDENCY", route_or_detail="/bootstrap/conrrad-normalizer", implementation_status="PLANNED", sort_order=801, tags=("bootstrap", "conrrad", "normalizer")),

        # Batch 015: Bootstrap Three-Plane Lifecycle (runtime/bootstrap/planes.py)
        _p("bootstrap.three_plane_resolver", "Three-plane bootstrap gate resolution lifecycle orchestrator", "CONRRAD", priority="P0", source_authority="THREE_PLANE_BOOTSTRAP", route_or_detail="/bootstrap/three-plane-resolver", implementation_status="PLANNED", sort_order=802, tags=("bootstrap", "three_plane", "resolver")),
        _p("bootstrap.gate_chain_evaluator", "Sequential bootstrap gate dependency chain evaluation engine", "CONRRAD", priority="P0", source_authority="THREE_PLANE_BOOTSTRAP", route_or_detail="/bootstrap/gate-chain", implementation_status="PLANNED", sort_order=803, tags=("bootstrap", "gates", "chain")),

        # Batch 015: Bootstrap Report (runtime/bootstrap/report.py)
        _p("bootstrap.report_formatter", "Bootstrap verification report and component inventory formatter", "CONRRAD", priority="P0", source_authority="BOOTSTRAP_REPORT", route_or_detail="/bootstrap/report-formatter", implementation_status="PLANNED", sort_order=804, tags=("bootstrap", "report", "formatter")),
        _p("bootstrap.component_inventory_report", "Bootstrap subsystem component inventory discovery and report projection", "Control Center", priority="P0", source_authority="BOOTSTRAP_REPORT", route_or_detail="/bootstrap/component-inventory", implementation_status="PLANNED", sort_order=805, tags=("bootstrap", "inventory", "report")),

        # Batch 015: API Bridge Authentication (runtime/api/bridge.py)
        _p("api.bridge_auth_gate", "ChatGPT/Luna external bridge API bearer token authentication gate", "Security / Trust", priority="P0", source_authority="BRIDGE_AUTH", route_or_detail="/api/v1/bridge/auth", implementation_status="PLANNED", sort_order=806, tags=("bridge", "authentication", "gate")),
        _p("api.bridge_dispatch", "External bridge API route dispatch and task lifecycle coordinator", "Communication", priority="P0", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge/dispatch", implementation_status="PLANNED", sort_order=807, tags=("bridge", "dispatch", "routing")),

        # Batch 015: Telemetry Domain Taxonomy (runtime/telemetry/telemetry.py)
        _p("telemetry.envelope_schema", "Canonical telemetry event envelope record schema and constructor", "Telemetry", priority="P0", source_authority="TELEMETRY_SCHEMA", route_or_detail="/telemetry/envelope-schema", implementation_status="PLANNED", sort_order=808, tags=("telemetry", "envelope", "schema")),
        _p("telemetry.domain_taxonomy", "Runtime telemetry domain classification taxonomy and routing classes", "Telemetry", priority="P0", source_authority="TELEMETRY_TAXONOMY", route_or_detail="/telemetry/domain-taxonomy", implementation_status="PLANNED", sort_order=809, tags=("telemetry", "domain", "taxonomy")),
        _p("telemetry.execution_mode_classifier", "Telemetry execution mode and routing class taxonomy classifier", "Telemetry", priority="P0", source_authority="TELEMETRY_SCHEMA", route_or_detail="/telemetry/execution-mode", implementation_status="PLANNED", sort_order=810, tags=("telemetry", "execution", "mode")),

        # Batch 015: Execution Receipt Store (runtime/execution/receipt.py)
        _p("execution.receipt_ledger", "Durable execution receipt cryptographic ledger and integrity store", "Evidence / Provenance", priority="P0", source_authority="RECEIPT_STORE", route_or_detail="/execution/receipt-ledger", implementation_status="PLANNED", sort_order=811, tags=("execution", "receipt", "ledger")),

        # Batch 015: Execution Policy Engine (runtime/execution/policy.py)
        _p("execution.policy_engine", "Task execution domain boundary and resource limit policy evaluator", "Execution", priority="P0", source_authority="EXECUTION_POLICY", route_or_detail="/execution/policy-engine", implementation_status="PLANNED", sort_order=812, tags=("execution", "policy", "limits")),

        # Batch 015: Intelligence Taxonomy (runtime/intelligence/taxonomy.py)
        _p("intelligence.taxonomy_service", "Local intelligence capability taxonomy classification service", "Intelligence", priority="P0", source_authority="INTELLIGENCE_TAXONOMY", route_or_detail="/intelligence/taxonomy-service", implementation_status="PLANNED", sort_order=813, tags=("intelligence", "taxonomy", "classifier")),

        # Batch 015: Intelligence Evidence Builder (runtime/intelligence/evidence_builder.py)
        _p("intelligence.evidence_builder_service", "Evaluation evidence artifact and scorecard provenance builder service", "Intelligence", priority="P0", source_authority="EVIDENCE_BUILDER", route_or_detail="/intelligence/evidence-builder-service", implementation_status="PLANNED", sort_order=814, tags=("intelligence", "evidence", "artifacts")),

        # Batch 015: Execution Validator (runtime/execution/validator.py)
        _p("execution.output_validator", "Model output structural conformance and policy compliance validator", "Execution", priority="P0", source_authority="OUTPUT_VALIDATOR", route_or_detail="/execution/output-validator", implementation_status="PLANNED", sort_order=815, tags=("execution", "output", "validation")),

        # Batch 015: Execution Selector (runtime/execution/selector.py)
        _p("execution.model_selector_service", "Dynamic capability-aware model executor selection and routing service", "Execution", priority="P0", source_authority="EXECUTOR_SELECTOR", route_or_detail="/execution/model-selector", implementation_status="PLANNED", sort_order=816, tags=("execution", "selector", "model")),

        # Batch 015: Admin GitHub Manager (runtime/admin/github.py)
        _p("admin.github_auth_manager", "GitHub credential lifecycle and device flow authorization manager", "GitHub", priority="P0", source_authority="GITHUB_AUTH_MANAGER", route_or_detail="/admin/github-manager", implementation_status="PLANNED", sort_order=817, tags=("admin", "github", "auth")),
        _p("admin.github_credential_state", "GitHub OAuth token persistence and validation state machine", "GitHub", priority="P0", source_authority="GITHUB_AUTH_MANAGER", route_or_detail="/admin/github-credential-state", implementation_status="PLANNED", sort_order=818, tags=("admin", "github", "credential")),

        # Batch 015: Admin Middleware (runtime/admin/middleware.py)
        _p("admin.middleware_guard", "Admin request authentication and authorization middleware enforcer", "Security / Trust", priority="P0", source_authority="ADMIN_MIDDLEWARE", route_or_detail="/admin/middleware-guard", implementation_status="PLANNED", sort_order=819, tags=("admin", "middleware", "auth")),
        _p("admin.onboarding_revocation", "Onboarding session scope revocation and upgrade controller", "Security / Trust", priority="P0", source_authority="ADMIN_MIDDLEWARE", route_or_detail="/admin/onboarding-revocation", implementation_status="PLANNED", sort_order=820, tags=("admin", "onboarding", "revocation")),

        # Batch 015: Admin CSRF (runtime/admin/csrf.py)
        _p("admin.csrf_validator", "CSRF token generation, rotation, and form submission validation service", "Security / Trust", priority="P0", source_authority="ADMIN_CSRF", route_or_detail="/admin/csrf-validator", implementation_status="PLANNED", sort_order=821, tags=("admin", "csrf", "validation")),

        # Batch 015: Execution Worker Manager (runtime/execution/worker.py)
        _p("execution.worker_registry", "Worker capability registration, heartbeat tracking, and drain lifecycle", "Execution", priority="P0", source_authority="WORKER_REGISTRY", route_or_detail="/execution/worker-registry", implementation_status="PLANNED", sort_order=822, tags=("execution", "worker", "registry")),

        # Batch 015: Execution Manager Queue (runtime/execution/manager.py)
        _p("execution.task_queue", "Task execution queue scheduling, prioritization, and lifecycle state machine", "Execution", priority="P0", source_authority="EXECUTION_MANAGER", route_or_detail="/execution/task-queue", implementation_status="PLANNED", sort_order=823, tags=("execution", "task", "queue")),

        # Batch 015: Continuity State Resolver (runtime/continuity/state.py)
        _p("continuity.state_machine", "Continuity bootstrap state resolver and lifecycle transition engine", "Continuity", priority="P0", source_authority="CONTINUITY_STATE", route_or_detail="/continuity/state-machine", implementation_status="PLANNED", sort_order=824, tags=("continuity", "state", "machine")),

        # Batch 015: Continuity Operational Provider (runtime/continuity/operational.py)
        _p("continuity.operational_repo_provider", "Operational repository git clone, checkout, and synchronization provider", "Continuity", priority="P0", source_authority="OPERATIONAL_PROVIDER", route_or_detail="/continuity/operational-repo-provider", implementation_status="PLANNED", sort_order=825, tags=("continuity", "operational", "repository")),

        # Batch 015: Fabric GitHub Adapter (runtime/fabric/github_adapter.py)
        _p("fabric.github_adapter_service", "GitHub REST API to repository fabric resource adaptation and mapping service", "Repository Fabric", priority="P0", source_authority="FABRIC_GITHUB_ADAPTER", route_or_detail="/fabric/github-adapter-service", implementation_status="PLANNED", sort_order=826, tags=("fabric", "github", "adapter")),

        # Batch 015: GitHub Client (runtime/github/client.py)
        _p("github.authenticated_client", "Authenticated GitHub REST API client with rate-limit and retry governance", "GitHub", priority="P0", source_authority="GITHUB_CLIENT", route_or_detail="/github/authenticated-client", implementation_status="PLANNED", sort_order=827, tags=("github", "client", "api")),

        # Batch 015: GitHub Discovery (runtime/github/discovery.py)
        _p("github.org_discovery_service", "GitHub organization, repository, and principal topology discovery service", "GitHub", priority="P0", source_authority="GITHUB_DISCOVERY_SERVICE", route_or_detail="/github/org-discovery", implementation_status="PLANNED", sort_order=828, tags=("github", "discovery", "organization")),

        # Batch 015: Platform Base Adapter (runtime/platform/base.py)
        _p("platform.base_adapter", "Cross-platform OS host abstraction and environment detection base adapter", "Infrastructure", priority="P0", source_authority="PLATFORM_BASE", route_or_detail="/platform/base-adapter", implementation_status="PLANNED", sort_order=829, tags=("platform", "base", "abstraction")),

        # Batch 015: MCP Tools Registry (runtime/mcp/tools.py)
        _p("mcp.tool_definitions", "MCP tool definition schema and capability metadata registration", "Infrastructure", priority="P0", source_authority="MCP_TOOLS", route_or_detail="/mcp/tool-definitions", implementation_status="PLANNED", sort_order=830, tags=("mcp", "tools", "definitions")),

        # Batch 015: Control Center Template Engine (runtime/admin/templates_cc.py)
        _p("admin.control_center_renderer", "Control Center single-page application HTML template renderer", "Control Center", priority="P0", source_authority="CC_RENDERER", route_or_detail="/admin/control-center-renderer", implementation_status="PLANNED", sort_order=831, tags=("admin", "renderer", "spa")),

        # Batch 015: Admin Templates (runtime/admin/templates.py)
        _p("admin.template_engine", "Admin panel page template composition and rendering engine", "Control Center", priority="P0", source_authority="ADMIN_TEMPLATES", route_or_detail="/admin/template-engine", implementation_status="PLANNED", sort_order=832, tags=("admin", "templates", "rendering")),

        # Batch 015: Compute Registry (runtime/compute/registry.py)
        _p("compute.capability_registry_service", "Compute hardware capability discovery and registration service", "Infrastructure", priority="P0", source_authority="COMPUTE_REGISTRY", route_or_detail="/compute/capability-registry-service", implementation_status="PLANNED", sort_order=833, tags=("compute", "capability", "registry")),

        # Batch 015: Tools Builtins (runtime/tools/builtins.py)
        _p("tools.builtin_executor", "Built-in filesystem, shell, and git tool capability-gated executor", "Execution", priority="P0", source_authority="BUILTIN_TOOLS", route_or_detail="/tools/builtin-executor", implementation_status="PLANNED", sort_order=834, tags=("tools", "builtin", "executor")),

        # Batch 015: Continuity Bootstrap (runtime/continuity/bootstrap.py)
        _p("continuity.bootstrap_provider", "Continuity bootstrap initialization and state seeding provider", "Continuity", priority="P0", source_authority="CONTINUITY_BOOTSTRAP", route_or_detail="/continuity/bootstrap-provider", implementation_status="PLANNED", sort_order=835, tags=("continuity", "bootstrap", "seeding")),

        # Batch 015: Continuity Models (runtime/continuity/models.py)
        _p("continuity.event_model", "Continuity event classification and lifecycle transition record model", "Continuity", priority="P0", source_authority="CONTINUITY_MODEL", route_or_detail="/continuity/event-model", implementation_status="PLANNED", sort_order=836, tags=("continuity", "event", "model")),

        # Batch 016: Core Runtime Engine State Machine (runtime/core/engine.py)
        _p("core.runtime_state_machine", "Runtime lifecycle state machine transitions and readiness supervisor", "Infrastructure", priority="P0", source_authority="RUNTIME_ENGINE", route_or_detail="/core/state-machine", implementation_status="PLANNED", sort_order=837, tags=("core", "state", "machine")),

        # Batch 016: Core Runtime Config (runtime/core/config.py)
        _p("core.runtime_config", "Durable runtime configuration loader and validation service", "Infrastructure", priority="P0", source_authority="RUNTIME_CONFIG", route_or_detail="/core/config", implementation_status="PLANNED", sort_order=838, tags=("core", "config", "loader")),

        # Batch 016: Core Inventory Discovery (runtime/core/inventory.py)
        _p("core.inventory_discovery", "Subsystem component inventory discovery and registration service", "Infrastructure", priority="P0", source_authority="INVENTORY_DISCOVERY", route_or_detail="/core/inventory-discovery", implementation_status="PLANNED", sort_order=839, tags=("core", "inventory", "discovery")),

        # Batch 016: Core Generation Identity (runtime/core/generation.py)
        _p("core.generation_identity", "Runtime generation monotonic identity and stale-generation fence", "Runtime Identity", priority="P0", source_authority="RUNTIME_GENERATION", route_or_detail="/core/generation-identity", implementation_status="PLANNED", sort_order=840, tags=("core", "generation", "fence")),

        # Batch 016: Execution Model Hierarchy (runtime/execution/models.py)
        _p("execution.task_model", "Task lifecycle model with context, status, and failure classification", "Execution", priority="P0", source_authority="EXECUTION_MODELS", route_or_detail="/execution/task-model", implementation_status="PLANNED", sort_order=841, tags=("execution", "task", "model")),
        _p("execution.execution_result_model", "Execution result and detail payload canonical data model", "Execution", priority="P0", source_authority="EXECUTION_MODELS", route_or_detail="/execution/result-model", implementation_status="PLANNED", sort_order=842, tags=("execution", "result", "model")),
        _p("execution.execution_status_taxonomy", "Execution status and failure reason enumeration taxonomy", "Execution", priority="P0", source_authority="EXECUTION_MODELS", route_or_detail="/execution/status-taxonomy", implementation_status="PLANNED", sort_order=843, tags=("execution", "status", "taxonomy")),
        _p("execution.model_definition", "Model definition schema with provider, context window, and cost metadata", "Execution", priority="P0", source_authority="EXECUTION_MODELS", route_or_detail="/execution/model-definition", implementation_status="PLANNED", sort_order=844, tags=("execution", "model", "definition")),
        _p("execution.model_capability_binding", "Model-to-capability binding and eligibility resolution record", "Execution", priority="P0", source_authority="EXECUTION_MODELS", route_or_detail="/execution/model-capability-binding", implementation_status="PLANNED", sort_order=845, tags=("execution", "model", "binding")),
        _p("execution.hardware_profile", "Execution hardware profile detection and resource constraint record", "Infrastructure", priority="P0", source_authority="EXECUTION_MODELS", route_or_detail="/execution/hardware-profile", implementation_status="PLANNED", sort_order=846, tags=("execution", "hardware", "profile")),
        _p("execution.model_performance_profile", "Model performance profile with latency, throughput, and cost metrics", "Intelligence", priority="P0", source_authority="EXECUTION_MODELS", route_or_detail="/execution/model-performance", implementation_status="PLANNED", sort_order=847, tags=("execution", "performance", "metrics")),

        # Batch 016: Execution Orchestrator (runtime/execution/executor.py)
        _p("execution.tool_invocation_model", "Tool invocation request and result payload canonical model", "Execution", priority="P0", source_authority="EXECUTION_ORCHESTRATOR", route_or_detail="/execution/tool-invocation", implementation_status="PLANNED", sort_order=848, tags=("execution", "tool", "invocation")),

        # Batch 016: Execution Capability Definition (runtime/execution/capability.py)
        _p("execution.capability_definition", "Executor capability definition schema and tier classification", "Execution", priority="P0", source_authority="CAPABILITY_REGISTRY", route_or_detail="/execution/capability-definition", implementation_status="PLANNED", sort_order=849, tags=("execution", "capability", "schema")),

        # Batch 016: Execution Model Registry (runtime/execution/registry.py)
        _p("execution.model_registry_service", "Model registry lifecycle with recovery attestation and consistency gate", "Execution", priority="P0", source_authority="MODEL_REGISTRY", route_or_detail="/execution/model-registry-service", implementation_status="PLANNED", sort_order=850, tags=("execution", "model", "registry")),

        # Batch 016: Security Authorization Store (runtime/security/authorization_store.py)
        _p("security.grant_store", "Authorization grant persistence store and revocation lifecycle manager", "Security / Trust", priority="P0", source_authority="AUTH_STORE", route_or_detail="/security/grant-store", implementation_status="PLANNED", sort_order=851, tags=("security", "grants", "store")),
        _p("security.grant_model", "Authorization grant record model with scope, expiry, and principal binding", "Security / Trust", priority="P0", source_authority="AUTH_STORE", route_or_detail="/security/grant-model", implementation_status="PLANNED", sort_order=852, tags=("security", "grant", "model")),

        # Batch 016: Security Context Guard (runtime/security/context_guard.py)
        _p("security.context_guard_engine", "Context access boundary enforcement and violation detection engine", "Security / Trust", priority="P0", source_authority="CONTEXT_GUARD", route_or_detail="/security/context-guard-engine", implementation_status="PLANNED", sort_order=853, tags=("security", "context", "guard")),

        # Batch 016: Security Active Context (runtime/security/active_context.py)
        _p("security.active_context_lifecycle", "Active security context lifecycle creation, scoping, and teardown manager", "Security / Trust", priority="P0", source_authority="ACTIVE_CONTEXT", route_or_detail="/security/active-context-lifecycle", implementation_status="PLANNED", sort_order=854, tags=("security", "context", "lifecycle")),

        # Batch 016: Session Lease Model (runtime/session/lease.py)
        _p("session.lease_model", "Session lease temporal model with TTL, renewal, and expiry tracking", "Communication", priority="P0", source_authority="SESSION_LEASE", route_or_detail="/session/lease-model", implementation_status="PLANNED", sort_order=855, tags=("session", "lease", "model")),
        _p("session.status_taxonomy", "Session status enumeration taxonomy and lifecycle transition rules", "Communication", priority="P0", source_authority="SESSION_LEASE", route_or_detail="/session/status-taxonomy", implementation_status="PLANNED", sort_order=856, tags=("session", "status", "taxonomy")),

        # Batch 016: Session Lifecycle Manager (runtime/session/manager.py)
        _p("session.lifecycle_manager", "Session lifecycle orchestrator with create, renew, expire, and destroy", "Communication", priority="P0", source_authority="SESSION_MANAGER", route_or_detail="/session/lifecycle-manager", implementation_status="PLANNED", sort_order=857, tags=("session", "lifecycle", "manager")),

        # Batch 016: Continuity Reconciler (runtime/continuity/reconciler.py)
        _p("continuity.reconciler_engine", "Operational state reconciler and drift detection engine", "Continuity", priority="P0", source_authority="CONTINUITY_RECONCILER", route_or_detail="/continuity/reconciler-engine", implementation_status="PLANNED", sort_order=858, tags=("continuity", "reconciler", "drift")),

        # Batch 016: Continuity Event Taxonomy (runtime/continuity/events.py)
        _p("continuity.event_type_taxonomy", "Continuity event type classification enumeration and severity model", "Continuity", priority="P0", source_authority="CONTINUITY_EVENTS", route_or_detail="/continuity/event-taxonomy", implementation_status="PLANNED", sort_order=859, tags=("continuity", "events", "taxonomy")),

        # Batch 016: Sync Service Engine (runtime/sync/service.py)
        _p("sync.service_engine", "Distribution sync orchestration service with stage/verify/activate lifecycle", "Distribution / Updates", priority="P0", source_authority="SYNC_SERVICE", route_or_detail="/sync/service-engine", implementation_status="PLANNED", sort_order=860, tags=("sync", "service", "lifecycle")),

        # Batch 016: Sync Models (runtime/sync/models.py)
        _p("sync.candidate_identity_model", "Sync candidate identity fingerprint and provenance verification model", "Distribution / Updates", priority="P0", source_authority="SYNC_MODELS", route_or_detail="/sync/candidate-identity-model", implementation_status="PLANNED", sort_order=861, tags=("sync", "candidate", "identity")),
        _p("sync.sync_state_machine", "Sync state machine with idle/staging/verifying/activating transitions", "Distribution / Updates", priority="P0", source_authority="SYNC_MODELS", route_or_detail="/sync/state-machine", implementation_status="PLANNED", sort_order=862, tags=("sync", "state", "machine")),
        _p("sync.sync_result_model", "Sync operation result canonical model with success/failure/rollback classification", "Distribution / Updates", priority="P0", source_authority="SYNC_MODELS", route_or_detail="/sync/result-model", implementation_status="PLANNED", sort_order=863, tags=("sync", "result", "model")),

        # Batch 016: Intelligence Capability Tier Taxonomy (runtime/intelligence/models.py)
        _p("intelligence.capability_tier_taxonomy", "Local intelligence capability tier classification and routing taxonomy", "Intelligence", priority="P0", source_authority="INTELLIGENCE_MODELS", route_or_detail="/intelligence/capability-tier-taxonomy", implementation_status="PLANNED", sort_order=864, tags=("intelligence", "capability", "tier")),
        _p("intelligence.delegation_decision_model", "Delegation decision model with local/remote/hybrid routing classification", "Intelligence", priority="P0", source_authority="INTELLIGENCE_MODELS", route_or_detail="/intelligence/delegation-decision", implementation_status="PLANNED", sort_order=865, tags=("intelligence", "delegation", "decision")),
        _p("intelligence.certification_status_model", "Model certification status lifecycle and compliance record model", "Intelligence", priority="P0", source_authority="INTELLIGENCE_MODELS", route_or_detail="/intelligence/certification-status", implementation_status="PLANNED", sort_order=866, tags=("intelligence", "certification", "status")),
        _p("intelligence.capability_assessment", "Capability assessment request/response protocol and scoring model", "Intelligence", priority="P0", source_authority="INTELLIGENCE_MODELS", route_or_detail="/intelligence/capability-assessment", implementation_status="PLANNED", sort_order=867, tags=("intelligence", "assessment", "protocol")),

        # Batch 016: Intelligence Grading (runtime/intelligence/grading.py)
        _p("intelligence.grading_result_model", "Model grading result record with score, confidence, and pass/fail determination", "Intelligence", priority="P0", source_authority="GRADING_ENGINE", route_or_detail="/intelligence/grading-result", implementation_status="PLANNED", sort_order=868, tags=("intelligence", "grading", "result")),

        # Batch 016: Intelligence Benchmark Store (runtime/intelligence/benchmark_store.py)
        _p("intelligence.benchmark_store_service", "Benchmark result persistence store and historical comparison service", "Intelligence", priority="P0", source_authority="BENCHMARK_STORE", route_or_detail="/intelligence/benchmark-store-service", implementation_status="PLANNED", sort_order=869, tags=("intelligence", "benchmark", "store")),

        # Batch 016: Admin Sync UI (runtime/admin/sync_ui.py)
        _p("admin.sync_ui_injector", "SYNC control surface injection and state-driven button rendering service", "Control Center", priority="P0", source_authority="SYNC_UI", route_or_detail="/admin/sync-ui-injector", implementation_status="PLANNED", sort_order=870, tags=("admin", "sync", "ui")),

        # Batch 016: Core Access Verifier Detail (runtime/core/access_verifier.py)
        _p("core.critical_access_report", "Critical access verification result and compliance summary report model", "Security / Trust", priority="P0", source_authority="ACCESS_VERIFIER", route_or_detail="/core/critical-access-report", implementation_status="PLANNED", sort_order=871, tags=("core", "access", "report")),

        # Batch 016: Admin Audit Entry Model (runtime/admin/audit.py)
        _p("admin.audit_persistence", "Admin audit log file persistence and rotation lifecycle manager", "Evidence / Provenance", priority="P0", source_authority="ADMIN_AUDIT", route_or_detail="/admin/audit-persistence", implementation_status="PLANNED", sort_order=872, tags=("admin", "audit", "persistence")),
    ]
    return ProjectionRegistry(items)


DEFAULT_PROJECTION_REGISTRY = default_projection_registry()

@dataclass(frozen=True)
class NavigationItem:
    """Canonical sidebar navigation item backed by a projection contract."""

    section: str
    label: str
    icon: str
    path: str
    projection_id: Optional[str] = None
    availability: str = "ACTIVE"

    def __post_init__(self) -> None:
        if self.availability not in {"ACTIVE", "ALIAS", "PLANNED"}:
            raise ValueError(f"Unsupported navigation availability: {self.availability}")
        if not self.path.startswith("/"):
            raise ValueError("Navigation paths must be absolute")
        if self.availability in {"ACTIVE", "ALIAS"}:
            if not self.projection_id:
                raise ValueError("Active navigation items require projection_id")
            if DEFAULT_PROJECTION_REGISTRY.get(self.projection_id) is None:
                raise ValueError(
                    f"Navigation projection_id is not registered: {self.projection_id}"
                )


DEFAULT_NAVIGATION_ITEMS: Tuple[NavigationItem, ...] = (
    NavigationItem("OVERVIEW", "Dashboard", "⬡", "/", "control.top_level_state"),
    NavigationItem("UNIVERSE", "Organization", "❖", "/universe/organization", "universe.organization"),
    NavigationItem("UNIVERSE", "Projects", "◫", "/universe/projects", "universe.projects"),
    NavigationItem("UNIVERSE", "Repositories", "⊙", "/universe/repositories", "universe.repositories"),
    NavigationItem("UNIVERSE", "Resources", "◈", "/universe/resources", "universe.resources"),
    NavigationItem("UNIVERSE", "Dependencies", "⋈", "/universe/dependencies", "fabric.connection", "PLANNED"),

    NavigationItem("EXECUTION", "Missions", "🎯", "/execution/missions", "execution.missions"),
    NavigationItem("EXECUTION", "Tasks", "✓", "/execution/tasks", "execution.tasks"),
    NavigationItem("EXECUTION", "Workers", "⚙", "/execution/workers", "execution.workers"),
    NavigationItem("EXECUTION", "Executions", "▶", "/execution/executions", "execution.execution_runs"),
    NavigationItem("EXECUTION", "Workspaces", "📁", "/execution/workspaces", "execution.workspaces", "PLANNED"),
    NavigationItem("EXECUTION", "Results", "📊", "/execution/results", "execution.results", "PLANNED"),

    NavigationItem("INTELLIGENCE", "Models", "🧠", "/models", "intelligence.models", "ALIAS"),
    NavigationItem("INTELLIGENCE", "Capabilities", "⚡", "/intelligence/capabilities", "intelligence.capabilities"),
    NavigationItem("INTELLIGENCE", "Executors", "🛠", "/intelligence/executors", "intelligence.executors", "PLANNED"),
    NavigationItem("INTELLIGENCE", "Performance", "📈", "/intelligence/performance", "intelligence.performance", "PLANNED"),

    NavigationItem("INFRASTRUCTURE", "Runtime", "🖥", "/infrastructure/runtime", "infrastructure.runtime"),
    NavigationItem("INFRASTRUCTURE", "GitHub", "🐙", "/infrastructure/github", "infrastructure.github", "PLANNED"),
    NavigationItem("INFRASTRUCTURE", "Fabric", "☁", "/infrastructure/fabric", "infrastructure.fabric", "PLANNED"),
    NavigationItem("INFRASTRUCTURE", "MCP", "🔌", "/infrastructure/mcp", "infrastructure.mcp", "PLANNED"),
    NavigationItem("INFRASTRUCTURE", "Azure", "🔷", "/infrastructure/azure", "infrastructure.azure", "PLANNED"),

    NavigationItem("TELEMETRY", "Live Stream", "📡", "/telemetry/live", "telemetry.live"),
    NavigationItem("TELEMETRY", "Timeline", "⏱", "/telemetry/timeline", "telemetry.timeline"),

    NavigationItem("CONTINUITY", "Timeline", "⏱", "/continuity/timeline", "continuity.status"),
    NavigationItem("CONTINUITY", "Mission", "🎯", "/continuity/mission", "project.current_mission", "PLANNED"),
    NavigationItem("CONTINUITY", "Task", "✓", "/continuity/task", "project.current_task", "PLANNED"),
    NavigationItem("CONTINUITY", "Next action", "⏭", "/continuity/next", "project.next_action", "PLANNED"),
    NavigationItem("CONTINUITY", "Blockers", "🛑", "/continuity/blockers", "project.blockers", "PLANNED"),
    NavigationItem("CONTINUITY", "Recovery", "⚕", "/continuity/recovery", "continuity.recovery", "PLANNED"),

    NavigationItem("AUDIT", "Events", "📋", "/audit/events", "audit.events"),
    NavigationItem("AUDIT", "Provenance", "🔍", "/audit/provenance", "evidence.provenance"),
    NavigationItem("AUDIT", "Evidence", "🛡", "/audit/evidence", "evidence.index"),
    NavigationItem("AUDIT", "Changes", "📝", "/audit/changes", "evidence.provenance", "PLANNED"),
)


def audit_navigation_contract(
    navigation_items: Iterable[NavigationItem],
    get_routes: Iterable[str],
    *,
    registry: ProjectionRegistry = DEFAULT_PROJECTION_REGISTRY,
) -> Dict[str, object]:
    """Return a read-only navigation integrity observation.

    The control-center registry intentionally contains PLANNED and BLOCKED
    projections which are not operator destinations.  This audit therefore
    checks only ACTIVE and ALIAS navigation entries for a registered projection
    and a concrete GET handler.  It never upgrades a projection's truth or
    implementation status; it merely exposes the currently wired contract.
    """
    items = tuple(navigation_items)
    routes = set(get_routes)
    active_items = tuple(
        item for item in items if item.availability in {"ACTIVE", "ALIAS"}
    )

    invalid_projection_ids = sorted(
        item.projection_id or item.label
        for item in active_items
        if not item.projection_id or registry.get(item.projection_id) is None
    )
    dead_links = sorted(item.path for item in active_items if item.path not in routes)
    stale_aliases = sorted(
        item.label
        for item in active_items
        if item.availability == "ALIAS"
        and (
            registry.get(item.projection_id or "") is None
            or registry.get(item.projection_id or "").route_or_detail != item.path
        )
    )
    duplicate_destinations = sorted(
        path for path in {item.path for item in items}
        if sum(item.path == path for item in items) > 1
    )
    false_online_declarations = sorted(
        item.projection_id or item.label
        for item in active_items
        if (projection := registry.get(item.projection_id or ""))
        and projection.current_status in {"ONLINE", "LIVE"}
        and projection.truth_class != "FACT"
    )

    failures = (
        invalid_projection_ids
        + dead_links
        + stale_aliases
        + duplicate_destinations
        + false_online_declarations
    )
    return {
        "status": "VALID" if not failures else "INVALID",
        "registered_projection_ids": {
            "valid": len(active_items) - len(invalid_projection_ids),
            "total": len(active_items),
        },
        "active_or_alias_destinations": len(active_items),
        "planned_destinations": sum(item.availability == "PLANNED" for item in items),
        "dead_links": dead_links,
        "stale_aliases": stale_aliases,
        "duplicate_destinations": duplicate_destinations,
        "false_online_declarations": false_online_declarations,
    }
