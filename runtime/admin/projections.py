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
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, object]:
        if limit < 1 or limit > 200:
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
        page = items[offset:offset + limit]
        return {
            "contract_version": REGISTRY_CONTRACT_VERSION,
            "master_inventory_boundary": MASTER_INVENTORY_BOUNDARY,
            "inventory_limit": None,
            "initial_p0_viewport_target": INITIAL_P0_VIEWPORT_TARGET,
            "summary": self.summary(),
            "page": {
                "limit": limit,
                "offset": offset,
                "returned": len(page),
                "total_filtered": total_filtered,
                "has_more": offset + len(page) < total_filtered,
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
        _p("onboarding.device_flow", "GitHub Device Flow", "Onboarding", priority="P1", source_authority="GITHUB_AUTH", route_or_detail="/github/device/poll", implementation_status="BOUND", sort_order=6, tags=("onboarding", "device-flow")),
        _p("onboarding.access_token", "GitHub access token fallback", "Onboarding", priority="P1", source_authority="GITHUB_AUTH", route_or_detail="/github/token", implementation_status="BOUND", sort_order=7, tags=("onboarding", "fallback")),
        _p("onboarding.ready", "Ready state", "Onboarding", priority="P1", source_authority="RUNTIME", implementation_status="BOUND", route_or_detail="/", sort_order=8, tags=("ready",)),
        _p("onboarding.failure", "Failure state", "Onboarding", priority="P1", source_authority="RUNTIME", implementation_status="BOUND", route_or_detail="/", sort_order=9, tags=("failure",)),
        _p("fabric.setup", "Repository Fabric setup", "Repository Fabric", priority="P1", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/fabric/setup", implementation_status="BOUND", sort_order=72, tags=("fabric", "setup")),
        _p("runtime.reconnect", "Runtime reconnect", "Runtime Identity", priority="P1", source_authority="RUNTIME", implementation_status="BOUND", tags=("reconnect",)),
        _p("admin.operations", "Operations", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/operations", implementation_status="PARTIAL", failure_reason="No canonical Runtime operation registry is exposed to the admin renderer.", sort_order=205, tags=("operations",)),
        _p("admin.receipts", "Receipts", "Evidence / Provenance", priority="P1", source_authority="RECEIPT_STORE", route_or_detail="/receipts", implementation_status="PARTIAL", failure_reason="No canonical Runtime receipt registry is exposed to the admin renderer.", sort_order=185, tags=("receipts",)),
        _p("admin.doctor", "Runtime doctor", "Security / Trust", priority="P1", source_authority="RUNTIME", route_or_detail="/doctor", implementation_status="BOUND", sort_order=325, tags=("doctor", "diagnostics")),
        _p("admin.policies", "Policies", "Security / Trust", priority="P1", source_authority="POLICY_ENGINE", route_or_detail="/policies", implementation_status="BOUND", sort_order=326, tags=("policy",)),
        _p("admin.diagnostics", "Admin diagnostics", "Security / Trust", priority="P1", source_authority="RUNTIME", route_or_detail="/admin/diagnostics", implementation_status="BOUND", sort_order=327, tags=("diagnostics",)),
        _p("admin.update_check", "Admin update check", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", route_or_detail="/admin/update-check", implementation_status="BOUND", sort_order=375, tags=("updates", "check")),
        _p("universe.accounts", "Accounts", "Universe", priority="P1", source_authority="ACCOUNT_REGISTRY", route_or_detail="/universe/accounts", implementation_status="BOUND", sort_order=15, tags=("universe", "accounts")),
        _p("universe.account_detail", "Account detail", "Universe", priority="P2", source_authority="ACCOUNT_REGISTRY", implementation_status="PLANNED", tags=("universe", "accounts", "detail")),
        _p("universe.organization", "Organization", "Universe", priority="P0", source_authority="CANONICAL_STATE", route_or_detail="/universe/organization", implementation_status="BOUND", sort_order=20, tags=("universe", "organization")),
        _p("universe.projects", "Projects", "Universe", priority="P0", source_authority="PROJECT_REGISTRY", route_or_detail="/universe/projects", implementation_status="PARTIAL", sort_order=25, tags=("universe", "projects")),
        _p("universe.repositories", "Repositories", "Universe", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/universe/repositories", implementation_status="BOUND", sort_order=30, tags=("universe", "repositories")),
        _p("universe.resources", "Resources", "Universe", priority="P1", source_authority="RESOURCE_REGISTRY", route_or_detail="/universe/resources", implementation_status="BOUND", sort_order=35, tags=("universe", "resources")),
        _p("execution.missions", "Missions", "Execution", priority="P0", source_authority="CANONICAL_STATE", route_or_detail="/execution/missions", implementation_status="BOUND", sort_order=196, tags=("execution", "missions")),
        _p("execution.execution_runs", "Executions", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/executions", implementation_status="BOUND", sort_order=197, tags=("execution", "runs")),
        _p("execution.workspaces", "Workspaces", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/workspaces", implementation_status="PLANNED", sort_order=198, tags=("execution", "workspace")),
        _p("intelligence.executors_view", "Executors view", "Intelligence", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/executors", implementation_status="PARTIAL", failure_reason="Current executor view remains a static compatibility surface; no canonical executor inventory is exposed.", sort_order=255, tags=("intelligence", "executors")),
        _p("browser.session_detail", "Managed browser session detail", "Browser", priority="P2", source_authority="BROWSER_RUNTIME", route_or_detail="/browser/{session_id}", implementation_status="BOUND", sort_order=365, tags=("browser", "detail")),
        _p("audit.search", "Audit/search discovery", "Evidence / Provenance", priority="P1", source_authority="AUDIT_STORE", route_or_detail="/search", implementation_status="PARTIAL", sort_order=182, tags=("audit", "search")),
        _p("runtime.identity.state", "ANNY runtime state", "Runtime Identity", sort_order=10, tags=("header", "state")),
        _p("control.top_level_state", "Top-Level State panel", "Control Center", priority="P0", source_authority="RUNTIME", sort_order=1, tags=("panel", "shell")),
        _p("control.operational_snapshot", "Operational Snapshot panel", "Control Center", priority="P0", source_authority="RUNTIME", sort_order=2, tags=("panel",)),
        _p("control.bootstrap_verification", "Bootstrap Verification panel", "Control Center", priority="P0", source_authority="BOOTSTRAP_ENGINE", sort_order=3, tags=("panel", "gates")),
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
        _p("runtime.health", "Runtime health", "Runtime Identity", sort_order=20, tags=("health",)),
        _p("runtime.version", "Runtime version", "Runtime Identity", sort_order=30, tags=("version",)),
        _p("runtime.readiness", "Runtime readiness", "Runtime Identity", sort_order=40, tags=("readiness",)),
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
        _p("continuity.status", "Continuity status", "Continuity", source_authority="CANONICAL_STATE", implementation_status="PARTIAL", route_or_detail="/continuity/timeline", sort_order=150, tags=("continuity",)),
        _p("continuity.recovery", "Continuity recovery", "Continuity", priority="P1", source_authority="CANONICAL_STATE", implementation_status="PLANNED", route_or_detail="/continuity/recovery", sort_order=160, tags=("recovery",)),
        _p("evidence.freshness", "Evidence freshness", "Evidence / Provenance", priority="P0", source_authority="EVIDENCE_REGISTRY", implementation_status="PLANNED", sort_order=170, tags=("evidence", "freshness")),
        _p("audit.events", "Audit events", "Evidence / Provenance", priority="P1", source_authority="AUDIT_STORE", route_or_detail="/audit/events", implementation_status="BOUND", sort_order=181, tags=("audit", "events")),
        
        _p("evidence.provenance", "Evidence provenance", "Evidence / Provenance", priority="P1", source_authority="EVIDENCE_REGISTRY", implementation_status="PARTIAL", route_or_detail="/audit/provenance", sort_order=180, tags=("provenance",)),
        _p("execution.processing_matrix", "Processing matrix", "Execution", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/api/processing/matrix", sort_order=190, tags=("execution", "telemetry")),
        _p("execution.tasks", "Execution tasks", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/tasks", implementation_status="BOUND", sort_order=200, tags=("tasks",)),
        _p("execution.workers", "Execution workers", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/workers", implementation_status="BOUND", sort_order=210, tags=("workers",)),
        _p("execution.worker_detail", "Execution worker detail", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/workers/{worker_id}", implementation_status="BOUND", sort_order=211, tags=("workers", "detail")),
        _p("execution.results", "Execution results", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/results", implementation_status="PLANNED", sort_order=220, tags=("results",)),
        _p("intelligence.capabilities", "Intelligence capabilities", "Intelligence", priority="P1", route_or_detail="/intelligence/capabilities", sort_order=230, tags=("capabilities",)),
        _p("intelligence.models", "Intelligence models", "Intelligence", priority="P1", route_or_detail="/models", implementation_status="PARTIAL", sort_order=240, tags=("models",)),
        _p("intelligence.model_detail", "Intelligence model detail", "Intelligence", priority="P2", source_authority="RUNTIME_MODEL_REGISTRY", route_or_detail="/models/{model_id}", implementation_status="BOUND", sort_order=241, tags=("models", "detail")),
        _p("intelligence.executors", "Intelligence executors", "Intelligence", priority="P1", route_or_detail="/intelligence/executors", implementation_status="PLANNED", sort_order=250, tags=("executors",)),
        _p("intelligence.performance", "Intelligence performance", "Intelligence", priority="P2", route_or_detail="/intelligence/performance", implementation_status="PLANNED", sort_order=260, tags=("performance",)),
        _p("infrastructure.runtime", "Runtime topology", "Infrastructure", priority="P1", route_or_detail="/infrastructure/runtime", sort_order=270, tags=("topology",)),
        _p("infrastructure.github", "GitHub infrastructure", "Infrastructure", priority="P1", source_authority="GITHUB_AUTH", route_or_detail="/infrastructure/github", implementation_status="PLANNED", sort_order=280, tags=("github", "infrastructure")),
        _p("infrastructure.fabric", "Fabric infrastructure", "Infrastructure", priority="P1", source_authority="FABRIC_LIVE_TRUTH", route_or_detail="/infrastructure/fabric", implementation_status="PLANNED", sort_order=290, tags=("fabric", "infrastructure")),
        _p("infrastructure.mcp", "MCP infrastructure", "Infrastructure", priority="P2", source_authority="RUNTIME_MCP", route_or_detail="/infrastructure/mcp", implementation_status="PLANNED", sort_order=300, tags=("mcp",)),
        _p("infrastructure.azure", "Azure infrastructure", "Infrastructure", priority="P2", source_authority="AZURE_LIVE_TRUTH", route_or_detail="/infrastructure/azure", implementation_status="PLANNED", sort_order=310, tags=("azure",)),
        _p("security.trust", "Security and trust posture", "Security / Trust", source_authority="RUNTIME_SECURITY", priority="P0", implementation_status="PARTIAL", sort_order=320, tags=("security", "trust")),
        _p("communication.sessions", "Admin sessions", "Communication", priority="P1", source_authority="RUNTIME_AUTH", route_or_detail="/sessions", sort_order=330, tags=("sessions",)),
        _p("telemetry.live", "Live telemetry", "Telemetry", priority="P1", source_authority="TELEMETRY_STREAM", route_or_detail="/telemetry/live", sort_order=340, tags=("sse", "live")),
        _p("telemetry.timeline", "Telemetry timeline", "Telemetry", priority="P1", source_authority="TELEMETRY_STORE", route_or_detail="/telemetry/timeline", sort_order=350, tags=("timeline",)),
        _p("browser.dashboard", "Managed browser dashboard", "Browser", priority="P1", source_authority="BROWSER_RUNTIME", route_or_detail="/browser", sort_order=360, tags=("browser",)),
        _p("distribution.sync", "Governed SYNC state", "Distribution / Updates", priority="P0", source_authority="SYNC_SERVICE", implementation_status="BOUND", sort_order=370, tags=("sync", "updates")),
        _p("distribution.sync_stage", "SYNC stage capability", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", implementation_status="BLOCKED", failure_reason="Stage currently uses a stub lifecycle and must not be presented as physical staging.", sort_order=380, tags=("sync", "stage")),
        _p("distribution.activation", "Activation capability", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", implementation_status="BLOCKED", failure_reason="Activation is intentionally fail-closed and not physically implemented.", sort_order=390, tags=("activation", "safe-fail-closed")),
        _p("distribution.rollback", "Rollback capability", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", implementation_status="BLOCKED", failure_reason="Rollback currently contains a stub lifecycle and must not be presented as physical rollback.", sort_order=400, tags=("rollback", "safe-fail-closed")),
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

    NavigationItem("CONTINUITY", "Current state", "⏱", "/continuity/state", "continuity.status", "PLANNED"),
    NavigationItem("CONTINUITY", "Mission", "🎯", "/continuity/mission", "project.current_mission", "PLANNED"),
    NavigationItem("CONTINUITY", "Task", "✓", "/continuity/task", "project.current_task", "PLANNED"),
    NavigationItem("CONTINUITY", "Next action", "⏭", "/continuity/next", "project.next_action", "PLANNED"),
    NavigationItem("CONTINUITY", "Blockers", "🛑", "/continuity/blockers", "project.blockers", "PLANNED"),
    NavigationItem("CONTINUITY", "Recovery", "⚕", "/continuity/recovery", "continuity.recovery", "PLANNED"),

    NavigationItem("AUDIT", "Events", "📋", "/audit/events", "audit.events"),
    NavigationItem("AUDIT", "Provenance", "🔍", "/audit/provenance", "evidence.provenance"),
    NavigationItem("AUDIT", "Evidence", "🛡", "/audit/evidence", "evidence.freshness", "PLANNED"),
    NavigationItem("AUDIT", "Changes", "📝", "/audit/changes", "evidence.provenance", "PLANNED"),
)

