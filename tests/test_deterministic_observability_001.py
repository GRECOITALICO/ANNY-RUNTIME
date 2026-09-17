import pytest
import os
import tempfile
import uuid
from datetime import datetime, timezone

from runtime.telemetry.telemetry import TelemetryEnvelope, RoutingClass
from runtime.telemetry.collector import TelemetryCollector
from runtime.telemetry.aggregator import TelemetryAggregator


@pytest.fixture
def telemetry_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def collector(telemetry_dir):
    return TelemetryCollector(telemetry_dir)


@pytest.fixture
def aggregator(collector):
    return TelemetryAggregator(collector)


def test_out_of_order_event_arrival_and_folding(collector, aggregator):
    """Blocker 3: Verify execution_id folding and handle out-of-order event arrivals."""
    execution_id = "test-exec-123"
    
    # Emit events out of order
    # Event 1: TERMINAL (Timestamp 3)
    ev_terminal = TelemetryEnvelope.create(
        component="worker",
        event_type="execution.finished",
        source="execution",
        execution_id=execution_id,
        status="SUCCEEDED",
        duration_ms=1200
    )
    # Mocking timestamp to appear later chronologically
    ev_terminal.timestamp = "2026-01-01T10:05:00Z"

    # Event 2: ROUTED (Timestamp 1)
    ev_routed = TelemetryEnvelope.create(
        component="manager",
        event_type="task.routed",
        source="execution",
        execution_id=execution_id,
        routing_class="DETERMINISTIC",
        department_id="DEPT-01"
    )
    ev_routed.timestamp = "2026-01-01T10:00:00Z"

    # Event 3: STARTED (Timestamp 2)
    ev_started = TelemetryEnvelope.create(
        component="worker",
        event_type="execution.started",
        source="execution",
        execution_id=execution_id,
        status="RUNNING"
    )
    ev_started.timestamp = "2026-01-01T10:02:00Z"

    collector.emit(ev_terminal)
    collector.emit(ev_routed)
    collector.emit(ev_started)

    matrix = aggregator.get_matrix()
    global_stats = matrix.get("global", {})
    
    # Asserting that the final state is SUCCEEDED despite being emitted first
    assert global_stats.get("success") == 1
    assert global_stats.get("total") == 1
    assert global_stats.get("deterministic") == 1


def test_deterministic_success_measurement_discipline(collector, aggregator):
    """Blocker 4: Routing != success. Missing execution result must not invent success."""
    execution_id = "test-exec-456"

    ev_routed = TelemetryEnvelope.create(
        component="manager",
        event_type="task.routed",
        source="execution",
        execution_id=execution_id,
        routing_class="DETERMINISTIC",
        department_id="DEPT-01",
        status="QUEUED"
    )
    
    collector.emit(ev_routed)

    matrix = aggregator.get_matrix()
    global_stats = matrix.get("global", {})

    assert global_stats.get("total") == 1
    assert global_stats.get("deterministic") == 1
    assert global_stats.get("success") == 0


def test_department_provenance_flow(collector, aggregator):
    """Blocker 5: Verify department_id provenance Task -> Worker -> Telemetry."""
    execution_id = "test-exec-789"
    department_id = "SEC-OPS"
    
    ev = TelemetryEnvelope.create(
        component="manager",
        event_type="task.created",
        source="execution",
        execution_id=execution_id,
        department_id=department_id,
        status="QUEUED"
    )
    
    collector.emit(ev)
    
    matrix = aggregator.get_matrix()
    departments = matrix.get("departments", {})
    
    assert department_id in departments
    assert departments[department_id].get("total") == 1


def test_telemetry_scrubbing(collector):
    """Blocker 6: Ensure TelemetryCollector applies scrubbing."""
    execution_id = "test-exec-999"
    sensitive_data = {
        "github_token": "ghp_xxxxxxxxxxxx",
        "aws_secret_key": "AKIAxxxxxxxxxxxx",
        "public_field": "hello world",
        "nested": {
            "password": "supersecretpassword",
            "safe_val": 42
        }
    }
    
    ev = TelemetryEnvelope.create(
        component="worker",
        event_type="execution.finished",
        source="execution",
        execution_id=execution_id,
        metadata=sensitive_data
    )
    
    collector.emit(ev)
    
    # Query raw to see if scrubbed
    events = collector.query({})
    assert len(events) == 1
    persisted_ev = events[0]
    
    meta = persisted_ev.metadata
    assert meta["github_token"] == "[REDACTED]"
    assert meta["aws_secret_key"] == "[REDACTED]"
    assert meta["public_field"] == "hello world"
    assert meta["nested"]["password"] == "[REDACTED]"
    assert meta["nested"]["safe_val"] == 42


def test_matrix_consistency(collector, aggregator):
    """Blocker 7: Verify global.total = sum of departments, no double-counting."""
    collector.emit(TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id="exec-1", department_id="DEPT-A", status="SUCCEEDED", routing_class="DETERMINISTIC"
    ))
    collector.emit(TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id="exec-2", department_id="DEPT-A", status="FAILED", routing_class="DETERMINISTIC"
    ))
    collector.emit(TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id="exec-3", department_id="DEPT-B", status="SUCCEEDED", routing_class="LOCAL_MODEL"
    ))
    
    matrix = aggregator.get_matrix()
    global_stats = matrix.get("global", {})
    dept_stats = matrix.get("departments", {})
    
    assert global_stats["total"] == 3
    assert global_stats["success"] == 2
    assert global_stats["failed"] == 1
    
    assert dept_stats["DEPT-A"]["total"] == 2
    assert dept_stats["DEPT-A"]["success"] == 1
    assert dept_stats["DEPT-B"]["total"] == 1
    
    # Consistency check
    assert global_stats["total"] == sum(d["total"] for d in dept_stats.values())
    assert global_stats["success"] == sum(d["success"] for d in dept_stats.values())


def test_collector_filters(collector, aggregator):
    """Blocker 8: Verify filter behavior on query and matrix."""
    collector.emit(TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id="exec-1", department_id="DEPT-A"
    ))
    collector.emit(TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id="exec-2", department_id="DEPT-B"
    ))
    
    # Filter by department_id
    filtered_events = collector.query({"department_id": "DEPT-A"})
    assert len(filtered_events) == 1
    assert filtered_events[0].execution_id == "exec-1"
    
    # Filter by execution_id
    filtered_events = collector.query({"execution_id": "exec-2"})
    assert len(filtered_events) == 1
    assert filtered_events[0].department_id == "DEPT-B"


def test_processing_matrix_http_boundary(collector, aggregator):
    """Blocker 9: Test HTTP endpoint proxy structures."""
    from runtime.admin.routes import AdminRouter
    
    collector.emit(TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id="exec-1", department_id="DEPT-A", status="SUCCEEDED", routing_class="DETERMINISTIC"
    ))

    router = AdminRouter({
        'telemetry_aggregator': aggregator
    })
    
    class MockParsedQuery:
        def __init__(self, query_string):
            self.query = query_string

    # Test /api/processing/matrix
    router.handle_processing_matrix(MockParsedQuery(""))
    response = router.context.get('direct_json_response')
    
    assert response is not None
    assert "global" in response
    assert "departments" in response
    assert response["global"]["total"] == 1

    # Test /api/processing/events
    router.handle_processing_events(MockParsedQuery("limit=10"))
    response_events = router.context.get('direct_json_response')
    
    assert response_events is not None
    assert isinstance(response_events, list)
    assert len(response_events) == 1
    assert response_events[0].get("execution_id") == "exec-1"
