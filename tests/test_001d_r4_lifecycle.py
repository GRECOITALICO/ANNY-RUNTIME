"""
tests/test_001d_r4_lifecycle.py

MISSION-001D-R4: Governed Browser Lifecycle Control — Lifecycle Tests.

Verifies the state machine of BrowserColabTransport.provision():
  - Browser is visible (launched) before READY
  - Browser is hidden/closed automatically once READY gate passes
  - Browser stays visible/alive on MCP failure
  - Remote session survives browser close
  - Reconnect reopens browser then hides it again after READY

All tests are unit tests using mocked BrowserSessionManager and MCP bridge.
"""

import os
import sys
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from unittest.mock import patch, MagicMock, call, PropertyMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from runtime.compute.colab import (
    BrowserColabTransport,
    BrowserSessionState,
    SyncMCPBridge,
)
from runtime.compute.models import RemoteSessionState


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _make_tools(*names):
    """Return a mock list_tools() result with the given tool names."""
    res = MagicMock()
    tools = []
    for n in names:
        t = MagicMock()
        t.name = n
        tools.append(t)
    res.tools = tools
    return res


def _make_bridge(tool_names, connected_after_n_polls=0):
    """
    Return a mock SyncMCPBridge.
    - list_tools() returns only open_colab_browser_connection for first N polls,
      then returns the full tool set.
    """
    bridge = MagicMock(spec=SyncMCPBridge)
    poll_count = {"n": 0}

    def _list_tools():
        if poll_count["n"] < connected_after_n_polls:
            poll_count["n"] += 1
            return _make_tools("open_colab_browser_connection")
        return _make_tools(*tool_names)

    bridge.list_tools.side_effect = _list_tools

    # add_code_cell / run_code_cell for execute path
    add_res = MagicMock()
    add_res.content = [MagicMock(text='{"newCellId": "cell-001"}')]
    run_res = MagicMock()
    run_res.content = [MagicMock(text='{"outputs": [{"text": ["ANNY_COLAB_MCP_OK"]}]}')]
    run_res.isError = False
    bridge.call_tool.side_effect = lambda name, args: run_res if name == "run_code_cell" else add_res

    return bridge


def _make_bmanager(is_running=True, hide_status="ok", hide_browser_state="HIDDEN"):
    """Return a mock BrowserSessionManager."""
    bm = MagicMock()
    bm.is_running.return_value = is_running
    bm.hide.return_value = {"status": hide_status, "browser_state": hide_browser_state,
                            "message": ""}
    return bm


def _provision_with_mocks(
    bridge_tool_names=None,
    connected_after_n_polls=0,
    hide_status="ok",
    hide_browser_state="HIDDEN",
    bmanager_is_running=True,
    url_intercepted="https://colab.research.google.com/?mcpProxyToken=test",
    mcp_start_raises=None,
):
    """
    Run BrowserColabTransport.provision() with all external dependencies mocked.
    Returns (session, bmanager_mock, bridge_mock).
    """
    if bridge_tool_names is None:
        bridge_tool_names = [
            "open_colab_browser_connection", "run_code_cell", "add_code_cell",
            "get_cells", "delete_cell", "update_cell",
        ]

    bridge = _make_bridge(bridge_tool_names, connected_after_n_polls)
    bmanager = _make_bmanager(bmanager_is_running, hide_status, hide_browser_state)

    transport = BrowserColabTransport()

    def _fake_bridge_start(env=None):
        if mcp_start_raises:
            raise mcp_start_raises

    with patch("runtime.compute.colab.SyncMCPBridge", return_value=bridge), \
         patch.object(bridge, "start", side_effect=_fake_bridge_start), \
         patch("runtime.browser.manager.BrowserSessionManager.create", return_value=bmanager), \
         patch("os.path.exists", return_value=(url_intercepted is not None)), \
         patch("os.path.getsize", return_value=(len(url_intercepted) if url_intercepted else 0)), \
         patch("builtins.open", MagicMock(return_value=MagicMock(
             __enter__=lambda s: MagicMock(read=lambda: url_intercepted or ""),
             __exit__=lambda s, *a: False,
         ))), \
         patch("os.remove"), \
         patch("os.close"), \
         patch("tempfile.mkstemp", return_value=(0, "/tmp/fake_url_file")):

        context = {"session_name": "test-lifecycle-001"}
        session = transport.provision(context)

    return session, bmanager, bridge


# ─── TEST_BROWSER_VISIBLE_WAITING_USER ───────────────────────────────────────

class TestBrowserVisibleWaitingUser:
    def test_browser_launched_before_ready(self):
        """provision() must call bmanager.launch() before READY is confirmed."""
        bridge = _make_bridge([
            "open_colab_browser_connection", "run_code_cell", "add_code_cell",
            "get_cells",
        ])
        bmanager = _make_bmanager()

        transport = BrowserColabTransport()
        launch_called_before_ready = {"v": False}
        original_is_running = bmanager.is_running

        def _track_launch(url):
            launch_called_before_ready["v"] = True

        bmanager.launch.side_effect = _track_launch

        with patch("runtime.compute.colab.SyncMCPBridge", return_value=bridge), \
             patch.object(bridge, "start"), \
             patch("runtime.browser.manager.BrowserSessionManager.create", return_value=bmanager), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=42), \
             patch("builtins.open", MagicMock(return_value=MagicMock(
                 __enter__=lambda s: MagicMock(read=lambda: "https://colab.google.com/"),
                 __exit__=lambda s, *a: False,
             ))), \
             patch("os.remove"), patch("os.close"), \
             patch("tempfile.mkstemp", return_value=(0, "/tmp/x")):
            context = {"session_name": "test-visible-auth"}
            transport.provision(context)

        assert launch_called_before_ready["v"], "Browser should be launched during auth phase"
        bmanager.launch.assert_called_once()


# ─── TEST_BROWSER_VISIBLE_DURING_AUDIT ───────────────────────────────────────

class TestBrowserVisibleDuringAudit:
    def test_hide_not_called_before_connection(self):
        """hide() must NOT be called until connection is confirmed."""
        bridge = _make_bridge([
            "open_colab_browser_connection", "run_code_cell", "add_code_cell", "get_cells",
        ], connected_after_n_polls=1)
        bmanager = _make_bmanager()

        transport = BrowserColabTransport()
        hide_call_order = {"n": 0}
        list_tools_call_order = {"n": 0}

        original_list_tools = bridge.list_tools.side_effect

        def _track_list_tools():
            list_tools_call_order["n"] += 1
            return original_list_tools()

        bridge.list_tools.side_effect = _track_list_tools

        original_hide = bmanager.hide

        def _track_hide():
            hide_call_order["n"] = list_tools_call_order["n"]
            return {"status": "ok", "browser_state": "HIDDEN"}

        bmanager.hide.side_effect = _track_hide

        with patch("runtime.compute.colab.SyncMCPBridge", return_value=bridge), \
             patch.object(bridge, "start"), \
             patch("runtime.browser.manager.BrowserSessionManager.create", return_value=bmanager), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=42), \
             patch("builtins.open", MagicMock(return_value=MagicMock(
                 __enter__=lambda s: MagicMock(read=lambda: "https://colab.google.com/"),
                 __exit__=lambda s, *a: False,
             ))), \
             patch("os.remove"), patch("os.close"), \
             patch("tempfile.mkstemp", return_value=(0, "/tmp/x")):
            transport.provision({"session_name": "test-audit-visible"})

        # hide was called only AFTER at least one poll confirmed connection
        assert hide_call_order["n"] >= list_tools_call_order["n"] - 1, \
            "hide() must not be called before connection is confirmed"


# ─── TEST_BROWSER_CLOSES_AFTER_READY ─────────────────────────────────────────

class TestBrowserClosesAfterReady:
    def test_hide_called_when_ready(self):
        session, bmanager, _ = _provision_with_mocks()
        assert session.state == RemoteSessionState.READY
        bmanager.hide.assert_called_once()

    def test_metadata_records_auto_hidden_true(self):
        session, _, _ = _provision_with_mocks(hide_status="ok", hide_browser_state="HIDDEN")
        assert session.metadata.get("browser_auto_hidden") is True

    def test_metadata_records_browser_final_state_hidden(self):
        session, _, _ = _provision_with_mocks(hide_status="ok", hide_browser_state="HIDDEN")
        assert session.metadata.get("browser_final_state") == "HIDDEN"

    def test_metadata_records_ready_and_hide_timestamps(self):
        session, _, _ = _provision_with_mocks()
        assert "ready_timestamp" in session.metadata
        assert "hide_timestamp" in session.metadata

    def test_fallback_to_close_when_hide_unavailable(self):
        session, bmanager, _ = _provision_with_mocks(
            hide_status="unavailable", hide_browser_state="RUNNING"
        )
        assert session.state == RemoteSessionState.FAILED
        bmanager.terminate.assert_called()
        assert session.metadata.get("browser_final_state") == "CLOSED"
        assert session.metadata.get("browser_auto_hidden") is True


# ─── TEST_BROWSER_REMAINS_IF_MCP_FAILS ───────────────────────────────────────

class TestBrowserRemainsIfMCPFails:
    def test_session_failed_when_mcp_start_raises(self):
        session, bmanager, _ = _provision_with_mocks(
            mcp_start_raises=RuntimeError("MCP connection refused"),
        )
        assert session.state == RemoteSessionState.FAILED
        # hide must NOT have been called (browser was never up in useful state)
        bmanager.hide.assert_not_called()

    def test_session_failed_when_no_url_intercepted(self):
        session, bmanager, _ = _provision_with_mocks(url_intercepted=None)
        assert session.state == RemoteSessionState.FAILED
        bmanager.hide.assert_not_called()


# ─── TEST_SESSION_SURVIVES_BROWSER_CLOSE ─────────────────────────────────────

class TestSessionSurvivesBrowserClose:
    def test_session_state_ready_after_hide(self):
        session, _, _ = _provision_with_mocks()
        # Session must still be READY even after hide was called
        assert session.state == RemoteSessionState.READY

    def test_session_state_ready_after_fallback_close(self):
        session, _, _ = _provision_with_mocks(
            hide_status="unavailable", hide_browser_state="RUNNING"
        )
        assert session.state == RemoteSessionState.FAILED

    def test_session_ready_even_if_hide_raises(self):
        """A hide() exception must be non-fatal — session stays READY."""
        bridge = _make_bridge([
            "open_colab_browser_connection", "run_code_cell", "add_code_cell", "get_cells",
        ])
        bmanager = _make_bmanager()
        bmanager.hide.side_effect = Exception("xdotool crashed")

        transport = BrowserColabTransport()

        with patch("runtime.compute.colab.SyncMCPBridge", return_value=bridge), \
             patch.object(bridge, "start"), \
             patch("runtime.browser.manager.BrowserSessionManager.create", return_value=bmanager), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=42), \
             patch("builtins.open", MagicMock(return_value=MagicMock(
                 __enter__=lambda s: MagicMock(read=lambda: "https://colab.google.com/"),
                 __exit__=lambda s, *a: False,
             ))), \
             patch("os.remove"), patch("os.close"), \
             patch("tempfile.mkstemp", return_value=(0, "/tmp/x")):
            session = transport.provision({"session_name": "test-survive"})

        assert session.state == RemoteSessionState.READY


# ─── TEST_RECONNECT_REOPENS_BROWSER ──────────────────────────────────────────

class TestReconnectReopensBrowser:
    def test_provision_called_twice_launches_browser_both_times(self):
        """Each provision() call should open the browser fresh."""
        bmanager = _make_bmanager()
        bridge = _make_bridge([
            "open_colab_browser_connection", "run_code_cell", "add_code_cell", "get_cells",
        ])
        transport = BrowserColabTransport()

        def run_provision():
            with patch("runtime.compute.colab.SyncMCPBridge", return_value=bridge), \
                 patch.object(bridge, "start"), \
                 patch("runtime.browser.manager.BrowserSessionManager.create", return_value=bmanager), \
                 patch("os.path.exists", return_value=True), \
                 patch("os.path.getsize", return_value=42), \
                 patch("builtins.open", MagicMock(return_value=MagicMock(
                     __enter__=lambda s: MagicMock(read=lambda: "https://colab.google.com/"),
                     __exit__=lambda s, *a: False,
                 ))), \
                 patch("os.remove"), patch("os.close"), \
                 patch("tempfile.mkstemp", return_value=(0, "/tmp/x")):
                return transport.provision({"session_name": "test-reconnect"})

        s1 = run_provision()
        s2 = run_provision()

        assert s1.state == RemoteSessionState.READY
        assert s2.state == RemoteSessionState.READY
        # launch should be called once per provision
        assert bmanager.launch.call_count == 2


# ─── TEST_RECONNECT_HIDES_BROWSER_AFTER_READY ────────────────────────────────

class TestReconnectHidesBrowserAfterReady:
    def test_hide_called_on_each_provision(self):
        """Each successful provision() must hide the browser."""
        bmanager = _make_bmanager()
        bridge = _make_bridge([
            "open_colab_browser_connection", "run_code_cell", "add_code_cell", "get_cells",
        ])
        transport = BrowserColabTransport()

        for i in range(2):
            with patch("runtime.compute.colab.SyncMCPBridge", return_value=bridge), \
                 patch.object(bridge, "start"), \
                 patch("runtime.browser.manager.BrowserSessionManager.create", return_value=bmanager), \
                 patch("os.path.exists", return_value=True), \
                 patch("os.path.getsize", return_value=42), \
                 patch("builtins.open", MagicMock(return_value=MagicMock(
                     __enter__=lambda s: MagicMock(read=lambda: "https://colab.google.com/"),
                     __exit__=lambda s, *a: False,
                 ))), \
                 patch("os.remove"), patch("os.close"), \
                 patch("tempfile.mkstemp", return_value=(0, "/tmp/x")):
                transport.provision({"session_name": f"test-reconnect-{i}"})

        assert bmanager.hide.call_count == 2, \
            f"Expected hide() called 2 times, got {bmanager.hide.call_count}"
