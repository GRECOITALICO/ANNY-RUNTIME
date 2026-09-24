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
