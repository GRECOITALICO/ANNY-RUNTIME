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
    evidence_ref: Optional[str]
    failure_reason: Optional[str]
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
    ) -> List[ProjectionDefinition]:
        items = list(self._items.values())
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
        return {
            "total_definitions": len(items),
            "by_priority": by_priority,
            "by_implementation_status": by_status,
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
    ) -> Dict[str, object]:
        items = self.list(
            priority=priority,
            section=section,
            implementation_status=implementation_status,
        )
        return {
            "contract_version": REGISTRY_CONTRACT_VERSION,
            "master_inventory_boundary": MASTER_INVENTORY_BOUNDARY,
            "inventory_limit": None,
            "initial_p0_viewport_target": INITIAL_P0_VIEWPORT_TARGET,
            "summary": self.summary(),
            "projections": [item.to_dict() for item in items],
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
    freshness: str = "LIVE_ON_READ",
    evidence_ref: Optional[str] = None,
    failure_reason: Optional[str] = None,
    dependencies: Sequence[str] = (),
    visibility_policy: str = "VISIBLE",
    renderer: str = "control_center",
    sort_order: int = 0,
    tags: Sequence[str] = (),
) -> ProjectionDefinition:
    return ProjectionDefinition(
        projection_id=projection_id,
        title=title,
        section=section,
        priority=priority,
        current_status="UNKNOWN",
        truth_class=truth_class,
        source_authority=source_authority,
        freshness=freshness,
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
        _p("runtime.identity.state", "ANNY runtime state", "Runtime Identity", sort_order=10, tags=("header", "state")),
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
        _p("evidence.provenance", "Evidence provenance", "Evidence / Provenance", priority="P1", source_authority="EVIDENCE_REGISTRY", implementation_status="PARTIAL", route_or_detail="/audit/provenance", sort_order=180, tags=("provenance",)),
        _p("execution.processing_matrix", "Processing matrix", "Execution", source_authority="TELEMETRY_AGGREGATOR", route_or_detail="/api/processing/matrix", sort_order=190, tags=("execution", "telemetry")),
        _p("execution.tasks", "Execution tasks", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/tasks", implementation_status="BOUND", sort_order=200, tags=("tasks",)),
        _p("execution.workers", "Execution workers", "Execution", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/workers", implementation_status="BOUND", sort_order=210, tags=("workers",)),
        _p("execution.results", "Execution results", "Execution", priority="P1", source_authority="RUNTIME_EXECUTION", route_or_detail="/execution/results", implementation_status="PLANNED", sort_order=220, tags=("results",)),
        _p("intelligence.capabilities", "Intelligence capabilities", "Intelligence", priority="P1", route_or_detail="/intelligence/capabilities", sort_order=230, tags=("capabilities",)),
        _p("intelligence.models", "Intelligence models", "Intelligence", priority="P1", route_or_detail="/intelligence/models", implementation_status="PARTIAL", sort_order=240, tags=("models",)),
        _p("intelligence.executors", "Intelligence executors", "Intelligence", priority="P1", route_or_detail="/intelligence/executors", implementation_status="BOUND", sort_order=250, tags=("executors",)),
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
