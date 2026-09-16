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
            f"PLANE_1_GITHUB_CONNECTED: {g(ReadinessGate.GITHUB_CONNECTED)}",
            f"PLANE_1_GITHUB_ORG_BOUND: {g(ReadinessGate.GITHUB_ORG_BOUND)}",
            f"PLANE_2_FABRIC_REACHABLE: {g(ReadinessGate.FABRIC_REACHABLE)}",
            f"PLANE_2_FABRIC_IDENTITY: {g(ReadinessGate.FABRIC_IDENTITY_VERIFIED)}",
            f"PLANE_2_FABRIC_TRUST: {g(ReadinessGate.FABRIC_TRUST_VERIFIED)}",
            f"PLANE_2_FABRIC_TENANT: {g(ReadinessGate.FABRIC_TENANT_BOUND)}",
            f"PLANE_2_FABRIC_STATE: {g(ReadinessGate.FABRIC_STATE_READABLE)}",
            f"PLANE_2_FABRIC_PROVENANCE: {g(ReadinessGate.FABRIC_PROVENANCE_VALID)}",
            f"PLANE_2_FABRIC_NODE_HEAD: {g(ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD)}",
            f"PLANE_3_RUNTIME_REACHABLE: {g(ReadinessGate.RUNTIME_REACHABLE)}",
            f"PLANE_3_RUNTIME_HEALTH: {g(ReadinessGate.RUNTIME_HEALTH_VERIFIED)}",
            f"PLANE_3_RUNTIME_BINDING: {g(ReadinessGate.RUNTIME_BINDING_VERIFIED)}",
            f"PLANE_3_RUNTIME_ADMITTED: {g(ReadinessGate.RUNTIME_ADMITTED)}",
            f"CROSS_RECONCILIATION: {g(ReadinessGate.PLANE_RECONCILIATION)}",
            f"CROSS_CONTINUITY: {g(ReadinessGate.CONTINUITY_COHERENT)}",
            f"RUNTIME_ID: {runtime_id}",
            f"FABRIC_NODE: {node_id}",
            f"FABRIC_TENANT: {tenant_id}",
        ]
        return "\n".join(lines)
