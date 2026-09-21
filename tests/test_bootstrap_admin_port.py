from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.request import Request

from runtime.bootstrap.gates import ReadinessGate
from runtime.bootstrap.planes import ThreePlaneBootstrap
from runtime.bootstrap.report import BootstrapReport


def _bootstrap(config):
    return ThreePlaneBootstrap(
        data_dir="/tmp",
        github_client=None,
        fabric_client=None,
        continuity_engine=Mock(),
        config=config,
    )


def _response():
    response = Mock()
    response.status = 200
    response.read.return_value = b'{"state": "ADMIN_MODE"}'
    response.__enter__ = lambda self: self
    response.__exit__ = Mock(return_value=False)
    return response


def test_runtime_probe_uses_configured_admin_port():
    bs = _bootstrap(SimpleNamespace(admin_host="127.0.0.1", admin_port=4545))
    report = BootstrapReport(anny_ready=False, runtime_id="RT-1", fabric_node="UNKNOWN")

    with patch("urllib.request.urlopen", return_value=_response()) as opener:
        assert bs._gate_runtime_reachable(report) is True

    request = opener.call_args.args[0]
    assert isinstance(request, Request)
    assert request.full_url == "http://127.0.0.1:4545/api/status"
    assert report.get_gate(ReadinessGate.RUNTIME_REACHABLE).passed is True


def test_runtime_probe_uses_runtime_default_port_when_config_omits_port():
    bs = _bootstrap(SimpleNamespace(admin_host="127.0.0.1"))
    report = BootstrapReport(anny_ready=False, runtime_id="RT-1", fabric_node="UNKNOWN")

    with patch("urllib.request.urlopen", return_value=_response()) as opener:
        assert bs._gate_runtime_reachable(report) is True

    request = opener.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:3643/api/status"


def test_runtime_probe_uses_configured_admin_host():
    bs = _bootstrap(SimpleNamespace(admin_host="localhost", admin_port=4545))
    assert bs._admin_url("/api/status") == "http://localhost:4545/api/status"
