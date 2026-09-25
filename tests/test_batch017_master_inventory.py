"""Batch 017: baseline reconciliation and Control Center truth tests."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from runtime.admin.projections import (
    DEFAULT_NAVIGATION_ITEMS,
    DEFAULT_PROJECTION_REGISTRY,
    audit_navigation_contract,
)
from runtime.admin.routes import AdminRouter
from runtime.bootstrap.gates import MANDATORY_GATES


class _Response:
    def __init__(self):
        self.status = None
        self.body = b""

    def send_response(self, code):
        self.status = code

    def send_header(self, _key, _value):
        pass

    def end_headers(self):
        pass

    def write(self, data):
        self.body += data


class _Handler:
    def __init__(self):
        self.wfile = _Response()

    def send_response(self, code, message=None):
        self.wfile.send_response(code)

    def send_header(self, key, value):
        self.wfile.send_header(key, value)

    def end_headers(self):
        self.wfile.end_headers()


def test_batch017_inventory_keeps_reconciled_floors_after_later_expansion():
    summary = DEFAULT_PROJECTION_REGISTRY.summary()
    assert summary["total_definitions"] >= 559
    assert summary["by_priority"]["P0"] >= 268
    assert summary["by_implementation_status"]["BOUND"] == 78


def test_batch017_status_api_fails_closed_for_unserializable_observations():
    engine = MagicMock()
    engine.state.name = "ERROR"
    engine.bootstrap_report.anny_ready = False
    engine.bootstrap_report.fabric_node = "UNKNOWN"
    engine.config = None
    handler = _Handler()

    AdminRouter({"runtime_engine": engine}).dispatch_get("/api/status", handler)

    payload = json.loads(handler.wfile.body.decode("utf-8"))
    assert handler.wfile.status == 200
    assert payload["runtime_health"] == "NOT_HEALTHY"
    assert payload["timestamp"] == "UNKNOWN"


def test_batch017_dependency_inventory_makes_preflight_pass():
    root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/preflight_check.py"],
        cwd=root,
        env={"PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DEPENDENCY_PREFLIGHT_PASS" in result.stdout


def test_batch017_navigation_contract_remains_valid():
    audit = audit_navigation_contract(
        DEFAULT_NAVIGATION_ITEMS,
        AdminRouter({})._get_routes,
    )
    assert audit["status"] == "VALID"
    assert audit["dead_links"] == []
    assert audit["false_online_declarations"] == []


def test_batch017_fail_closed_gate_contract_has_28_mandatory_gates():
    assert len(MANDATORY_GATES) == 28
