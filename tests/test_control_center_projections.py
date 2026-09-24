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
