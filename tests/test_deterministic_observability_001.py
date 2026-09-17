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
    """Blocker 9: Test real HTTP endpoint proxy structures."""
    import threading
    import urllib.request
    import json
    import time
    from runtime.admin.server import AdminServer
    
    collector.emit(TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id="exec-1", department_id="DEPT-A", status="SUCCEEDED", routing_class="DETERMINISTIC"
    ))

    # We need dummy managers for AdminServer
    class DummyAuth:
        ttl_seconds = 3600
        def validate(self, session_id):
            return type('Session', (), {'scope': 'FULL', 'username': 'admin', 'csrf_token': 'dummy_csrf'})()
        def create_session(self, username):
            return type('Session', (), {'admin_session_id': 'dummy', 'scope': 'FULL', 'username': username, 'csrf_token': 'dummy_csrf'})()
    
    # Run a real HTTP server on a random port
    server = AdminServer("127.0.0.1", 0, auth_manager=DummyAuth(), audit_manager=None, github_manager=None)
    server.admin_context['telemetry_aggregator'] = aggregator
    server.start()
    
    # Give the thread a moment to bind
    time.sleep(0.1)
    port = server.server4.server_port
    
    try:
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        
        # Test /api/processing/matrix via real HTTP
        req = urllib.request.Request(f"http://localhost:{port}/api/processing/matrix")
        req.add_header("Cookie", "admin_session=dummy")
        with opener.open(req) as resp:
            assert resp.status == 200
            response = json.loads(resp.read().decode())
            assert "global" in response
            assert "departments" in response
            assert response["global"]["total"] == 1

        # Test /api/processing/events via real HTTP
        req2 = urllib.request.Request(f"http://localhost:{port}/api/processing/events?limit=10")
        req2.add_header("Cookie", "admin_session=dummy")
        with opener.open(req2) as resp2:
            assert resp2.status == 200
            response_events = json.loads(resp2.read().decode())
            assert isinstance(response_events, list)
            assert len(response_events) == 1
            assert response_events[0].get("execution_id") == "exec-1"
    except urllib.error.HTTPError as e:
        print("HTTP ERROR:", e.read().decode())
        raise
    finally:
        server.server4.shutdown()
        server.server4.server_close()


def test_timezone_aware_aggregation(collector, aggregator):
    """Blocker 5: Verify that timezone offsets are correctly parsed and sorted."""
    execution_id = "test-exec-tz-1"
    
    # Event 1: Emitted at 10:00:00 UTC, but recorded as 11:00:00+01:00
    ev_1 = TelemetryEnvelope.create(
        component="manager", event_type="task.routed", source="execution",
        execution_id=execution_id, status="QUEUED"
    )
    ev_1.timestamp = "2026-01-01T11:00:00+01:00" # Equivalent to 10:00:00 UTC
    
    # Event 2: Emitted at 10:05:00 UTC, recorded as 05:05:00-05:00
    ev_2 = TelemetryEnvelope.create(
        component="worker", event_type="execution.finished", source="execution",
        execution_id=execution_id, status="FAILED" # Late event shouldn't override earlier SUCCEEDED in deterministic-first latch
    )
    ev_2.timestamp = "2026-01-01T05:05:00-05:00" # Equivalent to 10:05:00 UTC
    
    # Event 3: Emitted at 09:55:00 UTC, recorded as 09:55:00Z
    ev_0 = TelemetryEnvelope.create(
        component="manager", event_type="task.created", source="execution",
        execution_id=execution_id, status="SUCCEEDED"
    )
    ev_0.timestamp = "2026-01-01T09:55:00Z" # Equivalent to 09:55:00 UTC
    
    # Insert in random order
    collector.emit(ev_2)
    collector.emit(ev_0)
    collector.emit(ev_1)
    
    # Add a malformed timestamp event
    ev_malformed = TelemetryEnvelope.create(
        component="worker", event_type="task.log", source="execution", execution_id=execution_id
    )
    ev_malformed.timestamp = "NOT A TIMESTAMP"
    collector.emit(ev_malformed)
    
    matrix = aggregator.get_matrix()
    global_stats = matrix.get("global", {})
    
    # SUCCEEDED is latched from ev_0 even though ev_2 is later chronologically and FAILED
    assert global_stats.get("success") == 1
    # latest_execution timestamp should be the one from ev_2 since it's the latest in UTC
    assert global_stats.get("latest_execution") == "2026-01-01T05:05:00-05:00"


def test_full_provenance_chain(collector):
    """Blocker 2: Real Task -> ExecutionContext -> Worker -> Telemetry provenance."""
    from runtime.execution.manager import ExecutionManager
    from runtime.workspace.ephemeral import EphemeralWorkspaceManager
    from runtime.execution.models import Task, ExecutionStatus
    
    workspace_manager = EphemeralWorkspaceManager("/tmp/ws_test_provenance")
    manager = ExecutionManager(
        workspace_manager=workspace_manager,
        telemetry_collector=collector
    )
    
    class MockRegistry:
        def get(self, cap_id):
            from runtime.execution.capability import CapabilityDefinition
            return CapabilityDefinition(
                capability_id=cap_id,
                name="Test Cap",
                description="Test",
                family="test",
                version="1.0.0",
                enabled=True,
                side_effect="read",
                risk_level="LOW",
                deterministic_allowed=True,
                inference_required=False,
                required_tools=[],
                network_policy="none",
                filesystem_policy="readonly",
                max_runtime=30,
                max_output=1024,
                evidence_required=False,
                preferred_executor="DETERMINISTIC",
                fallback_executor=None
            )
            
    manager.registry = MockRegistry()
    
    # Submit task, this goes through manager -> context -> worker
    task = Task(
        task_id="task-provenance-1",
        account_id="acc-1",
        project_id="proj-1",
        department_id="DEPT-1",
        capability_id="cap-test",
        input={"test": "data"},
        constraints={},
        deadline=datetime.now(timezone.utc),
        workspace_policy="ephemeral",
        evidence_policy="standard",
        requested_by="test-user",
        created_at=datetime.now(timezone.utc)
    )
    
    ctx = manager.submit_task(task)
    assert ctx.execution_id is not None
    
    # We don't have to wait for full worker execution if submit_task routes it synchronously,
    # or we can inspect telemetry immediately.
    events = collector.query({"execution_id": ctx.execution_id})
    assert len(events) >= 1
    
    event_types = [e.event_type for e in events]
    assert "task.created" in event_types
    assert "task.routed" in event_types
    
    routed_event = next(e for e in events if e.event_type == "task.routed")
    assert routed_event.worker_id is not None
    assert routed_event.department_id == "DEPT-1"
