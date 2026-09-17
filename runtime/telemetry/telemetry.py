"""TelemetryEnvelope — the single canonical data structure for all ANNY Universe events.

Every component emits telemetry through this envelope. Fields that are not applicable
to a given event are set to None. The envelope is serialised to JSON Lines for
append-only persistence and can be reconstructed into full execution traces.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class ExecutionMode(str, enum.Enum):
    """Backward-compatible execution mode grouping."""
    DETERMINISTIC = "DETERMINISTIC"
    INFERENCE = "INFERENCE"


class RoutingClass(str, enum.Enum):
    """Canonical processing plane for task execution."""
    DETERMINISTIC = "DETERMINISTIC"
    LOCAL_MODEL = "LOCAL_MODEL"
    FRONTIER_MODEL = "FRONTIER_MODEL"
    UNKNOWN = "UNKNOWN"


class TelemetryDomain(str, enum.Enum):
    """Distinguishes Host Foundation events from ANNY Universe events."""
    HOST_FOUNDATION = "HOST_FOUNDATION"
    ANNY_UNIVERSE = "ANNY_UNIVERSE"


@dataclass
class TelemetryEnvelope:
    """Canonical telemetry envelope for the ANNY Universe.

    All fields are present on every envelope instance. Fields that do not
    apply to a specific event carry ``None``. The ``event_id`` is always
    populated; ``trace_id`` and ``span_id`` are populated when a
    ``TraceContext`` is available.
    """

    # Identity
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None

    # Temporal
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Classification
    component: str = ""
    event_type: str = ""
    source: str = ""
    domain: str = TelemetryDomain.ANNY_UNIVERSE.value

    # Correlation
    task_id: Optional[str] = None
    execution_id: Optional[str] = None
    worker_id: Optional[str] = None
    directorate_id: Optional[str] = None
    department_id: Optional[str] = None
    workspace_id: Optional[str] = None
    tenant_id: Optional[str] = None
    account_id: Optional[str] = None
    project_id: Optional[str] = None
    repository_id: Optional[str] = None
    resource_id: Optional[str] = None
    capability_id: Optional[str] = None
    capability_family: Optional[str] = None

    # Execution classification
    execution_mode: Optional[str] = None
    routing_class: Optional[str] = None
    executor_type: Optional[str] = None
    executor_id: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    policy_version: Optional[str] = None

    # Outcome
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    input_size: Optional[int] = None
    output_size: Optional[int] = None
    input_hash: Optional[str] = None
    result_hash: Optional[str] = None

    # Extensible metadata (safe fields only)
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict suitable for JSON encoding."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def create(
        cls,
        *,
        component: str,
        event_type: str,
        source: str,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        domain: str = TelemetryDomain.ANNY_UNIVERSE.value,
        task_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        directorate_id: Optional[str] = None,
        department_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        account_id: Optional[str] = None,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        capability_id: Optional[str] = None,
        capability_family: Optional[str] = None,
        execution_mode: Optional[str] = None,
        routing_class: Optional[str] = None,
        executor_type: Optional[str] = None,
        executor_id: Optional[str] = None,
        model_id: Optional[str] = None,
        model_version: Optional[str] = None,
        policy_version: Optional[str] = None,
        status: Optional[str] = None,
        duration_ms: Optional[int] = None,
        input_size: Optional[int] = None,
        output_size: Optional[int] = None,
        input_hash: Optional[str] = None,
        result_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TelemetryEnvelope":
        """Factory method with keyword-only arguments for clarity."""
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            component=component,
            event_type=event_type,
            source=source,
            domain=domain,
            task_id=task_id,
            execution_id=execution_id,
            worker_id=worker_id,
            directorate_id=directorate_id,
            department_id=department_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            account_id=account_id,
            project_id=project_id,
            repository_id=repository_id,
            resource_id=resource_id,
            capability_id=capability_id,
            capability_family=capability_family,
            execution_mode=execution_mode,
            routing_class=routing_class,
            executor_type=executor_type,
            executor_id=executor_id,
            model_id=model_id,
            model_version=model_version,
            policy_version=policy_version,
            status=status,
            duration_ms=duration_ms,
            input_size=input_size,
            output_size=output_size,
            input_hash=input_hash,
            result_hash=result_hash,
            metadata=metadata or {},
        )
