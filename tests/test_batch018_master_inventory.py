"""Batch 018: source-authority inventory controls are registry-derived."""

from urllib.parse import urlparse

from runtime.admin.projections import DEFAULT_PROJECTION_REGISTRY
from runtime.admin.routes import AdminRouter
from runtime.admin.templates_cc import control_center_page


def test_batch018_source_authority_facet_is_complete_and_filterable():
    payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(limit=1)
    authorities = payload["summary"]["by_source_authority"]

    assert authorities
    assert sum(authorities.values()) == payload["summary"]["total_definitions"]

    authority = next(iter(authorities))
    filtered = DEFAULT_PROJECTION_REGISTRY.to_api_dict(
        source_authority=authority.lower(),
    )
    assert filtered["filters"]["source_authority"] == authority.lower()
    assert filtered["page"]["total_filtered"] == authorities[authority]
    assert all(item["source_authority"] == authority for item in filtered["projections"])


def test_batch018_source_authority_filter_is_exposed_by_api_and_control_center():
    router = AdminRouter({})
    router.handle_control_center_projections(
        urlparse("/api/control-center/projections?source_authority=RUNTIME_ENGINE")
    )

    payload = router.context["direct_json_response"]
    assert payload["filters"]["source_authority"] == "RUNTIME_ENGINE"
    assert payload["projections"]
    assert all(item["source_authority"] == "RUNTIME_ENGINE" for item in payload["projections"])
    html = control_center_page("")
    assert 'id="projection-source-filter"' in html
    assert "source_authority" in html
