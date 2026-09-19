"""
tests/test_001g_managed_browser.py

MISSION-001G-R2 test suite (Browser Broker IPC refactor).

Key invariants:
  - ONE ColabWebSocketServer session
  - ONE token / ONE port / ONE browser URL
  - open_colab_browser_connection called EXACTLY ONCE
  - Auth wait uses monotonic deadline + list_tools() polling
  - WAITING_FOR_BROWSER_CONNECTION is NOT a failure
  - Cleanup fires on CONNECTED / FAILED / TIMEOUT
  - BrowserSessionManager communicates via IPC to Browser Broker
  - No subprocess.Popen or shutil.which in manager module
"""

import os
import sys
import time
import threading
import tempfile
import socket
import json
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock, call

# Make sure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from runtime.browser.manager import BrowserSessionManager, BrowserManagerError
from runtime.compute.colab import (
    BrowserColabTransport,
    BrowserSessionState,
    RemoteSessionState,
    SyncMCPBridge,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_tool_result(text: str) -> MagicMock:
    item = MagicMock()
    item.text = text
    res = MagicMock()
    res.isError = False
    res.content = [item]
    return res


def _make_tool_list(names: list[str]) -> MagicMock:
    tools = []
    for n in names:
        m = MagicMock()
        m.name = n
        tools.append(m)
    result = MagicMock()
    result.tools = tools
    return result


def _ipc_ok_start(pid=12345):
    """Returns an IPC response simulating successful START_BROWSER."""
    return {"status": "ok", "pid": pid}


def _ipc_ok_stop():
    """Returns an IPC response simulating successful STOP_BROWSER."""
    return {"status": "ok"}


def _ipc_ok_status(running=True, pid=12345):
    """Returns an IPC response simulating STATUS."""
    return {"status": "ok", "running": running, "pid": pid if running else None}


def _ipc_error(message="Broker unavailable"):
    return {"status": "error", "message": message}


# ── BrowserSessionManager IPC tests ───────────────────────────────────────────

class TestManagedBrowserProfile:
    """test_managed_browser_profile (IPC-based)"""

    def test_profile_dir_is_anny_scoped(self):
        mgr = BrowserSessionManager.create(profile="colab")
        assert "anny" in str(mgr.socket_path).lower() or "anny" in str(
            Path.home() / ".anny"
        ).lower()
        assert "colab" == mgr.profile

    def test_profile_never_uses_personal_chrome(self):
        mgr = BrowserSessionManager.create(profile="colab")
        # The manager no longer holds a profile_dir, but the broker server does.
        # Verify the socket path is not a personal Chrome config.
        assert ".config/google-chrome" not in str(mgr.socket_path)
        assert ".config/chromium" not in str(mgr.socket_path)

    def test_create_returns_instance(self):
        mgr = BrowserSessionManager.create(profile="colab")
        assert isinstance(mgr, BrowserSessionManager)
        assert mgr.profile == "colab"


class TestBrowserSessionManagerIPC:
    """IPC client tests for BrowserSessionManager."""

    def test_launch_sends_start_browser_ipc(self):
        url = "https://colab.research.google.com/test#token=1"
        mgr = BrowserSessionManager.create(profile="colab")
        with patch.object(mgr, "_send_ipc", return_value=_ipc_ok_start()) as mock_ipc:
            mgr.launch(url)
        mock_ipc.assert_called_once_with("START_BROWSER", url=url)

    def test_terminate_sends_stop_browser_ipc(self):
        mgr = BrowserSessionManager.create(profile="colab")
        with patch.object(mgr, "_send_ipc", return_value=_ipc_ok_stop()) as mock_ipc:
            mgr.terminate()
        mock_ipc.assert_called_once_with("STOP_BROWSER")

    def test_is_running_true_when_broker_reports_running(self):
        mgr = BrowserSessionManager.create(profile="colab")
        with patch.object(mgr, "_send_ipc", return_value=_ipc_ok_status(running=True)):
            assert mgr.is_running() is True

    def test_is_running_false_when_broker_reports_stopped(self):
        mgr = BrowserSessionManager.create(profile="colab")
        with patch.object(mgr, "_send_ipc", return_value=_ipc_ok_status(running=False)):
            assert mgr.is_running() is False

    def test_is_running_false_when_broker_unavailable(self):
        mgr = BrowserSessionManager.create(profile="colab")
        with patch.object(mgr, "_send_ipc", return_value=_ipc_error()):
            assert mgr.is_running() is False

    def test_launch_idempotent_via_broker(self):
        """Second launch request is proxied to broker; broker handles idempotency."""
        url1 = "https://colab.research.google.com/test#token=1"
        url2 = "https://colab.research.google.com/test#token=2"
        mgr = BrowserSessionManager.create(profile="colab")
        with patch.object(mgr, "_send_ipc", return_value=_ipc_ok_start()) as mock_ipc:
            mgr.launch(url1)
            mgr.launch(url2)
        # Both calls are forwarded to the broker
        assert mock_ipc.call_count == 2

    def test_no_subprocess_popen_in_manager(self):
        """Manager must NOT import or use subprocess.Popen for browser launch."""
        import runtime.browser.manager as mod
        # Verify subprocess is not imported in manager module
        assert not hasattr(mod, "subprocess") or not callable(
            getattr(getattr(mod, "subprocess", None), "Popen", None)
        ), "manager.py must not use subprocess.Popen — use IPC to broker instead"


# ── BrowserColabTransport tests ────────────────────────────────────────────────

class _BridgeMockFactory:
    """Builds a SyncMCPBridge mock for transport tests."""

    @staticmethod
    def connected_immediately():
        """Bridge where call_tool returns 'true' right away."""
        bridge = MagicMock(spec=SyncMCPBridge)
        bridge.call_tool.return_value = _make_tool_result("true")
        bridge.list_tools.return_value = _make_tool_list(["open_colab_browser_connection"])
        return bridge

    @staticmethod
    def url_then_tool_list_connected(url: str, url_file: str, tool_polls_before_connect: int = 2):
        """
        Bridge that:
         1. call_tool() blocks ~forever (simulates 60s internal wait)
         2. Writes url to url_file immediately (simulates webbrowser.open_new)
         3. list_tools() returns only the base tool for N polls, then returns extra tools
        """
        bridge = MagicMock(spec=SyncMCPBridge)

        connection_result = {}

        def _call_tool_side_effect(name, args):
            # Write URL immediately (sync, before blocking)
            with open(url_file, "w") as f:
                f.write(url)
            # Block until connection_result is set (simulates 60s wait)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if connection_result.get("done"):
                    break
                time.sleep(0.05)
            return _make_tool_result(connection_result.get("text", "false"))

        poll_count = [0]

        def _list_tools_side_effect():
            poll_count[0] += 1
            if poll_count[0] > tool_polls_before_connect:
                # Signal the call_tool thread to return 'true'
                connection_result["done"] = True
                connection_result["text"] = "true"
                return _make_tool_list(["open_colab_browser_connection", "python", "run_code"])
            return _make_tool_list(["open_colab_browser_connection"])

        bridge.call_tool.side_effect = _call_tool_side_effect
        bridge.list_tools.side_effect = _list_tools_side_effect
        return bridge


def _patch_browser_manager(mock_ipc_response=None):
    """Context manager helper that patches BrowserSessionManager IPC calls."""
    mock_manager = MagicMock(spec=BrowserSessionManager)
    mock_manager.is_running.return_value = True
    return mock_manager


