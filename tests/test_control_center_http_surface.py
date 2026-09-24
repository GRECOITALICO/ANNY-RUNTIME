"""HTTP integration contracts for the local ANNY Control Center surface.

These tests exercise the actual AdminServer + AdminMiddleware + AdminRouter path.
They do not assert live CONRRAD availability; they only verify the HTTP boundary
does not silently disconnect the GUI from its governed SYNC/status surface.
"""

from __future__ import annotations

import http.client
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

from runtime.admin.server import AdminServer
from runtime.sync.service import SyncService


class _Session:
    admin_session_id = "admin-session-test"
    csrf_token = "csrf-test-token"
    scope = "FULL"
    principal = "local-admin"
    issued_at = "2026-09-24T00:00:00+00:00"
    expires_at = "2026-09-25T00:00:00+00:00"


class _AuthManager:
    ttl_seconds = 3600

    def __init__(self) -> None:
        self.session = _Session()

    def validate(self, session_id):
        return self.session if session_id == self.session.admin_session_id else None

    def create_session(self, principal):
        return self.session

    def create_first_run_session(self):
        return self.session


class _GitHubManager:
    def has_token(self):
        return True


def _start_server(tmp_path: Path):
    sync = SyncService(tmp_path, local_version="0.2.0")
    server = AdminServer(
        "127.0.0.1",
        0,
        auth_manager=_AuthManager(),
        audit_manager=SimpleNamespace(),
        github_manager=_GitHubManager(),
        runtime_engine=SimpleNamespace(),
        sync_service=sync,
    )
    assert server.start() is True
    port = server.server4.server_address[1]
    return server, sync, port


def _request(port: int, method: str, path: str, *, cookie: str | None = None, body: str | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    payload = response.read().decode("utf-8")
    set_cookie = response.getheader("Set-Cookie")
    status = response.status
    conn.close()
    return status, payload, set_cookie


def test_control_center_http_exposes_sync_and_truth_surfaces():
    with tempfile.TemporaryDirectory() as raw:
        server, sync, port = _start_server(Path(raw))
        try:
            status, html, set_cookie = _request(port, "GET", "/")
            assert status == 200
            assert 'data-projection-id="distribution.sync"' in html
            assert 'data-projection-id="control.truth_freshness"' in html
            assert 'data-truth-source="truth_sources.conrrad"' in html
            assert set_cookie and "admin_session_id=" in set_cookie

            cookie = set_cookie.split(";", 1)[0]
            status, payload, _ = _request(port, "GET", "/api/sync/status", cookie=cookie)
            assert status == 200
            assert '"sync_state": "IDLE"' in payload
            assert '"local_version": "0.2.0"' in payload

            body = urlencode({"csrf_token": "csrf-test-token"})
            status, payload, _ = _request(
                port,
                "POST",
                "/api/sync/stage",
                cookie=cookie,
                body=body,
            )
            assert status == 200
            assert '"sync_state": "BLOCKED"' in payload
            assert '"error_classification": "STAGE_NOT_IMPLEMENTED"' in payload
        finally:
            sync.wait(timeout=1)
            server.stop()


def test_control_center_http_request_context_is_isolated_under_concurrency():
    with tempfile.TemporaryDirectory() as raw:
        server, sync, port = _start_server(Path(raw))
        try:
            status, _, set_cookie = _request(port, "GET", "/")
            assert status == 200
            cookie = set_cookie.split(";", 1)[0]

            paths = [
                "/api/status",
                "/api/processing/matrix",
                "/api/control-center/projections?limit=100",
            ] * 4

            def call(path):
                return path, _request(port, "GET", path, cookie=cookie)

            with ThreadPoolExecutor(max_workers=6) as executor:
                results = list(executor.map(call, paths))

            for path, (http_status, payload, _) in results:
                assert http_status == 200
                assert payload.startswith("{")
                if path == "/api/status":
                    assert '"runtime_state"' in payload
                elif path.startswith("/api/processing/matrix"):
                    assert '"error": "Aggregator unavailable"' in payload
                else:
                    assert '"projections"' in payload
        finally:
            sync.wait(timeout=1)
            server.stop()


def test_control_center_http_rejects_sync_mutation_without_csrf():
    with tempfile.TemporaryDirectory() as raw:
        server, sync, port = _start_server(Path(raw))
        try:
            status, _, set_cookie = _request(port, "GET", "/")
            assert status == 200
            cookie = set_cookie.split(";", 1)[0]

            status, _, _ = _request(
                port,
                "POST",
                "/api/sync",
                cookie=cookie,
                body=urlencode({"csrf_token": "wrong-token"}),
            )
            assert status == 303
        finally:
            sync.wait(timeout=1)
            server.stop()
