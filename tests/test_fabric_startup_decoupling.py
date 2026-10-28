"""Focused regressions for local startup with an unconfigured Repository Fabric."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch
import urllib.error

import pytest

from runtime.admin.routes import AdminRouter
from runtime.admin.server import build_fabric_client
from runtime.bootstrap.gates import ReadinessGate
from runtime.bootstrap.planes import ThreePlaneBootstrap
from runtime.fabric.github_adapter import GitHubFabricAdapter


@pytest.mark.parametrize(
    "fabric_org,fabric_repo",
    [(None, None), ("", ""), ("only-org", None), (None, "only-repo"), (" ", "repo")],
)
def test_unconfigured_or_partial_fabric_binding_returns_none(caplog, fabric_org, fabric_repo):
    config = SimpleNamespace(fabric_org=fabric_org, fabric_repo=fabric_repo)
    caplog.set_level(logging.INFO)

    assert build_fabric_client(Mock(), config) is None
    assert "NOT_CONFIGURED" in caplog.text


def test_no_github_client_keeps_existing_absent_fabric_behavior():
    assert build_fabric_client(None, SimpleNamespace(fabric_org="org", fabric_repo="repo")) is None


def test_complete_fabric_binding_constructs_real_adapter():
    config = SimpleNamespace(fabric_org="configured-org", fabric_repo="configured-repo")

    adapter = build_fabric_client(Mock(), config)

    assert isinstance(adapter, GitHubFabricAdapter)
    assert adapter.org == "configured-org"
    assert adapter.repo == "configured-repo"


def test_fabric_route_exposes_missing_binding_as_not_configured(monkeypatch):
    rendered = {}
    engine = SimpleNamespace(config=SimpleNamespace(fabric_org=None, fabric_repo=None))
    github_manager = SimpleNamespace(has_token=lambda: True)
    router = AdminRouter({
        "runtime_engine": engine,
        "github_manager": github_manager,
        "secret_backend": object(),
    })

    def render(status, _csrf):
        rendered["status"] = status
        return "fabric-page"

    monkeypatch.setattr("runtime.admin.routes.fabric_page", render)

    assert router.handle_fabric(None) == "fabric-page"
    assert rendered["status"]["fabric_status"] == "NOT_CONFIGURED"


def test_bootstrap_without_fabric_remains_fail_closed(tmp_path):
    identity = SimpleNamespace(runtime_id="runtime-test", _private_key=b"x" * 32)
    bootstrap = ThreePlaneBootstrap(
        data_dir=str(tmp_path),
        github_client=Mock(),
        fabric_client=None,
        continuity_engine=None,
        config=SimpleNamespace(fabric_org=None, fabric_repo=None, admin_host="127.0.0.1", admin_port=3643),
    )

    with patch("runtime.bootstrap.planes.RuntimeIdentity.load", return_value=identity), patch(
        "runtime.bootstrap.planes.urllib.request.urlopen",
        side_effect=urllib.error.URLError("no local runtime started"),
    ):
        report = bootstrap.resolve()

    assert report.anny_ready is False
    for gate in (
        ReadinessGate.FABRIC_REACHABLE,
        ReadinessGate.FABRIC_IDENTITY_VERIFIED,
        ReadinessGate.FABRIC_TRUST_VERIFIED,
        ReadinessGate.FABRIC_TENANT_BOUND,
        ReadinessGate.FABRIC_STATE_READABLE,
        ReadinessGate.FABRIC_PROVENANCE_VALID,
        ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD,
        ReadinessGate.RUNTIME_ADMITTED,
    ):
        assert report.get_gate(gate).passed is False
