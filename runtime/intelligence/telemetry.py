import logging
from typing import Optional, Dict, Any
from runtime.intelligence.models import CapabilityAssessmentRequest, CapabilityAssessmentResponse, DelegationDecision

try:
    from runtime.telemetry.collector import TelemetryCollector
    from runtime.telemetry.models import TelemetryEvent, TraceContext
except ImportError:
    TelemetryCollector = None
    TelemetryEvent = None
    TraceContext = None

logger = logging.getLogger(__name__)

class IntelligenceTelemetry:
    """Emits telemetry events for the Local Intelligence Layer."""

    def __init__(self, collector: Optional['TelemetryCollector'] = None):
        self.collector = collector

    def emit_capability_assessed(
        self,
        request: CapabilityAssessmentRequest,
        response: CapabilityAssessmentResponse,
        decision: str,
        session_id: str = "unknown",
        account_id: str = "unknown",
        project_id: str = "unknown",
        workspace_id: str = "unknown",
        task_id: str = "unknown",
        execution_id: str = "unknown",
        trace_context: Optional['TraceContext'] = None
    ):
        if not self.collector:
            return

        # Phase 27: Telemetry must capture the decision without logging secrets.
        payload = {
            "capability_id": request.capability_id,
            "quality_required": request.quality_required,
            "quality_available": response.quality_score,
            "tier": response.tier.value if hasattr(response.tier, 'value') else response.tier,
            "execution_mode": decision,
            "available": response.available,
            "resource_fit": response.resource_fit.value if hasattr(response.resource_fit, 'value') else response.resource_fit,
            "policy_fit": response.policy_fit,
        }

        # Based on decision, pick event type
        event_type = f"capability.{decision.lower()}"
        if decision == DelegationDecision.LOCAL_INFERENCE if hasattr(DelegationDecision, 'LOCAL_INFERENCE') else "LOCAL_INFERENCE":
            event_type = "capability.delegated"
            
        # Emit assessed event
        self.collector.record_event(
            name="capability.assessed",
            payload=payload,
            session_id=session_id,
            account_id=account_id,
            project_id=project_id,
            workspace_id=workspace_id,
            trace_context=trace_context
        )
        
        # Emit decision event
        self.collector.record_event(
            name=event_type,
            payload=payload,
            session_id=session_id,
            account_id=account_id,
            project_id=project_id,
            workspace_id=workspace_id,
            trace_context=trace_context
        )
