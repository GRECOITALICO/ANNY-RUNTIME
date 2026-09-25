"""Focused regression tests for Control Center Master Inventory Batch 005."""
import pytest
from runtime.admin.projections import default_projection_registry

def test_batch005_projection_registry_counts_and_invariants():
    reg = default_projection_registry()
    items = reg.list()
    assert len(items) >= 148

    summary = reg.summary()
    assert summary["total_definitions"] >= 148
    assert summary["by_priority"]["P0"] >= 42
    assert summary["by_priority"]["P1"] >= 86
    assert summary["by_priority"]["P2"] >= 20
    assert summary["by_priority"]["P3"] == 0

    assert summary["by_implementation_status"]["BOUND"] >= 64
    assert summary["by_implementation_status"]["PARTIAL"] <= 13
    assert summary["by_implementation_status"]["BLOCKED"] == 3
    assert summary["by_implementation_status"]["PLANNED"] >= 68

    assert summary["by_freshness"]["LIVE_ON_READ"] >= 64
    assert summary["by_freshness"]["NOT_BOUND"] >= 84

    # Ensure no duplicates
    ids = [p.projection_id for p in items]
    assert len(ids) == len(set(ids))

def test_batch005_exact_projection_definitions_present():
    reg = default_projection_registry()
    batch_005_ids = [
        "api.status",
        "continuity.bootstrap_api",
        "control.projections_api",
        "telemetry.stream_api",
        "projects.registry",
        "accounts.registry",
        "compute.runtime_capabilities",
        "compute.resource_discovery",
        "mcp.gateway",
        "tools.builtins",
        "security.secure_tool_registry",
        "security.authorization_store",
        "execution.manager",
        "execution.selector",
        "execution.runtime_policy",
        "intelligence.benchmark_runner",
        "intelligence.grading_engine",
        "intelligence.evidence_builder",
        "sync.package_verifier",
        "sync.github_source",
        "telemetry.aggregator",
        "browser.broker_server",
    ]
    assert len(batch_005_ids) == 22
    for pid in batch_005_ids:
        proj = reg.get(pid)
        assert proj is not None, f"Missing projection: {pid}"
        assert proj.projection_id == pid
        assert proj.source_authority != ""
        assert proj.title != ""

def test_batch005_panel_binding_and_route_improvements():
    reg = default_projection_registry()
    
    # 1. Existing projection route binding improvement: runtime.health
    health = reg.get("runtime.health")
    assert health is not None
    assert health.implementation_status == "BOUND"
    assert health.route_or_detail == "/health/live"
    assert health.priority == "P0"
    
    # 2. Existing projection route binding improvement: runtime.readiness
    readiness = reg.get("runtime.readiness")
    assert readiness is not None
    assert readiness.implementation_status == "BOUND"
    assert readiness.route_or_detail == "/health/ready"
    assert readiness.priority == "P0"

    # 3. New live API bindings (BOUND)
    api_status = reg.get("api.status")
    assert api_status is not None
    assert api_status.implementation_status == "BOUND"
    assert api_status.route_or_detail == "/api/status"
    
    boot_api = reg.get("continuity.bootstrap_api")
    assert boot_api is not None
    assert boot_api.implementation_status == "BOUND"
    assert boot_api.route_or_detail == "/api/v1/continuity/bootstrap"
    
    proj_api = reg.get("control.projections_api")
    assert proj_api is not None
    assert proj_api.implementation_status == "BOUND"
    assert proj_api.route_or_detail == "/api/control-center/projections"
    
    stream_api = reg.get("telemetry.stream_api")
    assert stream_api is not None
    assert stream_api.implementation_status == "BOUND"
    assert stream_api.route_or_detail == "/api/v1/telemetry/stream"

def test_batch005_filtering_and_pagination():
    reg = default_projection_registry()
    
    # Priority filtering
    p0_res = reg.to_api_dict(priority="P0")
    assert p0_res["page"]["total_filtered"] >= 42
    
    p1_res = reg.to_api_dict(priority="P1")
    assert p1_res["page"]["total_filtered"] >= 86
    
    p2_res = reg.to_api_dict(priority="P2")
    assert p2_res["page"]["total_filtered"] >= 20
    
    # Status filtering
    planned_res = reg.to_api_dict(implementation_status="PLANNED")
    assert planned_res["page"]["total_filtered"] >= 68
    
    bound_res = reg.to_api_dict(implementation_status="BOUND")
    assert bound_res["page"]["total_filtered"] >= 64
    
    # Exact projection ID query
    single = reg.to_api_dict(projection_id="api.status")
    assert single["page"]["total_filtered"] == 1
    assert single["projections"][0]["projection_id"] == "api.status"
    
    # Pagination
    page1 = reg.to_api_dict(limit=10, offset=0)
    assert len(page1["projections"]) == 10
    assert page1["page"]["has_more"] is True
    assert page1["page"]["total_filtered"] >= 148
