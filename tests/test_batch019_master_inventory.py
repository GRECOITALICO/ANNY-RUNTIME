"""Batch 019: Control Center source-authority grounding remains registry-derived."""

from urllib.parse import urlparse

from runtime.admin.projections import DEFAULT_PROJECTION_REGISTRY
from runtime.admin.routes import AdminRouter
from runtime.admin.templates_cc import control_center_page


def test_batch019_filtered_summary_is_exactly_derived_from_registered_items():
    authority = "RUNTIME_ENGINE"
    payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(source_authority=authority)
    filtered = payload["filtered_summary"]

    assert payload["projections"]
    assert filtered["total_definitions"] == payload["page"]["total_filtered"]
    assert sum(filtered["by_implementation_status"].values()) == filtered["total_definitions"]
    assert sum(filtered["by_truth_class"].values()) == filtered["total_definitions"]
    assert filtered["by_source_authority"] == {authority: filtered["total_definitions"]}


def test_batch019_api_and_ui_expose_filtered_operator_truth_without_live_claims():
    router = AdminRouter({})
    router.handle_control_center_projections(
        urlparse("/api/control-center/projections?source_authority=RUNTIME_ENGINE")
    )
    payload = router.context["direct_json_response"]

    assert "filtered_summary" in payload
    assert payload["filtered_summary"]["by_truth_class"]["UNKNOWN"] >= 0
    html = control_center_page("")
    assert "FILTERED BOUND=" in html
    assert "FILTERED UNKNOWN=" in html
