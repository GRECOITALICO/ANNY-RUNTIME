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
