"""
Bootstrap Report and Formatting.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime, timezone

from .gates import ReadinessGate, GateResult


@dataclass
class ComponentInventory:
    declared: List[str] = field(default_factory=list)
    configured: List[str] = field(default_factory=list)
    enabled: List[str] = field(default_factory=list)
    authorized: List[str] = field(default_factory=list)
    available: List[str] = field(default_factory=list)
    functional: List[str] = field(default_factory=list)
    tested: List[str] = field(default_factory=list)
    verified: List[str] = field(default_factory=list)

@dataclass
class BootstrapReport:
    """The result of a full 3-plane bootstrap sequence."""
    anny_ready: bool
    runtime_id: str
    fabric_node: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = None
    gates: List[GateResult] = field(default_factory=list)
    
    # State tracking
    policy_revision: str = "UNKNOWN"
    admission_status: str = "UNKNOWN"
    reconciliation_status: str = "UNKNOWN"
    limits_verified: bool = False
    # Local observations of external CONRRAD authority; empty means not observed.
    bootstrap_state: str = "UNKNOWN"
    conrrad_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    
    # Inventories
    capabilities: ComponentInventory = field(default_factory=ComponentInventory)
    tools: ComponentInventory = field(default_factory=ComponentInventory)
    models: ComponentInventory = field(default_factory=ComponentInventory)
    workers: ComponentInventory = field(default_factory=ComponentInventory)
    connectors: ComponentInventory = field(default_factory=ComponentInventory)

    def add_result(self, result: GateResult) -> None:
        self.gates.append(result)

    def finish(self, ready: bool) -> None:
        self.anny_ready = ready
        self.bootstrap_state = "READY" if ready else "BLOCKED"
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def get_gate(self, gate: ReadinessGate) -> GateResult:
        for g in self.gates:
            if g.gate == gate:
                return g
        return GateResult(gate, False, "Not evaluated")


class ChatGPTBootstrapFormatter:
    """Formats a BootstrapReport into the canonical structure."""

    @staticmethod
    def format(report: BootstrapReport) -> str:
        if report.anny_ready:
            status = "READY"
        else:
            status = "BLOCKED"   # NEVER "DEGRADED" — failure = BLOCKED

        # Extract evidence safely
        node_id = report.fabric_node or "UNKNOWN"
        runtime_id = report.runtime_id or "UNKNOWN"
        tenant_id = report.get_gate(ReadinessGate.FABRIC_TENANT_BOUND).evidence or "UNBOUND"

        def g(gate):
            r = report.get_gate(gate)
            return "PASS" if r.passed else "FAIL"

        lines = [
            f"ANNY BOOTSTRAP: {status}",
            f"---",
            f"PHASE A (LOCAL RUNTIME):",
            f"  RUNTIME_IDENTITY: {g(ReadinessGate.RUNTIME_IDENTITY)}",
            f"  RUNTIME_REACHABLE: {g(ReadinessGate.RUNTIME_REACHABLE)}",
            f"  RUNTIME_HEALTH: {g(ReadinessGate.RUNTIME_HEALTH_VERIFIED)}",
            f"PHASE B (GITHUB):",
            f"  GITHUB_CONNECTED: {g(ReadinessGate.GITHUB_CONNECTED)}",
            f"  GITHUB_ORG_BOUND: {g(ReadinessGate.GITHUB_ORG_BOUND)}",
            f"PHASE C (FABRIC):",
            f"  FABRIC_REACHABLE: {g(ReadinessGate.FABRIC_REACHABLE)}",
            f"  FABRIC_STATE_READABLE: {g(ReadinessGate.FABRIC_STATE_READABLE)}",
            f"  FABRIC_NODE_HEAD: {g(ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD)}",
            f"PHASE D (TRUST & ADMISSION):",
            f"  FABRIC_IDENTITY: {g(ReadinessGate.FABRIC_IDENTITY_VERIFIED)}",
            f"  FABRIC_TRUST: {g(ReadinessGate.FABRIC_TRUST_VERIFIED)}",
            f"  FABRIC_TENANT: {g(ReadinessGate.FABRIC_TENANT_BOUND)}",
            f"  RUNTIME_BINDING: {g(ReadinessGate.RUNTIME_BINDING_VERIFIED)}",
            f"  RUNTIME_ADMITTED: {g(ReadinessGate.RUNTIME_ADMITTED)}",
            f"PHASE E (POLICY):",
            f"  POLICY_SNAPSHOT_FRESH: {g(ReadinessGate.POLICY_SNAPSHOT_FRESH)}",
            f"PHASE F (RECONCILIATION):",
            f"  PLANE_RECONCILIATION: {g(ReadinessGate.PLANE_RECONCILIATION)}",
            f"PHASE G (INVENTORY):",
            f"  CAPABILITIES_INVENTORIED: {g(ReadinessGate.CAPABILITIES_INVENTORIED)}",
            f"  TOOLS_INVENTORIED: {g(ReadinessGate.TOOLS_INVENTORIED)}",
            f"  MODELS_INVENTORIED: {g(ReadinessGate.MODELS_INVENTORIED)}",
            f"  WORKERS_INVENTORIED: {g(ReadinessGate.WORKERS_INVENTORIED)}",
            f"  CONNECTORS_INVENTORIED: {g(ReadinessGate.CONNECTORS_INVENTORIED)}",
            f"PHASE H (ACCESS):",
            f"  CRITICAL_ACCESS_VERIFIED: {g(ReadinessGate.CRITICAL_ACCESS_VERIFIED)}",
            f"PHASE I (CONTRACTS):",
            f"  CONTRACTS_DISCOVERED: {g(ReadinessGate.CONTRACTS_DISCOVERED)}",
            f"PHASE J (CONTEXT):",
            f"  DELEGATION_CONTEXT_BUILT: {g(ReadinessGate.DELEGATION_CONTEXT_BUILT)}",
            f"PHASE K (CONTINUITY):",
            f"  CONTINUITY_COHERENT: {g(ReadinessGate.CONTINUITY_COHERENT)}",
        ]
        
        def format_comp(name, comp):
            return f"  {name}: {len(comp.declared)} DEC, {len(comp.configured)} CFG, {len(comp.enabled)} ENA, {len(comp.authorized)} AUT, {len(comp.available)} AVL, {len(comp.functional)} FNC, {len(comp.tested)} TST, {len(comp.verified)} VRF"
        
        lines.extend([
            f"---",
            f"INVENTORY SUMMARY:",
            format_comp("Capabilities", report.capabilities),
            format_comp("Tools", report.tools),
            format_comp("Models", report.models),
            format_comp("Workers", report.workers),
            format_comp("Connectors", report.connectors),
            f"---",
            f"RUNTIME_ID: {runtime_id}",
            f"FABRIC_NODE: {node_id}",
            f"FABRIC_TENANT: {tenant_id}",
            f"POLICY_REVISION: {report.policy_revision}",
            f"LIMITS_VERIFIED: {report.limits_verified}",
            f"BOOTSTRAP_STATE: {report.bootstrap_state}",
            f"CONRRAD_DEPENDENCIES_OBSERVED: {len(report.conrrad_dependencies)}",
        ])
        return "\n".join(lines)
