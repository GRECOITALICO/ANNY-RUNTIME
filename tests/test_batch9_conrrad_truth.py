"""Batch 9 regressions for the CONRRAD-first and truthful-status contracts.

The doubles in this module exercise only local code-path semantics. They are
not service implementations and provide no live-infrastructure evidence.
"""
import inspect
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from runtime.admin.routes import AdminRouter
from runtime.admin.server import AdminRequestHandler
from runtime.admin.sync_ui import inject_sync_controls
from runtime.bootstrap.conrrad import REQUIRED_CONRRAD_SERVICES
from runtime.bootstrap.gates import ReadinessGate
from runtime.bootstrap.planes import ThreePlaneBootstrap
from runtime.bootstrap.report import BootstrapReport
from runtime.identity.runtime_identity import RuntimeIdentity
from runtime.sync.service import SyncService


class _Response:
    status = 200

    def read(self):
        return b'{"anny_ready": false, "state": "ADMIN_MODE"}'

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _ExternalConrradDouble:
    """Bounded test double; production Runtime receives an injected client."""

    def __init__(self, preflight="ONLINE_VERIFIED", trust="VERIFIED", manifest="VERIFIED", registry=None):
        self.preflight = preflight
        self.trust = trust
        self.manifest = manifest
        self.registry = registry if registry is not None else [
            {"service_name": name, "online_status": "ONLINE_VERIFIED", "trust_status": "VERIFIED"}
            for name in REQUIRED_CONRRAD_SERVICES
        ]

    def bootstrap_preflight(self, _runtime_id):
        return {"status": self.preflight}

    def verify_manifest_and_trust(self, _runtime_id):
        return {"manifest_status": self.manifest, "trust_status": self.trust}

    def load_required_dependency_registry(self):
        return self.registry


def _bootstrap(conrrad, github=None, events=None):
    identity = Mock(spec=RuntimeIdentity)
    identity.runtime_id = "runtime-test"
    identity._private_key = b"test-only"
    identity.origin_commit = "a" * 40
    github = github or Mock()
    github.get_authenticated_principal.return_value = {"login": "test-user"}
    github.list_organizations.return_value = []
    return (
        ThreePlaneBootstrap(
            "/tmp",
            github,
            Mock(),
            Mock(status={"state": "COHERENT"}),
            config=SimpleNamespace(admin_host="127.0.0.1", admin_port=3643, fabric_org="org", fabric_repo="repo"),
            conrrad_client=conrrad,
            event_sink=events.append if events is not None else None,
        ),
        identity,
        github,
    )


def _resolve(bootstrap, identity):
    with patch("runtime.identity.runtime_identity.RuntimeIdentity.load", return_value=identity), patch(
        "urllib.request.urlopen", return_value=_Response()
    ):
        return bootstrap.resolve()


def test_b9_t01_preflight_precedes_all_github_connectivity():
    events = []
    bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(), events=events)
    _resolve(bootstrap, identity)

    assert events[0] == "CONRRAD_BOOTSTRAP_PREFLIGHT"
    assert events.index("CONRRAD_BOOTSTRAP_PREFLIGHT") < events.index("CONNECT_GITHUB")
    github.get_authenticated_principal.assert_called_once()


def test_b9_t02_unavailable_conrrad_blocks_before_github():
    bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(preflight="BLOCKED"))
    report = _resolve(bootstrap, identity)

    assert report.anny_ready is False
    assert report.bootstrap_state == "BLOCKED"
    assert report.get_gate(ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT).passed is False
    github.get_authenticated_principal.assert_not_called()
    github.list_organizations.assert_not_called()


def test_b9_t03_unverified_trust_prevents_ready_and_github():
    bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(trust="UNVERIFIED"))
    report = _resolve(bootstrap, identity)

    assert report.anny_ready is False
    assert report.get_gate(ReadinessGate.CONRRAD_MANIFEST_AND_TRUST_VERIFIED).passed is False
    github.get_authenticated_principal.assert_not_called()
    github.list_organizations.assert_not_called()


def test_b9_t04_missing_dependency_registry_blocks_without_synthesis():
    partial_registry = [{"service_name": "CONRRAD.BOOTSTRAP", "online_status": "UNKNOWN"}]
    bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(registry=partial_registry))
    report = _resolve(bootstrap, identity)

    assert report.anny_ready is False
    assert report.bootstrap_state == "BLOCKED"
    assert report.get_gate(ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED).passed is False
    assert [item["service_name"] for item in report.conrrad_dependencies] == ["CONRRAD.BOOTSTRAP"]
    github.get_authenticated_principal.assert_not_called()


def test_online_verified_registry_with_verified_trust_can_progress_to_github():
    registry = [
        {"service_name": name, "online_status": "ONLINE_VERIFIED", "trust_status": "VERIFIED"}
        for name in REQUIRED_CONRRAD_SERVICES
    ]
    bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(registry=registry))
    report = _resolve(bootstrap, identity)

    assert report.get_gate(ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED).passed is True
    github.get_authenticated_principal.assert_called_once()


def test_canonical_non_success_registry_statuses_block_before_github():
    for online_status in ("ONLINE_UNVERIFIED", "OFFLINE", "BLOCKED", "NOT_CONFIGURED", "UNKNOWN"):
        registry = [
            {"service_name": name, "online_status": online_status, "trust_status": "VERIFIED"}
            for name in REQUIRED_CONRRAD_SERVICES
        ]
        bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(registry=registry))
        report = _resolve(bootstrap, identity)

        assert report.get_gate(ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED).passed is False
        assert report.anny_ready is False
        github.get_authenticated_principal.assert_not_called()
        github.list_organizations.assert_not_called()


def test_noncanonical_registry_status_aliases_block_before_github():
    for online_status in ("READY", "AVAILABLE", "ONLINE", "PASS"):
        registry = [
            {"service_name": name, "online_status": online_status, "trust_status": "VERIFIED"}
            for name in REQUIRED_CONRRAD_SERVICES
        ]
        bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(registry=registry))
        report = _resolve(bootstrap, identity)

        assert report.get_gate(ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED).passed is False
        assert report.anny_ready is False
        github.get_authenticated_principal.assert_not_called()
        github.list_organizations.assert_not_called()


def test_complete_unknown_dependency_registry_blocks_before_github():
    unknown_registry = [
        {"service_name": name, "online_status": "UNKNOWN", "trust_status": "UNKNOWN"}
        for name in REQUIRED_CONRRAD_SERVICES
    ]
    bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(registry=unknown_registry))
    report = _resolve(bootstrap, identity)

    assert report.anny_ready is False
    assert report.get_gate(ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED).passed is False
    assert [item["service_name"] for item in report.conrrad_dependencies] == list(REQUIRED_CONRRAD_SERVICES)
    assert all(item["online_status"] == "UNKNOWN" for item in report.conrrad_dependencies)
    assert all(item["trust_status"] == "UNKNOWN" for item in report.conrrad_dependencies)
    github.get_authenticated_principal.assert_not_called()
    github.list_organizations.assert_not_called()


def test_unknown_and_noncanonical_preflight_statuses_block_before_github():
    for preflight_status in (
        "UNKNOWN", "UNVERIFIED", "OFFLINE", "BLOCKED", "NOT_CONFIGURED",
        "READY", "AVAILABLE", "ONLINE", "PASS",
    ):
        bootstrap, identity, github = _bootstrap(_ExternalConrradDouble(preflight=preflight_status))
        report = _resolve(bootstrap, identity)

        assert report.get_gate(ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT).passed is False
        assert report.anny_ready is False
        github.get_authenticated_principal.assert_not_called()
        github.list_organizations.assert_not_called()


def test_b9_t05_healthy_github_cannot_mask_unavailable_conrrad():
    github = Mock()
    github.get_authenticated_principal.return_value = {"login": "healthy"}
    github.list_organizations.return_value = [{"login": "org"}]
    bootstrap, identity, _ = _bootstrap(_ExternalConrradDouble(preflight="UNAVAILABLE"), github=github)
    report = _resolve(bootstrap, identity)

    assert report.bootstrap_state == "BLOCKED"
    github.get_authenticated_principal.assert_not_called()
    github.list_organizations.assert_not_called()


class _ResponseWriter:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.body = b""

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass

    def write(self, body):
        self.body += body


class _Handler:
    def __init__(self):
        self.wfile = _ResponseWriter()

    def send_response(self, status, message=None):
        self.wfile.send_response(status)

    def send_header(self, key, value):
        self.wfile.send_header(key, value)

    def end_headers(self):
        self.wfile.end_headers()


def test_b9_t06_status_does_not_manufacture_authority_success():
    report = BootstrapReport(anny_ready=True, runtime_id="runtime-test", fabric_node="UNKNOWN")
    report.bootstrap_state = "BLOCKED"
    engine = SimpleNamespace(
        state=SimpleNamespace(name="READY"),
        config=SimpleNamespace(fabric_org="configured-org", fabric_repo="configured-repo"),
        bootstrap_report=report,
    )
    router = AdminRouter({"runtime_engine": engine})
    handler = _Handler()
    router.dispatch_get("/api/status", handler)
    status = json.loads(handler.wfile.body.decode())

    assert status["admission_status"] == "BLOCKED"
    assert status["reconciliation_status"] == "BLOCKED"
    assert status["github_org"] == "UNKNOWN"
    assert status["tenant"] == "UNKNOWN"
    assert status["capabilities"] == "UNKNOWN"
    assert status["continuity"]["blockers"] == "BLOCKED"
    assert len(status["conrrad_dependencies"]) == len(REQUIRED_CONRRAD_SERVICES)
    assert all(item["online_status"] == "NOT_CONFIGURED" for item in status["conrrad_dependencies"])

    router.context["bootstrap_snapshot"] = {"result": report, "discovered_repos": []}
    assert router._get_continuity_dto().reconciliation_status == "BLOCKED"


def test_empty_bootstrap_dependency_observation_projects_not_configured_entries():
    report = BootstrapReport(anny_ready=False, runtime_id="runtime-test", fabric_node="UNKNOWN")
    engine = SimpleNamespace(
        state=SimpleNamespace(name="ADMIN_MODE"),
        config=SimpleNamespace(fabric_org="configured-org", fabric_repo="configured-repo"),
        bootstrap_report=report,
    )
    router = AdminRouter({"runtime_engine": engine})
    handler = _Handler()
    router.dispatch_get("/api/status", handler)
    status = json.loads(handler.wfile.body.decode())

    assert status["conrrad_dependencies"] != []
    assert len(status["conrrad_dependencies"]) == len(REQUIRED_CONRRAD_SERVICES)
    assert {item["service_name"] for item in status["conrrad_dependencies"]} == set(REQUIRED_CONRRAD_SERVICES)
    assert all(item["online_status"] == "NOT_CONFIGURED" for item in status["conrrad_dependencies"])
    assert all(item["trust_status"] == "UNKNOWN" for item in status["conrrad_dependencies"])


def test_b9_t07_sync_routes_and_fail_closed_activation_are_preserved(tmp_path):
    assert "/api/sync/status" in inspect.getsource(AdminRequestHandler.do_GET)
    assert "/api/sync" in inspect.getsource(AdminRequestHandler.do_POST)
    page = "<html><head></head><body><main>\n</main></body></html>"
    assert "SYNC NOW" in inject_sync_controls(page, "csrf")

    service = SyncService(tmp_path, local_version="v0.4.0", discover=lambda: {"source": "test"})
    service.start()
    service.wait()
    assert service.activate()["error"] != "ACTIVATED"
