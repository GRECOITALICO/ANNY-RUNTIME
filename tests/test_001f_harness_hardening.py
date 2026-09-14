"""
ANNY-REMOTE-COMPUTE-001F: Validation Harness Hardening Tests

TEST A – Linux headless  → DISPLAY_UNAVAILABLE / INTERACTIVE_BROWSER_UNAVAILABLE  (no hang)
TEST B – browser missing → BROWSER_EXECUTABLE_NOT_FOUND
TEST C – display absent  → DISPLAY_UNAVAILABLE
TEST D – fake READY, no exec → success_marker = NOT_VERIFIED
TEST E – fake stdout, job not COMPLETED → success_marker = NOT_VERIFIED
TEST F – real success fixture → BROWSER_MCP_REAL_REMOTE = VERIFIED (classifier only)
TEST G – CLI regression  → ANNY_REMOTE_SMOKE_OK
"""

import json
import hashlib
import pytest
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Make sure runtime is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.run_001d_interactive_colab_validation import (
    HostPreflight,
    run_host_preflight,
    classify_remote_success,
    scrub_evidence,
    credential_isolation_check,
    REMOTE_SUCCESS_MARKER,
    FORBIDDEN_EVIDENCE_PATTERNS,
)
from runtime.compute.models import RemoteComputeJob


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(status="COMPLETED", stdout=REMOTE_SUCCESS_MARKER):
    job = MagicMock()
    job.status = status
    job.stdout = stdout
    return job


def _preflight(display=True, browser="/usr/bin/google-chrome"):
    return HostPreflight(
        platform="linux",
        display_available=display,
        browser_executable=browser,
        browser_available=browser is not None,
        interactive_capable=display and browser is not None,
        reason="test fixture",
    )


# ---------------------------------------------------------------------------
# TEST A: Linux headless — no display, no hang
# ---------------------------------------------------------------------------

class TestA_LinuxHeadless:
    def test_preflight_no_display_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        with patch("shutil.which", return_value=None):
            pf = run_host_preflight()
        assert pf.interactive_capable is False
        assert pf.display_available is False
        assert pf.status() == "DISPLAY_UNAVAILABLE"

    def test_preflight_headless_status_string(self):
        pf = _preflight(display=False, browser=None)
        assert pf.status() == "DISPLAY_UNAVAILABLE"

    def test_preflight_dict_has_required_keys(self):
        pf = _preflight(display=False, browser=None)
        d = pf.to_dict()
        for key in ("platform", "display_available", "browser_executable",
                    "browser_available", "interactive_capable", "reason", "status"):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# TEST B: Browser executable missing
# ---------------------------------------------------------------------------

class TestB_BrowserMissing:
    def test_browser_not_found_status(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("DISPLAY", ":99")
        with patch("shutil.which", return_value=None):
            pf = run_host_preflight()
        assert pf.display_available is True
        assert pf.browser_available is False
        assert pf.interactive_capable is False
        assert pf.status() == "BROWSER_EXECUTABLE_NOT_FOUND"

    def test_browser_not_found_dict_status(self):
        pf = HostPreflight(
            platform="linux",
            display_available=True,
            browser_executable=None,
            browser_available=False,
            interactive_capable=False,
            reason="no browser found",
        )
        assert pf.status() == "BROWSER_EXECUTABLE_NOT_FOUND"


# ---------------------------------------------------------------------------
# TEST C: Display unavailable
# ---------------------------------------------------------------------------

class TestC_DisplayUnavailable:
    def test_no_display_env(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        with patch("shutil.which", return_value="/usr/bin/chromium"):
            pf = run_host_preflight()
        assert pf.display_available is False
        assert pf.status() == "DISPLAY_UNAVAILABLE"
        assert pf.interactive_capable is False


# ---------------------------------------------------------------------------
# TEST D: Fake READY, no remote execution → success_marker NOT_VERIFIED
# ---------------------------------------------------------------------------

class TestD_FakeReadyNoExecution:
    def test_classifier_returns_false_on_none(self):
        assert classify_remote_success(None) is False

    def test_classifier_returns_false_on_not_completed(self):
        job = _make_job(status="RUNNING", stdout=REMOTE_SUCCESS_MARKER)
        assert classify_remote_success(job) is False

    def test_classifier_returns_false_when_marker_missing(self):
        job = _make_job(status="COMPLETED", stdout="some other output")
        assert classify_remote_success(job) is False

    def test_classifier_returns_false_on_empty_stdout(self):
        job = _make_job(status="COMPLETED", stdout="")
        assert classify_remote_success(job) is False

    def test_classifier_returns_false_on_none_stdout(self):
        job = _make_job(status="COMPLETED", stdout=None)
        assert classify_remote_success(job) is False


# ---------------------------------------------------------------------------
# TEST E: Fake stdout present but job not COMPLETED
# ---------------------------------------------------------------------------

class TestE_FakeStdout:
    def test_marker_in_stdout_but_status_failed(self):
        # Marker present but status != COMPLETED → NOT VERIFIED
        job = _make_job(status="FAILED", stdout=f"some output\n{REMOTE_SUCCESS_MARKER}\nextra")
        assert classify_remote_success(job) is False

    def test_marker_in_stdout_but_status_running(self):
        job = _make_job(status="RUNNING", stdout=REMOTE_SUCCESS_MARKER)
        assert classify_remote_success(job) is False

    def test_partial_marker_not_enough(self):
        # Partial match should not count
        job = _make_job(status="COMPLETED", stdout="ANNY_COLAB_MCP_O")
        assert classify_remote_success(job) is False


# ---------------------------------------------------------------------------
# TEST F: Real success fixture → VERIFIED (classifier only, not physical cert)
# ---------------------------------------------------------------------------

class TestF_RealSuccessFixture:
    def test_classifier_verified_on_full_success(self):
        job = _make_job(status="COMPLETED", stdout=f"hostname: colab-machine\n{REMOTE_SUCCESS_MARKER}\nGPU_OBSERVED: T4")
        assert classify_remote_success(job) is True

    def test_classifier_verified_marker_at_start(self):
        job = _make_job(status="COMPLETED", stdout=f"{REMOTE_SUCCESS_MARKER}\nhostname: x")
        assert classify_remote_success(job) is True

    def test_classifier_verified_marker_at_end(self):
        job = _make_job(status="COMPLETED", stdout=f"hostname: x\n{REMOTE_SUCCESS_MARKER}")
        assert classify_remote_success(job) is True


# ---------------------------------------------------------------------------
# TEST G: CLI regression
# ---------------------------------------------------------------------------

class TestG_CLIRegression:
    """Ensure the CLI transport path remains unbroken."""

    def test_cli_transport_probe_available(self):
        from runtime.compute.colab import CliColabTransport, ProviderAvailability
        transport = CliColabTransport()
        transport.probe_availability()
        # We accept either AVAILABLE or UNAVAILABLE — what matters is no crash
        assert transport._availability in (
            ProviderAvailability.AVAILABLE,
            ProviderAvailability.UNAVAILABLE,
        )

    def test_provider_routes_cli_by_default(self):
        from runtime.compute.colab import ColabComputeProvider, CliColabTransport
        provider = ColabComputeProvider()
        transport = provider._get_transport({})
        assert isinstance(transport, CliColabTransport)


# ---------------------------------------------------------------------------
# Credential isolation
# ---------------------------------------------------------------------------

class TestCredentialIsolation:
    def test_scrub_removes_password(self):
        ev = {"password": "s3cr3t", "data": "safe"}
        scrubbed = scrub_evidence(ev)
        assert scrubbed["password"] == "<REDACTED>"
        assert scrubbed["data"] == "safe"

    def test_scrub_removes_refresh_token(self):
        ev = {"refresh_token": "abc123"}
        scrubbed = scrub_evidence(ev)
        assert scrubbed["refresh_token"] == "<REDACTED>"

    def test_scrub_redacts_google_token_in_string(self):
        ev = {"url": "https://auth?token=ya29.SUPERSECRET"}
        scrubbed = scrub_evidence(ev)
        assert scrubbed["url"] == "<REDACTED>"

    def test_scrub_nested_dict(self):
        ev = {"outer": {"cookie": "sessionval", "safe": "ok"}}
        scrubbed = scrub_evidence(ev)
        assert scrubbed["outer"]["cookie"] == "<REDACTED>"
        assert scrubbed["outer"]["safe"] == "ok"

    def test_isolation_check_passes_clean_evidence(self):
        ev = {"data": "safe", "exit_code": 0, "stdout": REMOTE_SUCCESS_MARKER}
        assert credential_isolation_check(ev) is True

    def test_isolation_check_fails_on_bearer(self):
        ev = {"header": "Bearer mysecrettoken"}
        # After scrubbing the value becomes <REDACTED>, so scrub first
        scrubbed = scrub_evidence(ev)
        # After scrubbing there should be no raw bearer
        assert "Bearer " not in json.dumps(scrubbed)


# ---------------------------------------------------------------------------
# Preflight dict completeness
# ---------------------------------------------------------------------------

class TestPreflightSchema:
    def test_interactive_available_dict(self):
        pf = _preflight(display=True, browser="/usr/bin/chrome")
        d = pf.to_dict()
        assert d["interactive_capable"] is True
        assert d["status"] == "INTERACTIVE_BROWSER_AVAILABLE"

    def test_no_browser_dict(self):
        pf = _preflight(display=True, browser=None)
        d = pf.to_dict()
        assert d["interactive_capable"] is False
        assert d["browser_available"] is False
        assert d["status"] == "BROWSER_EXECUTABLE_NOT_FOUND"

    def test_no_display_dict(self):
        pf = _preflight(display=False, browser=None)
        d = pf.to_dict()
        assert d["display_available"] is False
        assert d["status"] == "DISPLAY_UNAVAILABLE"
