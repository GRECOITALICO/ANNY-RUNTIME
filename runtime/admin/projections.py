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
        _p("runtime.reconnect", "Runtime reconnect", "Runtime Identity", priority="P1", source_authority="RUNTIME", implementation_status="BOUND", tags=("reconnect",)),
        _p("admin.operations", "Operations", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/operations", implementation_status="PARTIAL", failure_reason="No canonical Runtime operation registry is exposed to the admin renderer.", sort_order=205, tags=("operations",)),
        _p("admin.receipts", "Receipts", "Evidence / Provenance", priority="P1", source_authority="RECEIPT_STORE", route_or_detail="/receipts", implementation_status="PARTIAL", failure_reason="No canonical Runtime receipt registry is exposed to the admin renderer.", sort_order=185, tags=("receipts",)),
        _p("admin.doctor", "Runtime doctor", "Security / Trust", priority="P0", source_authority="RUNTIME", route_or_detail="/doctor", implementation_status="BOUND", sort_order=325, tags=("doctor", "diagnostics")),
        _p("admin.policies", "Policies", "Security / Trust", priority="P0", source_authority="POLICY_ENGINE", route_or_detail="/policies", implementation_status="BOUND", sort_order=326, tags=("policy",)),
        _p("admin.diagnostics", "Admin diagnostics", "Security / Trust", priority="P1", source_authority="RUNTIME", route_or_detail="/admin/diagnostics", implementation_status="BOUND", sort_order=327, tags=("diagnostics",)),
        _p("admin.update_check", "Admin update check", "Distribution / Updates", priority="P1", source_authority="SYNC_SERVICE", route_or_detail="/admin/update-check", implementation_status="BOUND", sort_order=375, tags=("updates", "check")),
        _p("universe.accounts", "Accounts", "Universe", priority="P0", source_authority="ACCOUNT_REGISTRY", route_or_detail="/universe/accounts", implementation_status="BOUND", sort_order=15, tags=("universe", "accounts")),
        _p("universe.account_detail", "Account detail", "Universe", priority="P2", source_authority="ACCOUNT_REGISTRY", route_or_detail="/universe/accounts/{account_id}", implementation_status="PLANNED", tags=("universe", "accounts", "detail")),
        _p("universe.organization", "Organization", "Universe", priority="P0", source_authority="CANONICAL_STATE", route_or_detail="/universe/organization", implementation_status="BOUND", sort_order=20, tags=("universe", "organization")),
        _p("universe.projects", "Projects", "Universe", priority="P0", source_authority="PROJECT_REGISTRY", route_or_detail="/universe/projects", implementation_status="PARTIAL", sort_order=25, tags=("universe", "projects")),
        _p("universe.repositories", "Repositories", "Universe", priority="P0", source_authority="GITHUB_AUTH", route_or_detail="/universe/repositories", implementation_status="BOUND", sort_order=30, tags=("universe", "repositories")),
        _p("universe.resources", "Resources", "Universe", priority="P0", source_authority="RESOURCE_REGISTRY", route_or_detail="/universe/resources", implementation_status="BOUND", sort_order=35, tags=("universe", "resources")),
        _p("execution.missions", "Missions", "Execution", priority="P0", source_authority="CANONICAL_STATE", route_or_detail="/execution/missions", implementation_status="BOUND", sort_order=196, tags=("execution", "missions")),
        _p("execution.execution_runs", "Executions", "Execution", priority="P0", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/executions", implementation_status="BOUND", sort_order=197, tags=("execution", "runs")),
        _p("execution.workspaces", "Workspaces", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/workspaces", implementation_status="PLANNED", sort_order=198, tags=("execution", "workspace")),
        _p("intelligence.executors_view", "Executors view", "Intelligence", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/executors", implementation_status="PARTIAL", failure_reason="Current executor view remains a static compatibility surface; no canonical executor inventory is exposed.", sort_order=255, tags=("intelligence", "executors")),
        _p("browser.session_detail", "Managed browser session detail", "Browser", priority="P2", source_authority="BROWSER_RUNTIME", route_or_detail="/browser/{session_id}", implementation_status="BOUND", sort_order=365, tags=("browser", "detail")),
        _p("audit.search", "Audit/search discovery", "Evidence / Provenance", priority="P1", source_authority="AUDIT_STORE", route_or_detail="/search", implementation_status="PARTIAL", sort_order=182, tags=("audit", "search")),
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
        
        _p("evidence.provenance", "Evidence provenance", "Evidence / Provenance", priority="P1", source_authority="EVIDENCE_REGISTRY", implementation_status="PARTIAL", route_or_detail="/audit/provenance", sort_order=180, tags=("provenance",)),
        _p("execution.processing_matrix", "Processing matrix", "Execution", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/api/processing/matrix", sort_order=190, tags=("execution", "telemetry")),
        _p("execution.tasks", "Execution tasks", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/tasks", implementation_status="BOUND", sort_order=200, tags=("tasks",)),
        _p("execution.workers", "Execution workers", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/workers", implementation_status="BOUND", sort_order=210, tags=("workers",)),
        _p("execution.worker_detail", "Execution worker detail", "Execution", priority="P2", source_authority="RUNTIME_EXECUTION", route_or_detail="/workers/{worker_id}", implementation_status="BOUND", sort_order=211, tags=("workers", "detail")),
        _p("execution.results", "Execution results", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/results", implementation_status="PLANNED", sort_order=220, tags=("results",)),
        _p("intelligence.capabilities", "Intelligence capabilities", "Intelligence", priority="P0", route_or_detail="/intelligence/capabilities", sort_order=230, tags=("capabilities",)),
        _p("intelligence.models", "Intelligence models", "Intelligence", priority="P1", route_or_detail="/models", implementation_status="PARTIAL", sort_order=240, tags=("models",)),
        _p("intelligence.model_detail", "Intelligence model detail", "Intelligence", priority="P2", source_authority="RUNTIME_MODEL_REGISTRY", route_or_detail="/models/{model_id}", implementation_status="BOUND", sort_order=241, tags=("models", "detail")),
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
        _p("processing.events", "Processing events stream", "Telemetry", priority="P1", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/api/processing/events", implementation_status="BOUND", sort_order=410, tags=("telemetry", "events", "processing")),
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
        _p("continuity.bootstrap_api", "Continuity bootstrap API", "Continuity", priority="P1", source_authority="CONTINUITY_ENGINE", route_or_detail="/api/v1/continuity/bootstrap", implementation_status="BOUND", sort_order=441, tags=("api", "continuity", "bootstrap")),
        _p("control.projections_api", "Control Center projection registry API", "Control Center", priority="P0", source_authority="PROJECTION_REGISTRY", route_or_detail="/api/control-center/projections", implementation_status="BOUND", sort_order=442, tags=("api", "projections", "control_center")),
        _p("telemetry.stream_api", "Telemetry event stream API", "Telemetry", priority="P1", source_authority="TELEMETRY_STREAM", route_or_detail="/api/v1/telemetry/stream", implementation_status="BOUND", sort_order=443, tags=("api", "telemetry", "stream", "sse")),
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
        _p("api.bridge_tasks", "ChatGPT/Luna external bridge task creation", "Control Center", priority="P1", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge/tasks", implementation_status="BOUND", sort_order=462, tags=("api", "bridge", "tasks")),
        _p("api.bridge_task_query", "External bridge task status query", "Control Center", priority="P1", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge/tasks/{task_id}", implementation_status="BOUND", sort_order=463, tags=("api", "bridge", "tasks", "query")),
        _p("api.bridge_execution_query", "External bridge execution result query", "Control Center", priority="P1", source_authority="BRIDGE_ROUTER", route_or_detail="/api/v1/bridge/executions/{execution_id}", implementation_status="BOUND", sort_order=464, tags=("api", "bridge", "executions", "query")),
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
        _p("admin.executions", "Execution list compatibility surface", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/executions", implementation_status="BOUND", sort_order=486, tags=("execution", "compatibility", "admin")),
        _p("admin.workers", "Worker list compatibility surface", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/workers", implementation_status="BOUND", sort_order=487, tags=("workers", "compatibility", "admin")),
        _p("admin.capabilities", "Capability list compatibility surface", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/capabilities", implementation_status="BOUND", sort_order=488, tags=("capabilities", "compatibility", "admin")),

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

