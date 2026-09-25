"""Focused regression tests for Control Center Master Inventory Batch 006."""
import pytest
from runtime.admin.projections import default_projection_registry

def test_batch006_projection_registry_counts_and_invariants():
    reg = default_projection_registry()
    items = reg.list()
    assert len(items) == 172

    summary = reg.summary()
    assert summary["total_definitions"] == 172
    assert summary["by_priority"]["P0"] == 42
    assert summary["by_priority"]["P1"] == 107
    assert summary["by_priority"]["P2"] == 23
    assert summary["by_priority"]["P3"] == 0

    assert summary["by_implementation_status"]["BOUND"] == 70
    assert summary["by_implementation_status"]["PARTIAL"] == 13
    assert summary["by_implementation_status"]["BLOCKED"] == 3
    assert summary["by_implementation_status"]["PLANNED"] == 86

    assert summary["by_freshness"]["LIVE_ON_READ"] == 70
    assert summary["by_freshness"]["NOT_BOUND"] == 102

    # Ensure no duplicates
    ids = [p.projection_id for p in items]
    assert len(ids) == len(set(ids))

def test_batch006_exact_projection_definitions_present():
    reg = default_projection_registry()
    batch_006_ids = [
        "api.bridge_tasks",
        "api.bridge_task_query",
        "api.bridge_execution_query",
        "admin.logout",
        "github.disconnect",
        "github.device_init",
        "git.service",
        "diagnostics.doctor",
        "platform.manager",
        "process.manager",
        "updater.manager",
        "fabric.github_adapter",
        "identity.enrollment",
        "identity.runtime_identity",
        "journal.operation_store",
        "journal.mission_store",
        "orchestration.kernel",
        "orchestration.frontier",
        "sandbox.manager",
        "sandbox.backend",
        "secrets.backend",
        "secrets.broker",
        "session.manager",
        "workspace.ephemeral",
    ]
    assert len(batch_006_ids) == 24
    for pid in batch_006_ids:
        proj = reg.get(pid)
        assert proj is not None, f"Missing projection: {pid}"
        assert proj.projection_id == pid
        assert proj.source_authority != ""
        assert proj.title != ""

def test_batch006_panel_binding_and_route_improvements():
    reg = default_projection_registry()
    
    # 1. Existing projection route binding improvement: universe.account_detail
    acct = reg.get("universe.account_detail")
    assert acct is not None
    assert acct.route_or_detail == "/universe/accounts/{account_id}"
    assert acct.priority == "P2"

    # 2. New bound live API bridge endpoints (BOUND)
    b_tasks = reg.get("api.bridge_tasks")
    assert b_tasks is not None
    assert b_tasks.implementation_status == "BOUND"
    assert b_tasks.route_or_detail == "/api/v1/bridge/tasks"
    
    b_tquery = reg.get("api.bridge_task_query")
    assert b_tquery is not None
    assert b_tquery.implementation_status == "BOUND"
    assert b_tquery.route_or_detail == "/api/v1/bridge/tasks/{task_id}"
    
    b_equery = reg.get("api.bridge_execution_query")
    assert b_equery is not None
    assert b_equery.implementation_status == "BOUND"
    assert b_equery.route_or_detail == "/api/v1/bridge/executions/{execution_id}"

    # 3. New bound admin & github actions (BOUND)
    logout = reg.get("admin.logout")
    assert logout is not None
    assert logout.implementation_status == "BOUND"
    assert logout.route_or_detail == "/logout"

    gh_disc = reg.get("github.disconnect")
    assert gh_disc is not None
    assert gh_disc.implementation_status == "BOUND"
    assert gh_disc.route_or_detail == "/github/disconnect"

    gh_init = reg.get("github.device_init")
    assert gh_init is not None
    assert gh_init.implementation_status == "BOUND"
    assert gh_init.route_or_detail == "/github/device/init"

def test_batch006_filtering_and_pagination():
    reg = default_projection_registry()
    
    # Priority filtering
    p0_res = reg.to_api_dict(priority="P0")
    assert p0_res["page"]["total_filtered"] == 42
    
    p1_res = reg.to_api_dict(priority="P1")
    assert p1_res["page"]["total_filtered"] == 107
    
    p2_res = reg.to_api_dict(priority="P2")
    assert p2_res["page"]["total_filtered"] == 23
    
    # Status filtering
    planned_res = reg.to_api_dict(implementation_status="PLANNED")
    assert planned_res["page"]["total_filtered"] == 86
    
    bound_res = reg.to_api_dict(implementation_status="BOUND")
    assert bound_res["page"]["total_filtered"] == 70
    
    # Exact projection ID query
    single = reg.to_api_dict(projection_id="api.bridge_tasks")
    assert single["page"]["total_filtered"] == 1
    assert single["projections"][0]["projection_id"] == "api.bridge_tasks"
    
    # Pagination
    page1 = reg.to_api_dict(limit=10, offset=0)
    assert len(page1["projections"]) == 10
    assert page1["page"]["has_more"] is True
    assert page1["page"]["total_filtered"] == 172
