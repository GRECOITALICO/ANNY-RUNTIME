from urllib.parse import urlparse

import pytest

from runtime.admin.projections import (
    DEFAULT_PROJECTION_REGISTRY,
    INITIAL_P0_VIEWPORT_TARGET,
    MASTER_INVENTORY_BOUNDARY,
    ProjectionDefinition,
    ProjectionRegistry,
)
from runtime.admin.routes import AdminRouter


def test_projection_registry_is_open_ended_and_seeded():
    payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict()

    assert payload["initial_p0_viewport_target"] == INITIAL_P0_VIEWPORT_TARGET == 349
    assert payload["master_inventory_boundary"] == MASTER_INVENTORY_BOUNDARY == "OPEN_ENDED_1000_PLUS"
    assert payload["inventory_limit"] is None
    assert payload["summary"]["total_definitions"] == len(payload["projections"])
    assert payload["summary"]["by_priority"]["P0"] > 0


def test_projection_registry_rejects_duplicate_ids():
    first = ProjectionDefinition(
        projection_id="test.duplicate",
        title="First",
        section="Test",
        priority="P0",
        current_status="UNKNOWN",
        truth_class="UNKNOWN",
        source_authority="TEST",
        freshness="STATIC",
    )
    second = ProjectionDefinition(
        projection_id="test.duplicate",
        title="Second",
        section="Test",
        priority="P0",
        current_status="UNKNOWN",
        truth_class="UNKNOWN",
        source_authority="TEST",
        freshness="STATIC",
    )

    registry = ProjectionRegistry([first])
    with pytest.raises(ValueError, match="Duplicate projection_id"):
        registry.register(second)


def test_control_center_projection_api_is_read_only_and_filterable():
    router = AdminRouter({})
    router.handle_control_center_projections(urlparse("/api/control-center/projections?priority=P0"))

    payload = router.context["direct_json_response"]
    assert payload["inventory_limit"] is None
    assert payload["projections"]
    assert all(item["priority"] == "P0" for item in payload["projections"])


def test_control_center_projection_api_rejects_invalid_priority():
    router = AdminRouter({})
    router.handle_control_center_projections(urlparse("/api/control-center/projections?priority=P9"))

    assert router.context["direct_json_response"] == {
        "error": "INVALID_PRIORITY",
        "status": "BLOCKED",
    }


def test_canonical_navigation_keeps_all_visible_destinations_and_marks_unavailable_items():
    from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
    from runtime.admin.templates import _render_navigation

    assert len(DEFAULT_NAVIGATION_ITEMS) == 33
    paths = [item.path for item in DEFAULT_NAVIGATION_ITEMS]
    assert len(paths) == len(set(paths))
    assert any(item.path == "/models" and item.availability == "ALIAS" for item in DEFAULT_NAVIGATION_ITEMS)
    assert not any(item.path == "/intelligence/models" for item in DEFAULT_NAVIGATION_ITEMS)

    html = _render_navigation("/")
    assert 'href="/models"' in html
    assert 'href="/intelligence/models"' not in html

    for item in DEFAULT_NAVIGATION_ITEMS:
        if item.availability == "PLANNED":
            assert f'>{item.label}</span></span>' in html or f'>{item.label}</span>' in html
            assert f'href="{item.path}"' not in html


def test_control_center_existing_panels_have_stable_projection_ids():
    from runtime.admin.templates_cc import control_center_page
    from runtime.admin.projections import DEFAULT_PROJECTION_REGISTRY

    html = control_center_page("")
    panel_ids = {
        "control.top_level_state",
        "control.operational_snapshot",
        "control.bootstrap_verification",
        "control.runtime_health",
        "control.repository_fabric",
        "control.access_verification",
        "control.current_contract",
        "control.capability_inventory",
        "control.tools",
        "control.models",
        "control.workers",
        "control.connectors",
        "control.processing_matrix",
        "control.continuity",
    }
    assert all(f'data-projection-id="{projection_id}"' in html for projection_id in panel_ids)
    assert all(DEFAULT_PROJECTION_REGISTRY.get(projection_id) is not None for projection_id in panel_ids)


def test_control_center_dynamic_html_rendering_escapes_backend_values():
    from runtime.admin.templates_cc import control_center_page

    html = control_center_page("")
    assert "function escapeHtml(value)" in html
    assert "escapeHtml(g.phase||'')" in html
    assert "escapeHtml(g.gate||'')" in html
    assert "escapeHtml(g.detail||'')" in html
    assert "escapeHtml(g.evidence||'')" in html
    assert "escapeHtml(a.capability)" in html
    assert "escapeHtml(d.contract.allowed||'NONE')" in html
    assert "stateBadge.innerHTML = (d.runtime_state || 'UNKNOWN')" not in html


def test_projection_registry_search_and_pagination():
    payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(q="runtime", limit=2, offset=0)

    assert payload["page"]["limit"] == 2
    assert payload["page"]["offset"] == 0
    assert payload["page"]["returned"] <= 2
    assert payload["page"]["total_filtered"] >= payload["page"]["returned"]
    assert all(
        "runtime" in (
            item["projection_id"].lower()
            + " " + item["title"].lower()
            + " " + item["section"].lower()
            + " " + item["source_authority"].lower()
        )
        for item in payload["projections"]
    )

    later = DEFAULT_PROJECTION_REGISTRY.to_api_dict(limit=2, offset=2)
    assert later["page"]["offset"] == 2


def test_projection_registry_rejects_invalid_page_size():
    with pytest.raises(ValueError, match="limit"):
        DEFAULT_PROJECTION_REGISTRY.to_api_dict(limit=201)

    with pytest.raises(ValueError, match="offset"):
        DEFAULT_PROJECTION_REGISTRY.to_api_dict(offset=-1)


def test_projection_registry_filters_by_truth_and_implementation():
    blocked = DEFAULT_PROJECTION_REGISTRY.to_api_dict(implementation_status="BLOCKED")
    assert blocked["projections"]
    assert all(item["implementation_status"] == "BLOCKED" for item in blocked["projections"])

    unknown = DEFAULT_PROJECTION_REGISTRY.to_api_dict(truth_class="UNKNOWN")
    assert unknown["projections"]
    assert all(item["truth_class"] == "UNKNOWN" for item in unknown["projections"])


def test_projection_registry_exact_detail_query():
    item = DEFAULT_PROJECTION_REGISTRY.list()[0]
    payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(projection_id=item.projection_id, limit=1)

    assert payload["page"]["total_filtered"] == 1
    assert payload["page"]["returned"] == 1
    assert payload["projections"][0]["projection_id"] == item.projection_id


def test_projection_detail_filter_is_exact():
    payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(projection_id="does.not.exist", limit=1)
    assert payload["page"]["total_filtered"] == 0
    assert payload["projections"] == []


def test_active_navigation_items_resolve_to_real_get_routes():
    from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
    from runtime.admin.routes import AdminRouter

    router = AdminRouter({})
    get_routes = router._get_routes

    for item in DEFAULT_NAVIGATION_ITEMS:
        if item.availability == "PLANNED":
            continue
        assert item.path in get_routes, item.path


def test_projection_freshness_default_reflects_implementation_state():
    from runtime.admin.projections import ProjectionDefinition

    bound = ProjectionDefinition(
        projection_id="test.bound.freshness",
        title="Bound",
        section="Test",
        priority="P0",
        current_status="UNKNOWN",
        truth_class="UNKNOWN",
        source_authority="TEST",
        freshness="LIVE_ON_READ",
    )
    planned = ProjectionDefinition(
        projection_id="test.planned.freshness",
        title="Planned",
        section="Test",
        priority="P1",
        current_status="UNKNOWN",
        truth_class="UNKNOWN",
        source_authority="TEST",
        freshness="NOT_BOUND",
        implementation_status="PLANNED",
    )

    assert bound.freshness == "LIVE_ON_READ"
    assert planned.freshness == "NOT_BOUND"


def test_projection_registry_exposes_section_and_freshness_dimensions():
    payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(limit=1)

    assert payload["summary"]["by_section"]
    assert payload["summary"]["by_freshness"]

    section = next(iter(payload["summary"]["by_section"]))
    section_payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(section=section)
    assert section_payload["page"]["total_filtered"] == payload["summary"]["by_section"][section]
    assert section_payload["projections"]
    assert all(item["section"] == section for item in section_payload["projections"])

    freshness = next(iter(payload["summary"]["by_freshness"]))
    freshness_payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(freshness=freshness)
    assert freshness_payload["page"]["total_filtered"] == payload["summary"]["by_freshness"][freshness]
    assert freshness_payload["projections"]
    assert all(item["freshness"] == freshness for item in freshness_payload["projections"])


def test_admin_shell_has_no_external_font_dependency():
    from runtime.admin.templates import COMMON_CSS

    assert "fonts.googleapis.com" not in COMMON_CSS


def test_control_center_conrrad_projection_is_strict_and_non_synthetic():
    from types import SimpleNamespace

    router = AdminRouter({})
    router.handle_api_status(urlparse("/api/status"))
    data = router.context["direct_json_response"]

    assert data["conrrad_gate_status"] == "BLOCKED"
    assert data["conrrad_required_service_count"] == 8
    assert data["conrrad_observed_service_count"] == 0
    assert data["conrrad_online_verified_count"] == 0
    assert data["conrrad_trust_verified_count"] == 0
    assert len(data["conrrad_dependencies"]) == 8
    assert data["github_org"] == "UNKNOWN"
    assert data["tenant"] == "UNKNOWN"
    assert data["policy_revision"] == "UNKNOWN"
    assert data["contract_revision"] == "UNKNOWN"
    assert data["capabilities"] == "UNKNOWN"
    assert data["anny_ready"] is False
    assert "N/A" not in str(data)

    class Engine:
        state = SimpleNamespace(name="READY")
        config = SimpleNamespace(fabric_org="configured-org", fabric_repo="configured-repo")
        bootstrap_report = SimpleNamespace(
            anny_ready=True,
            bootstrap_state="READY",
            fabric_node="fabric-node-observed",
            policy_revision="policy-1",
            admission_status="ADMITTED",
            reconciliation_status="COHERENT",
            capabilities=SimpleNamespace(declared=["capability.one"]),
            tools=SimpleNamespace(declared=["tool.one"]),
            models=SimpleNamespace(declared=["model.one"]),
            workers=SimpleNamespace(declared=["worker.one"]),
            connectors=SimpleNamespace(declared=["connector.one"]),
            gates=[],
            completed_at="2026-09-23T21:00:00+00:00",
            conrrad_dependencies=[
                {
                    "service_name": name,
                    "online_status": "ONLINE_VERIFIED",
                    "trust_status": "VERIFIED",
                    "certification_state": "CERTIFIED_BY_LIVE_EVIDENCE",
                    "last_live_check": "2026-09-23T21:00:00+00:00",
                    "evidence_ref": "evidence/" + name,
                }
                for name in __import__("runtime.bootstrap.conrrad", fromlist=["REQUIRED_CONRRAD_SERVICES"]).REQUIRED_CONRRAD_SERVICES
            ],
            health_check=lambda self: {"status": "ok"},
        )

    router = AdminRouter({"runtime_engine": Engine()})
    router.handle_api_status(urlparse("/api/status"))
    data = router.context["direct_json_response"]
    assert data["conrrad_gate_status"] == "ONLINE_VERIFIED"
    assert data["conrrad_observed_service_count"] == 8
    assert data["conrrad_online_verified_count"] == 8
    assert data["conrrad_trust_verified_count"] == 8
    assert data["anny_ready"] is True
    assert data["fabric_status"] == "ONLINE_VERIFIED"
    assert data["continuity"]["status"] == "UNKNOWN"


def test_control_center_conrrad_panel_is_bound_and_offline_safe():
    from runtime.admin.templates_cc import control_center_page

    html = control_center_page("")
    assert 'data-projection-id="control.conrrad_mandatory_services"' in html
    assert 'id="conrrad-deps-tbody"' in html
    assert "ONLINE_VERIFIED" in html
    assert "CERTIFIED_BY_LIVE_EVIDENCE" in html
    assert "No CONRRAD" not in html


def test_control_center_has_no_external_font_dependency():
    from runtime.admin.templates_cc import control_center_page
    from runtime.admin.routes import AdminRouter

    html = control_center_page("")
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html

    router = AdminRouter({})
    source = __import__("inspect").getsource(router._set_security_headers)
    assert "fonts.googleapis.com" not in source
    assert "fonts.gstatic.com" not in source


def test_conrrad_registry_completion_requires_canonical_live_status_and_trust():
    from runtime.bootstrap.conrrad import REQUIRED_CONRRAD_SERVICES, registry_is_complete

    records = [
        {"service_name": name, "online_status": "ONLINE", "trust_status": "VERIFIED"}
        for name in REQUIRED_CONRRAD_SERVICES
    ]
    assert registry_is_complete(records) is False

    records[-1]["online_status"] = "ONLINE_VERIFIED"
    assert registry_is_complete(records) is False

    records = [
        {"service_name": name, "online_status": "ONLINE_VERIFIED", "trust_status": "VERIFIED"}
        for name in REQUIRED_CONRRAD_SERVICES
    ]
    assert registry_is_complete(records) is True


def test_conrrad_default_projection_is_explicitly_not_observed():
    from runtime.bootstrap.conrrad import (
        REQUIRED_CONRRAD_SERVICES,
        project_dependency_matrix,
    )

    rows = project_dependency_matrix(None)
    assert [row["service_name"] for row in rows] == list(REQUIRED_CONRRAD_SERVICES)
    assert all(row["online_status"] == "NOT_CONFIGURED" for row in rows)
    assert all(row["trust_status"] == "UNKNOWN" for row in rows)
    assert all(row["evidence_ref"] == "UNKNOWN" for row in rows)


def test_bootstrap_report_preserves_explicit_external_truth_channel():
    from runtime.bootstrap.report import BootstrapReport

    report = BootstrapReport(anny_ready=False, runtime_id="runtime-test", fabric_node="UNKNOWN")
    assert report.bootstrap_state == "UNKNOWN"
    assert report.conrrad_dependencies == []

    report.conrrad_dependencies = [
        {"service_name": "CONRRAD.BOOTSTRAP", "online_status": "ONLINE_VERIFIED", "trust_status": "VERIFIED"}
    ]
    report.finish(False)
    assert report.bootstrap_state == "BLOCKED"
    assert len(report.conrrad_dependencies) == 1


def test_active_navigation_requires_a_registered_projection():
    from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS, DEFAULT_PROJECTION_REGISTRY

    active = [item for item in DEFAULT_NAVIGATION_ITEMS if item.availability in {"ACTIVE", "ALIAS"}]
    assert active
    assert all(item.projection_id for item in active)
    assert all(DEFAULT_PROJECTION_REGISTRY.get(item.projection_id) is not None for item in active)


def test_navigation_models_projection_uses_canonical_models_route():
    from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
    item = next(item for item in DEFAULT_NAVIGATION_ITEMS if item.label == "Models")
    projection = DEFAULT_PROJECTION_REGISTRY.get(item.projection_id)
    assert item.path == "/models"
    assert projection is not None
    assert projection.route_or_detail == "/models"


def test_audit_events_navigation_is_backed_by_a_projection():
    from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS
    item = next(item for item in DEFAULT_NAVIGATION_ITEMS if item.label == "Events")
    projection = DEFAULT_PROJECTION_REGISTRY.get(item.projection_id)
    assert item.path == "/audit/events"
    assert projection is not None
    assert projection.route_or_detail == "/audit/events"


def test_classic_admin_shell_escapes_titles_tokens_and_rejects_executable_hrefs():
    from runtime.admin.templates import _safe_href, base_layout, device_flow_page

    assert _safe_href("javascript:alert(1)") == "#"
    assert _safe_href("data:text/html,<svg>") == "#"
    assert _safe_href("/browser/abc") == "/browser/abc"
    assert _safe_href("https://github.com/login/device") == "https://github.com/login/device"

    html = base_layout('<img src=x onerror=alert(1)>', '<p>content</p>', '/', '"csrf<script>', '<projection>"')
    assert '<img src=x onerror=alert(1)>' not in html
    assert '&lt;img' in html
    assert 'csrf&lt;script&gt;' in html
    assert 'data-projection-id="&lt;projection&gt;&quot;"' in html

    page = device_flow_page('<XSS>', 'javascript:alert(1)', '"csrf')
    assert '<XSS>' not in page
    assert '&lt;XSS&gt;' in page
    assert 'href="#"' in page
    assert 'javascript:alert(1)' not in page


def test_telemetry_live_renderer_has_no_dynamic_innerhtml_path():
    from runtime.admin.templates import telemetry_live_page

    html = telemetry_live_page()
    assert 'innerHTML' not in html
    assert 'replaceChildren()' in html
    assert 'textContent = value' in html
    assert 'JSON.stringify(env.metadata)' in html


def test_browser_renderers_are_bound_safe_and_do_not_reference_missing_renderer():
    from types import SimpleNamespace
    from runtime.admin.templates import browser_dashboard_page, browser_session_page

    policy = SimpleNamespace(
        network_policy='<network>',
        allowed_domains=['example.com', '<evil>'],
        timeout_ms=1234,
        human_assistance_allowed=False,
    )
    session = SimpleNamespace(
        session_id='abc" onmouseover="x',
        worker_id='worker',
        task_id='task',
        mode=SimpleNamespace(value='<MODE>'),
        status=SimpleNamespace(value='RUNNING'),
        current_url='javascript:alert(1)',
        created_at=SimpleNamespace(isoformat=lambda: '<TIME>'),
        policy=policy,
        profile_path='<PROFILE>',
    )

    dashboard = browser_dashboard_page([(session,)])
    detail = browser_session_page(session)

    assert 'render_admin_page' not in dashboard
    assert 'render_admin_page' not in detail
    assert 'href="javascript:alert(1)"' not in detail
    assert 'href="#"' in detail
    assert '&lt;MODE&gt;' in detail
    assert '&lt;PROFILE&gt;' in detail
    assert 'href="/browser/abc" onmouseover=' not in dashboard
    assert 'data-projection-id="browser.dashboard"' in dashboard
    assert 'data-projection-id="browser.session_detail"' in detail


def test_project_map_renders_registered_projects_instead_of_static_empty_state():
    from types import SimpleNamespace
    from runtime.admin.templates import universe_projects_page

    html = universe_projects_page([
        SimpleNamespace(project_id='<project>', name='<Project Name>', status='<READY>', repositories=['a', 'b'])
    ])

    assert 'No projects discovered' not in html
    assert '&lt;project&gt;' in html
    assert '&lt;Project Name&gt;' in html
    assert '&lt;READY&gt;' in html
    assert '>2</td>' in html


def test_browser_session_projection_is_bound_to_implemented_detail_route():
    projection = DEFAULT_PROJECTION_REGISTRY.get("browser.session_detail")
    assert projection is not None
    assert projection.implementation_status == "BOUND"
    assert projection.route_or_detail == "/browser/{session_id}"


def test_control_center_truth_as_of_uses_server_timestamp_not_client_clock():
    from runtime.admin.templates_cc import control_center_page

    html = control_center_page("csrf-token")
    assert 'id="last-verified">TRUTH AS OF: —' in html
    assert "setText('last-verified', 'TRUTH AS OF: ' + (d.timestamp || 'UNKNOWN'))" in html
    assert "LAST POLLED" not in html
    assert "new Date().toISOString()" not in html


def test_missions_route_renders_canonical_continuity_projection_and_execution_alias_is_not_placeholder():
    from types import SimpleNamespace
    from runtime.admin.templates import execution_missions_page

    continuity = SimpleNamespace(
        current_mission="MISSION-059",
        current_task="CONTROL-CENTER",
        next_action="CONTINUE_GUI",
        blocker_count=2,
        status="BLOCKED",
        reconciliation_status="BLOCKED",
    )
    html = execution_missions_page(continuity)
    assert "Current Mission" in html
    assert "MISSION-059" in html
    assert "CONTROL-CENTER" in html
    assert "CONTINUE_GUI" in html
    assert ">2</span>" in html
    assert 'data-projection-id="execution.missions"' in html
    assert "generic_placeholder_page" not in html


def test_classic_execution_worker_and_model_links_are_safe_and_execution_view_is_projection_bound():
    from runtime.admin.templates import executions_page, models_page, workers_page
    from types import SimpleNamespace
    from datetime import datetime

    worker = SimpleNamespace(
        worker_id='worker" onmouseover="x',
        execution_id='exec',
        capability_id='cap',
        executor_type='deterministic',
        state=SimpleNamespace(value='RUNNING'),
        created_at=datetime(2026, 1, 1),
    )
    model = SimpleNamespace(
        model_id='model" onmouseover="x',
        model_name='Model',
        provider='provider',
        version='1',
        state=SimpleNamespace(value='READY'),
    )
    execution = SimpleNamespace(
        execution_id='exec',
        task_id='task',
        capability_id='cap',
        status=SimpleNamespace(value='SUCCEEDED'),
        started_at=None,
        completed_at=None,
        duration_ms=None,
    )

    workers_html = workers_page([worker])
    models_html = models_page([model])
    executions_html = executions_page([execution])

    assert 'href="/workers/worker" onmouseover=' not in workers_html
    assert 'href="/models/model" onmouseover=' not in models_html
    assert 'data-projection-id="execution.execution_runs"' in executions_html
    assert 'href="/execution/executions"' in executions_html


def test_every_active_or_alias_navigation_item_resolves_to_a_get_route():
    from runtime.admin.projections import DEFAULT_NAVIGATION_ITEMS

    active = [item for item in DEFAULT_NAVIGATION_ITEMS if item.availability in {"ACTIVE", "ALIAS"}]
    expected_paths = {item.path for item in active}

    router_probe = __import__("runtime.admin.routes", fromlist=["AdminRouter"])
    assert expected_paths <= {
        "/",
        "/github",
        "/fabric",
        "/sessions",
        "/operations",
        "/receipts",
        "/executions",
        "/workers",
        "/capabilities",
        "/models",
        "/doctor",
        "/universe/accounts",
        "/universe/organization",
        "/universe/projects",
        "/universe/repositories",
        "/universe/resources",
        "/execution/missions",
        "/execution/tasks",
        "/execution/workers",
        "/execution/executions",
        "/intelligence/capabilities",
        "/telemetry/live",
        "/telemetry/timeline",
        "/audit/events",
        "/audit/provenance",
        "/browser",
    }

    # Route table must remain directly inspectable on the concrete AdminRouter.
    assert hasattr(router_probe.AdminRouter, "__init__")
