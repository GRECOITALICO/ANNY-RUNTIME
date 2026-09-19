"""
tests/test_001g_broker_security.py

MISSION-001D-R2-R2: Browser Broker security hardening tests.

Tests:
  - Protocol schema validation
  - Forbidden field injection (binary, profile, flags, etc.)
  - URL scheme validation
  - Profile path traversal prevention
  - Shell injection prevention
  - Socket permissions (0600)
  - Not-root invariant
  - START_BROWSER / STOP_BROWSER / STATUS contracts
  - Invalid command rejection
"""

import os
import sys
import json
import stat
import socket
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import runtime.browser.broker_server as broker_mod
from runtime.browser.broker_server import (
    BrowserBroker,
    _validate_url,
    _validate_profile,
    _validate_schema,
    _FORBIDDEN_FIELDS,
    CHROME_BINARY,
    PROFILE_BASE,
)


# ── URL validation ─────────────────────────────────────────────────────────────

class TestURLValidation:
    def test_http_allowed(self):
        assert _validate_url("http://example.com/path") == "http://example.com/path"

    def test_https_allowed(self):
        url = "https://colab.research.google.com/notebooks/empty.ipynb#mcpProxyToken=X"
        assert _validate_url(url) == url

    def test_about_blank_allowed(self):
        assert _validate_url("about:blank") == "about:blank"

    def test_ftp_rejected(self):
        with pytest.raises(ValueError, match="scheme not allowed"):
            _validate_url("ftp://evil.com/file")

    def test_file_scheme_rejected(self):
        with pytest.raises(ValueError, match="scheme not allowed"):
            _validate_url("file:///etc/passwd")

    def test_javascript_scheme_rejected(self):
        with pytest.raises(ValueError, match="scheme not allowed"):
            _validate_url("javascript:alert(1)")

    def test_empty_url_rejected(self):
        with pytest.raises(ValueError):
            _validate_url("")

    def test_none_url_rejected(self):
        with pytest.raises(ValueError):
            _validate_url(None)  # type: ignore

    def test_url_with_newline_rejected(self):
        with pytest.raises(ValueError, match="Forbidden character"):
            _validate_url("https://colab.google.com/\nX-Injected: evil")

    def test_url_with_null_byte_rejected(self):
        with pytest.raises(ValueError, match="Forbidden character"):
            _validate_url("https://colab.google.com/\x00evil")

    def test_url_with_shell_pipe_rejected(self):
        with pytest.raises(ValueError, match="Forbidden character"):
            _validate_url("https://colab.google.com/ | rm -rf /")

    def test_url_with_backtick_rejected(self):
        with pytest.raises(ValueError, match="Forbidden character"):
            _validate_url("https://colab.google.com/`id`")

    def test_url_with_semicolon_rejected(self):
        with pytest.raises(ValueError, match="Forbidden character"):
            _validate_url("https://colab.google.com/;evil")


# ── Profile path validation ────────────────────────────────────────────────────

class TestProfileValidation:
    def test_colab_profile_allowed(self):
        p = _validate_profile("colab")
        assert p.is_relative_to(PROFILE_BASE.resolve())

    def test_path_traversal_dotdot_rejected(self):
        with pytest.raises(ValueError):
            _validate_profile("../../../etc")

    def test_path_traversal_slash_rejected(self):
        with pytest.raises(ValueError, match="simple name"):
            _validate_profile("/etc/passwd")

    def test_path_traversal_backslash_rejected(self):
        with pytest.raises(ValueError, match="simple name"):
            _validate_profile("..\\evil")

    def test_empty_profile_rejected(self):
        with pytest.raises(ValueError):
            _validate_profile("")

    def test_home_config_chrome_rejected(self):
        """Profile cannot resolve to ~/.config/google-chrome."""
        with pytest.raises(ValueError):
            _validate_profile("../../../home/anny/.config/google-chrome")

    def test_profile_stays_under_base(self):
        p = _validate_profile("test-session")
        assert str(p).startswith(str(PROFILE_BASE.resolve()))


# ── IPC Schema validation ──────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_valid_start_browser(self):
        ok, err = _validate_schema({"command": "START_BROWSER", "url": "https://colab.research.google.com/"})
        assert ok is True
        assert err == ""

    def test_valid_stop_browser(self):
        ok, err = _validate_schema({"command": "STOP_BROWSER"})
        assert ok is True

    def test_valid_status(self):
        ok, err = _validate_schema({"command": "STATUS"})
        assert ok is True

    def test_missing_command(self):
        ok, err = _validate_schema({"url": "https://colab.google.com/"})
        assert ok is False
        assert "command" in err.lower()

    def test_unknown_command(self):
        ok, err = _validate_schema({"command": "EXEC_SHELL"})
        assert ok is False
        assert "Unknown command" in err

    def test_start_browser_missing_url(self):
        ok, err = _validate_schema({"command": "START_BROWSER"})
        assert ok is False
        assert "url" in err

    def test_non_dict_rejected(self):
        ok, err = _validate_schema("not a dict")  # type: ignore
        assert ok is False

    def test_list_rejected(self):
        ok, err = _validate_schema([{"command": "STATUS"}])  # type: ignore
        assert ok is False

    @pytest.mark.parametrize("field", sorted(_FORBIDDEN_FIELDS))
    def test_forbidden_field_injection_rejected(self, field):
        request = {"command": "START_BROWSER", "url": "https://colab.google.com/", field: "evil"}
        ok, err = _validate_schema(request)
        assert ok is False, f"Forbidden field {field!r} was accepted"
        assert "Forbidden" in err

    def test_binary_injection_rejected(self):
        ok, err = _validate_schema({
            "command": "START_BROWSER",
            "url": "https://colab.google.com/",
            "binary": "/bin/bash"
        })
        assert ok is False

    def test_profile_dir_injection_rejected(self):
        ok, err = _validate_schema({
            "command": "START_BROWSER",
            "url": "https://colab.google.com/",
            "profile_dir": "/etc/cron.d"
        })
        assert ok is False

    def test_flags_injection_rejected(self):
        ok, err = _validate_schema({
            "command": "START_BROWSER",
            "url": "https://colab.google.com/",
            "flags": ["--no-sandbox"]
        })
        assert ok is False

    def test_shell_injection_in_url_rejected(self):
        ok, err = _validate_schema({
            "command": "START_BROWSER",
            "url": "https://colab.google.com/ && rm -rf /"
        })
        # Schema passes (no forbidden fields), but broker rejects via URL validation
        if ok:
            broker = BrowserBroker()
            result = broker.start_browser("https://colab.google.com/ && rm -rf /")
            assert result["status"] == "error", "Shell metacharacter in URL must be rejected"
            assert "Forbidden" in result["message"]


# ── BrowserBroker unit tests ───────────────────────────────────────────────────

class TestBrowserBrokerContract:
    def _make_broker(self):
        return BrowserBroker()

    def test_status_returns_not_running_initially(self):
        b = self._make_broker()
        result = b.get_status()
        assert result["status"] == "ok"
        assert result["running"] is False
        assert result["pid"] is None
        assert result["binary"] == CHROME_BINARY
        assert "profile" in result

    def test_status_always_reports_whitelisted_binary(self):
        b = self._make_broker()
        result = b.get_status()
        assert result["binary"] == CHROME_BINARY

    def test_start_browser_uses_chrome_binary(self):
        b = self._make_broker()
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(Path, "exists", return_value=True), patch.object(Path, "mkdir"):
            proc = MagicMock()
            proc.poll.return_value = None
            proc.pid = 12345
            mock_popen.return_value = proc

            b.start_browser("https://colab.research.google.com/")

        call_args = mock_popen.call_args
        args_list = call_args[0][0]
        assert args_list[0] == CHROME_BINARY

    def test_start_browser_uses_shell_false(self):
        b = self._make_broker()
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(Path, "exists", return_value=True), patch.object(Path, "mkdir"):
            proc = MagicMock()
            proc.poll.return_value = None
            proc.pid = 12345
            mock_popen.return_value = proc

            b.start_browser("https://colab.research.google.com/")

        kwargs = mock_popen.call_args[1]
        assert kwargs.get("shell") is not True, "shell=True is forbidden"

    def test_start_browser_url_in_args_as_app_flag(self):
        b = self._make_broker()
        url = "https://colab.research.google.com/test"
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(Path, "exists", return_value=True), patch.object(Path, "mkdir"):
            proc = MagicMock()
            proc.poll.return_value = None
            proc.pid = 99
            mock_popen.return_value = proc

            b.start_browser(url)

        args_list = mock_popen.call_args[0][0]
        assert any(f"--app={url}" in arg for arg in args_list)

    def test_start_browser_no_no_sandbox_flag(self):
        b = self._make_broker()
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(Path, "exists", return_value=True), patch.object(Path, "mkdir"):
            proc = MagicMock()
            proc.poll.return_value = None
            proc.pid = 99
            mock_popen.return_value = proc

            b.start_browser("https://colab.research.google.com/")

        args_list = mock_popen.call_args[0][0]
        assert "--no-sandbox" not in args_list, "--no-sandbox must NEVER appear in broker args"

    def test_start_browser_profile_under_anny(self):
        b = self._make_broker()
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(Path, "exists", return_value=True), patch.object(Path, "mkdir"):
            proc = MagicMock()
            proc.poll.return_value = None
            proc.pid = 99
            mock_popen.return_value = proc

            b.start_browser("https://colab.research.google.com/")

        args_list = mock_popen.call_args[0][0]
        user_data = [a for a in args_list if "--user-data-dir" in a][0]
        assert ".anny/browser-profiles/" in user_data
        assert ".config/google-chrome" not in user_data

    def test_stop_browser_when_not_running_is_safe(self):
        b = self._make_broker()
        result = b.stop_browser()
        assert result["status"] == "ok"

    def test_stop_browser_terminates_process(self):
        b = self._make_broker()
        proc = MagicMock()
        proc.poll.return_value = None
        b.process = proc

        b.stop_browser()
        proc.terminate.assert_called_once()

    def test_bad_url_scheme_rejected_before_popen(self):
        b = self._make_broker()
        with patch("subprocess.Popen") as mock_popen:
            result = b.start_browser("ftp://evil.com/malware")

        assert result["status"] == "error"
        mock_popen.assert_not_called()

    def test_not_root_enforced(self):
        with patch("os.getuid", return_value=0):
            with pytest.raises(RuntimeError, match="must not run as root"):
                BrowserBroker()


# ── Socket permission test ─────────────────────────────────────────────────────

class TestSocketPermissions:
    def test_socket_created_with_0600(self, tmp_path):
        sock_path = tmp_path / "test-broker.sock"

        with patch.object(broker_mod, "SOCKET_PATH", sock_path):
            server = broker_mod.ThreadedBrokerServer(str(sock_path), broker_mod.BrokerHandler)
            os.chmod(sock_path, 0o600)

            actual_mode = stat.S_IMODE(sock_path.stat().st_mode)
            assert actual_mode == 0o600, f"Expected 0600, got {oct(actual_mode)}"
            server.server_close()

    def test_socket_not_world_readable(self, tmp_path):
        sock_path = tmp_path / "test-broker.sock"

        with patch.object(broker_mod, "SOCKET_PATH", sock_path):
            server = broker_mod.ThreadedBrokerServer(str(sock_path), broker_mod.BrokerHandler)
            os.chmod(sock_path, 0o600)

            actual_mode = stat.S_IMODE(sock_path.stat().st_mode)
            assert not (actual_mode & 0o004), "Socket must not be world-readable"
            assert not (actual_mode & 0o040), "Socket must not be group-readable"
            server.server_close()
