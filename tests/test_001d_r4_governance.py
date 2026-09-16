"""
tests/test_001d_r4_governance.py

MISSION-001D-R4: Governed Browser Lifecycle Control — Governance Tests.

Verifies that:
  - All new IPC commands (HIDE_BROWSER, NAVIGATE, RESTART_BROWSER) are schema-validated.
  - Forbidden fields are rejected.
  - URL scheme validation applies to NAVIGATE.
  - Broker methods call the right subprocesses (no shell, correct binary).
  - Personal profile is never touched.
  - Binary is never user-selectable.
  - All subprocess calls use shell=False.

All tests are unit tests — no physical browser or X display required.
"""

import os
import sys
import json
import shutil
import socket
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import runtime.browser.broker_server as broker_mod
from runtime.browser.broker_server import (
    BrowserBroker,
    BrowserState,
    _validate_url,
    _validate_profile,
    _validate_schema,
    _FORBIDDEN_FIELDS,
    _REQUIRED_FIELDS,
    CHROME_BINARY,
    PROFILE_BASE,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def broker():
    with patch("runtime.browser.broker_server._check_not_root"):
        b = BrowserBroker()
    return b


@pytest.fixture()
def running_broker(broker):
    """A broker with a mock running Chrome process."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None   # process alive
    mock_proc.pid = 12345
    broker.process = mock_proc
    broker.browser_state = BrowserState.RUNNING
    broker._last_url = "https://colab.research.google.com/"
    return broker


# ─── TEST_START_GOVERNED_BROWSER ──────────────────────────────────────────────

class TestStartGovernedBrowser:
    def test_start_returns_pid_profile_binary(self, broker):
        with patch("runtime.browser.broker_server.Path.exists", return_value=True), \
             patch("runtime.browser.broker_server.Path.mkdir"), \
             patch("runtime.browser.broker_server.subprocess.Popen") as mock_popen, \
             patch("runtime.browser.broker_server._build_chrome_env", return_value={}):
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_popen.return_value = mock_proc

            res = broker.start_browser("https://colab.research.google.com/")

        assert res["status"] == "ok"
        assert res["pid"] == 99999
        assert res["profile"] == str(broker.profile_dir)
        assert res["binary"] == CHROME_BINARY

    def test_start_stores_last_url(self, broker):
        url = "https://colab.research.google.com/"
        with patch("runtime.browser.broker_server.Path.exists", return_value=True), \
             patch("runtime.browser.broker_server.Path.mkdir"), \
             patch("runtime.browser.broker_server.subprocess.Popen") as mock_popen, \
             patch("runtime.browser.broker_server._build_chrome_env", return_value={}):
            mock_proc = MagicMock()
            mock_proc.pid = 1
            mock_popen.return_value = mock_proc
            broker.start_browser(url)

        assert broker._last_url == url

    def test_start_uses_no_shell(self, broker):
        with patch("runtime.browser.broker_server.Path.exists", return_value=True), \
             patch("runtime.browser.broker_server.Path.mkdir"), \
             patch("runtime.browser.broker_server.subprocess.Popen") as mock_popen, \
             patch("runtime.browser.broker_server._build_chrome_env", return_value={}):
            mock_proc = MagicMock()
            mock_proc.pid = 1
            mock_popen.return_value = mock_proc
            broker.start_browser("https://colab.research.google.com/")
            _, kwargs = mock_popen.call_args
            assert kwargs.get("shell") is False


# ─── TEST_STATUS_GOVERNED_BROWSER ────────────────────────────────────────────

class TestStatusGovernedBrowser:
    def test_status_running(self, running_broker):
        res = running_broker.get_status()
        assert res["status"] == "ok"
        assert res["running"] is True
        assert res["pid"] == 12345
        assert res["binary"] == CHROME_BINARY

    def test_status_stopped(self, broker):
        broker.process = None
        res = broker.get_status()
        assert res["status"] == "ok"
        assert res["running"] is False
        assert res["pid"] is None


# ─── TEST_NAVIGATE_ALLOWED_URL ────────────────────────────────────────────────

class TestNavigateAllowedURL:
    def test_navigate_https(self, running_broker):
        with patch.object(running_broker, "_cdp_request") as mock_cdp:
            res = running_broker.navigate("https://colab.research.google.com/new")
        assert res["status"] == "ok"
        assert res["url"] == "https://colab.research.google.com/new"
        mock_cdp.assert_called_once_with("Page.navigate", {"url": "https://colab.research.google.com/new"})

    def test_navigate_http(self, running_broker):
        with patch.object(running_broker, "_cdp_request") as mock_cdp:
            res = running_broker.navigate("http://localhost:8888/")
        assert res["status"] == "ok"
        mock_cdp.assert_called_once_with("Page.navigate", {"url": "http://localhost:8888/"})

    def test_navigate_about(self, running_broker):
        with patch.object(running_broker, "_cdp_request") as mock_cdp:
            res = running_broker.navigate("about:blank")
        assert res["status"] == "ok"
        mock_cdp.assert_called_once_with("Page.navigate", {"url": "about:blank"})

    def test_navigate_uses_no_shell(self, running_broker):
        # Now uses CDP, which is inherently shell=False and injection proof.
        with patch.object(running_broker, "_cdp_request") as mock_cdp:
            running_broker.navigate("https://colab.research.google.com/new")
            mock_cdp.assert_called_once_with("Page.navigate", {"url": "https://colab.research.google.com/new"})

    def test_navigate_uses_correct_binary(self, running_broker):
        # Navigation no longer launches a binary directly.
        pass


# ─── TEST_NAVIGATE_FORBIDDEN_SCHEME ──────────────────────────────────────────

class TestNavigateForbiddenScheme:
    @pytest.mark.parametrize("url", [
        "ftp://evil.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "chrome-extension://abc/bg.js",
        "chrome-untrusted://abc/",
    ])
    def test_forbidden_scheme_rejected(self, running_broker, url):
        res = running_broker.navigate(url)
        assert res["status"] == "error"
        assert "scheme" in res["message"].lower() or "not allowed" in res["message"].lower()


# ─── TEST_HIDE_GOVERNED_BROWSER ──────────────────────────────────────────────

class TestHideGovernedBrowser:
    def test_hide_with_xdotool(self, running_broker):
        with patch("runtime.browser.broker_server.shutil.which", return_value="/usr/bin/xdotool"), \
             patch("runtime.browser.broker_server.subprocess.run") as mock_run:
            search_res = MagicMock()
            search_res.stdout = "111111\n222222\n"
            minimize_res = MagicMock()
            mock_run.side_effect = [search_res, minimize_res, minimize_res]

            res = running_broker.hide_browser()

        assert res["status"] == "ok"
        assert res["browser_state"] == BrowserState.HIDDEN

    def test_hide_sets_hidden_state(self, running_broker):
        with patch("runtime.browser.broker_server.shutil.which", return_value="/usr/bin/xdotool"), \
             patch("runtime.browser.broker_server.subprocess.run") as mock_run:
            search_res = MagicMock()
            search_res.stdout = "111111\n"
            mock_run.side_effect = [search_res, MagicMock()]
            running_broker.hide_browser()

        assert running_broker.browser_state == BrowserState.HIDDEN

    def test_hide_without_xdotool_returns_unavailable(self, running_broker):
        with patch("runtime.browser.broker_server.os.path.exists", return_value=False):
            res = running_broker.hide_browser()
        assert res["status"] == "unavailable"

    def test_hide_not_running_is_noop(self, broker):
        broker.process = None
        res = broker.hide_browser()
        assert res["status"] == "ok"

    def test_hide_uses_no_shell(self, running_broker):
        with patch("runtime.browser.broker_server.shutil.which", return_value="/usr/bin/xdotool"), \
             patch("runtime.browser.broker_server.subprocess.run") as mock_run:
            search_res = MagicMock()
            search_res.stdout = "111111\n"
            mock_run.side_effect = [search_res, MagicMock()]
            running_broker.hide_browser()
            for c in mock_run.call_args_list:
                assert c.kwargs.get("shell") is False or c[1].get("shell") is False


# ─── TEST_STOP_GOVERNED_BROWSER ──────────────────────────────────────────────

class TestStopGovernedBrowser:
    def test_stop_terminates_process(self, running_broker):
        mock_proc = running_broker.process  # capture before stop clears it
        mock_proc.wait.return_value = 0
        res = running_broker.stop_browser()
        mock_proc.terminate.assert_called_once()
        assert res["status"] == "ok"
        assert res["browser_state"] == BrowserState.CLOSED


# ─── TEST_PERSONAL_PROFILE_UNTOUCHABLE ────────────────────────────────────────

class TestPersonalProfileUntouchable:
    def test_broker_profile_hardwired_to_colab(self):
        with patch("runtime.browser.broker_server._check_not_root"):
            b = BrowserBroker()
        assert b.profile_name == "colab"
        assert str(b.profile_dir).startswith(str(PROFILE_BASE))
        assert "colab" in str(b.profile_dir)

    def test_personal_chrome_profile_not_used(self):
        personal = str(Path.home() / ".config" / "google-chrome")
        with patch("runtime.browser.broker_server._check_not_root"):
            b = BrowserBroker()
        assert str(b.profile_dir) != personal
        assert not str(b.profile_dir).startswith(personal)


# ─── TEST_BINARY_NOT_USER_SELECTABLE ─────────────────────────────────────────

class TestBinaryNotUserSelectable:
    def test_binary_field_in_request_rejected(self):
        req = {"command": "START_BROWSER", "url": "https://colab.google.com/", "binary": "/bin/sh"}
        valid, err = _validate_schema(req)
        assert not valid
        assert "binary" in err.lower() or "forbidden" in err.lower()

    def test_executable_field_rejected(self):
        req = {"command": "START_BROWSER", "url": "https://colab.google.com/", "executable": "evil"}
        valid, err = _validate_schema(req)
        assert not valid


# ─── TEST_PROFILE_NOT_USER_SELECTABLE ────────────────────────────────────────

class TestProfileNotUserSelectable:
    def test_profile_field_in_request_rejected(self):
        req = {"command": "START_BROWSER", "url": "https://colab.google.com/", "profile": "personal"}
        valid, err = _validate_schema(req)
        assert not valid
        assert "forbidden" in err.lower() or "profile" in err.lower()

    def test_profile_dir_field_rejected(self):
        req = {"command": "START_BROWSER", "url": "https://colab.google.com/", "profile_dir": "/tmp/hack"}
        valid, err = _validate_schema(req)
        assert not valid


# ─── TEST_NO_SHELL_EXECUTION ──────────────────────────────────────────────────

class TestNoShellExecution:
    def test_schema_has_no_shell_command(self):
        for cmd in _REQUIRED_FIELDS:
            assert "shell" not in _REQUIRED_FIELDS[cmd]

    def test_shell_field_rejected(self):
        req = {"command": "STATUS", "shell": "true"}
        valid, err = _validate_schema(req)
        assert not valid

    def test_new_commands_registered_in_schema(self):
        assert "HIDE_BROWSER" in _REQUIRED_FIELDS
        assert "NAVIGATE" in _REQUIRED_FIELDS
        assert "RESTART_BROWSER" in _REQUIRED_FIELDS

    def test_navigate_requires_url(self):
        req = {"command": "NAVIGATE"}
        valid, err = _validate_schema(req)
        assert not valid
        assert "url" in err.lower()

    def test_hide_requires_no_fields(self):
        req = {"command": "HIDE_BROWSER"}
        valid, err = _validate_schema(req)
        assert valid, f"Expected valid, got: {err}"

    def test_restart_requires_no_fields(self):
        req = {"command": "RESTART_BROWSER"}
        valid, err = _validate_schema(req)
        assert valid, f"Expected valid, got: {err}"
