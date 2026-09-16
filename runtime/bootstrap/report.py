"""
Bootstrap Report and Formatting.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime, timezone

from .gates import ReadinessGate, GateResult


@dataclass
class BootstrapReport:
    """The result of a full 3-plane bootstrap sequence."""
    anny_ready: bool
    runtime_id: str
    fabric_node: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = None
    gates: List[GateResult] = field(default_factory=list)

    def add_result(self, result: GateResult) -> None:
        self.gates.append(result)

    def finish(self, ready: bool) -> None:
        self.anny_ready = ready
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def get_gate(self, gate: ReadinessGate) -> GateResult:
        for g in self.gates:
            if g.gate == gate:
                return g
        return GateResult(gate, False, "Not evaluated")


class ChatGPTBootstrapFormatter:
    """Formats a BootstrapReport into the canonical 9-line structure."""
    
    @staticmethod
    def format(report: BootstrapReport) -> str:
        status = "READY" if report.anny_ready else "DEGRADED"
        
        # Extract evidence safely
        node_id = report.fabric_node or "UNKNOWN"
        runtime_id = report.runtime_id or "UNKNOWN"
        tenant_id = report.get_gate(ReadinessGate.FABRIC_TENANT_BOUND).evidence or "UNBOUND"
        
        return f"""ANNY BOOTSTRAP: {status}
PLANE_1_GITHUB: {report.get_gate(ReadinessGate.GITHUB_CONNECTED).passed}
PLANE_2_FABRIC: {report.get_gate(ReadinessGate.FABRIC_REACHABLE).passed}
PLANE_3_RUNTIME: {report.get_gate(ReadinessGate.RUNTIME_IDENTITY).passed}
RUNTIME_ID: {runtime_id}
FABRIC_NODE: {node_id}
FABRIC_TENANT: {tenant_id}
RECONCILIATION: {report.get_gate(ReadinessGate.PLANE_RECONCILIATION).passed}
CONTINUITY_COHERENT: {report.get_gate(ReadinessGate.CONTINUITY_COHERENT).passed}"""
