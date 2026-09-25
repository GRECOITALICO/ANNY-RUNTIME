"""Focused regression tests for Control Center Master Inventory Batch 003."""
import pytest
from runtime.admin.projections import default_projection_registry

def test_batch003_projection_registry_counts_and_invariants():
    reg = default_projection_registry()
    items = reg.list()
    assert len(items) >= 115

    summary = reg.summary()
    assert summary["total_definitions"] >= 115
    assert summary["by_priority"]["P0"] == 42
    assert summary["by_priority"]["P1"] >= 57
    assert summary["by_priority"]["P2"] >= 16
    assert summary["by_priority"]["P3"] == 0

    assert summary["by_implementation_status"]["BOUND"] >= 59
    assert summary["by_implementation_status"]["PARTIAL"] == 13
    assert summary["by_implementation_status"]["BLOCKED"] == 3
    assert summary["by_implementation_status"]["PLANNED"] >= 40

    # Ensure no duplicates
    ids = [p.projection_id for p in items]
    assert len(ids) == len(set(ids))

def test_batch003_exact_projection_definitions_present():
    reg = default_projection_registry()
    batch_003_ids = [
        "processing.events",
        "events.bus",
        "journal.operations",
        "journal.missions",
        "security.grants",
        "security.active_context",
        "capability.gate_grants",
        "secrets.references",
        "execution.processes",
        "workspace.detail",
        "orchestration.routing_decisions",
        "orchestration.execution_plans",
        "sandbox.policies",
        "compute.remote_profiles",
        "compute.remote_sessions",
        "session.leases",
        "runtime.generation_fencing",
        "runtime.enrollment",
        "continuity.mutation_contract",
        "filesystem.workspace_service",
    ]
    for pid in batch_003_ids:
        proj = reg.get(pid)
        assert proj is not None, f"Missing projection: {pid}"
        assert proj.projection_id == pid
        assert proj.source_authority != ""
        assert proj.title != ""

def test_batch003_panel_binding_processing_events():
    reg = default_projection_registry()
    p = reg.get("processing.events")
    assert p is not None
    assert p.implementation_status == "BOUND"
    assert p.route_or_detail == "/api/processing/events"
    assert p.source_authority == "TELEMETRY_AGGREGATOR"
    assert p.truth_class == "UNKNOWN"

def test_batch003_filtering_and_pagination():
    reg = default_projection_registry()
    
    # Priority filtering
    p0_res = reg.to_api_dict(priority="P0")
    assert p0_res["page"]["total_filtered"] == 42
    
    p1_res = reg.to_api_dict(priority="P1")
    assert p1_res["page"]["total_filtered"] >= 57
    
    p2_res = reg.to_api_dict(priority="P2")
    assert p2_res["page"]["total_filtered"] >= 16
    
    # Status filtering
    planned_res = reg.to_api_dict(implementation_status="PLANNED")
    assert planned_res["page"]["total_filtered"] >= 40
    
    bound_res = reg.to_api_dict(implementation_status="BOUND")
    assert bound_res["page"]["total_filtered"] >= 59
    
    # Exact projection ID query
    single = reg.to_api_dict(projection_id="processing.events")
    assert single["page"]["total_filtered"] == 1
    assert single["projections"][0]["projection_id"] == "processing.events"
    
    # Pagination
    page1 = reg.to_api_dict(limit=10, offset=0)
    assert len(page1["projections"]) == 10
    assert page1["page"]["has_more"] is True
    assert page1["page"]["total_filtered"] >= 115
