"""Focused regression tests for Control Center Master Inventory Batch 004."""
import pytest
from runtime.admin.projections import default_projection_registry

def test_batch004_projection_registry_counts_and_invariants():
    reg = default_projection_registry()
    items = reg.list()
    assert len(items) == 126

    summary = reg.summary()
    assert summary["total_definitions"] == 126
    assert summary["by_priority"]["P0"] == 42
    assert summary["by_priority"]["P1"] == 66
    assert summary["by_priority"]["P2"] == 18
    assert summary["by_priority"]["P3"] == 0

    assert summary["by_implementation_status"]["BOUND"] == 60
    assert summary["by_implementation_status"]["PARTIAL"] == 13
    assert summary["by_implementation_status"]["BLOCKED"] == 3
    assert summary["by_implementation_status"]["PLANNED"] == 50

    assert summary["by_freshness"]["LIVE_ON_READ"] == 60
    assert summary["by_freshness"]["NOT_BOUND"] == 66

    # Ensure no duplicates
    ids = [p.projection_id for p in items]
    assert len(ids) == len(set(ids))

def test_batch004_exact_projection_definitions_present():
    reg = default_projection_registry()
    batch_004_ids = [
        "admin.restart",
        "intelligence.scorecards",
        "intelligence.benchmark_cases",
        "intelligence.failure_records",
        "intelligence.implementation_profiles",
        "intelligence.capability_taxonomy",
        "security.context_guard",
        "security.execution_context",
        "security.authorized_pipeline",
        "security.authority_validator",
        "shell.executor",
    ]
    for pid in batch_004_ids:
        proj = reg.get(pid)
        assert proj is not None, f"Missing projection: {pid}"
        assert proj.projection_id == pid
        assert proj.source_authority != ""
        assert proj.title != ""

def test_batch004_panel_binding_and_route_improvements():
    reg = default_projection_registry()
    
    # 1. Existing projection route binding improvement
    boot = reg.get("control.bootstrap_verification")
    assert boot is not None
    assert boot.implementation_status == "BOUND"
    assert boot.route_or_detail == "/api/bootstrap/verify"
    assert boot.source_authority == "BOOTSTRAP_ENGINE"
    
    # 2. New bound administrative action
    restart = reg.get("admin.restart")
    assert restart is not None
    assert restart.implementation_status == "BOUND"
    assert restart.route_or_detail == "/admin/restart"
    assert restart.source_authority == "RUNTIME_ADMIN"

def test_batch004_filtering_and_pagination():
    reg = default_projection_registry()
    
    # Priority filtering
    p0_res = reg.to_api_dict(priority="P0")
    assert p0_res["page"]["total_filtered"] == 42
    
    p1_res = reg.to_api_dict(priority="P1")
    assert p1_res["page"]["total_filtered"] == 66
    
    p2_res = reg.to_api_dict(priority="P2")
    assert p2_res["page"]["total_filtered"] == 18
    
    # Status filtering
    planned_res = reg.to_api_dict(implementation_status="PLANNED")
    assert planned_res["page"]["total_filtered"] == 50
    
    bound_res = reg.to_api_dict(implementation_status="BOUND")
    assert bound_res["page"]["total_filtered"] == 60
    
    # Exact projection ID query
    single = reg.to_api_dict(projection_id="admin.restart")
    assert single["page"]["total_filtered"] == 1
    assert single["projections"][0]["projection_id"] == "admin.restart"
    
    # Pagination
    page1 = reg.to_api_dict(limit=10, offset=0)
    assert len(page1["projections"]) == 10
    assert page1["page"]["has_more"] is True
    assert page1["page"]["total_filtered"] == 126
