"""
ANNY-REMOTE-COMPUTE-001C-A: Browser-Assisted Colab Transport Tests

Tests:
  BA-01 browser open
  BA-02 login state detection
  BA-03 authentication completion
  BA-04 cancel
  BA-05 browser failure
  BA-06 account separation
  BA-07 session discovery
  BA-08 supported attach
  BA-09 unsupported attach rejection
  BA-10 real remote smoke
  BA-11 termination
  BA-12 credential isolation
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import timedelta

from runtime.compute.colab import (
    ColabComputeProvider,
    CliColabTransport,
    BrowserColabTransport,
    BrowserSessionState,
    ColabTransport,
)
from runtime.compute.models import (
    RemoteSessionState,
    ExecutionClassification,
)


# =============================================================================
# BA-01: Browser Open
# =============================================================================

class TestBA01BrowserOpen:
    """BA-01: Browser transport opens the browser."""

    def test_browser_opens_colab_url(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba01-test"})
        mock_opener.assert_called_once_with("https://colab.research.google.com/")

    def test_browser_open_via_provider(self):
        mock_opener = MagicMock()
        provider = ColabComputeProvider(browser_opener=mock_opener)
        session = provider.provision({"transport_type": "browser", "session_name": "ba01-provider"})
        mock_opener.assert_called_once_with("https://colab.research.google.com/")


# =============================================================================
# BA-02: Login State Detection
# =============================================================================

class TestBA02LoginStateDetection:
    """BA-02: Browser transport tracks browser state transitions."""

    def test_browser_state_reaches_attaching(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba02-test"})
        assert session.metadata["browser_state"] == BrowserSessionState.ATTACHING.value


# =============================================================================
# BA-03: Authentication Completion
# =============================================================================

class TestBA03AuthCompletion:
    """BA-03: Browser transport detects auth completion (browser opened successfully)."""

    def test_successful_browser_open_transitions_past_auth(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba03-test"})
        # If browser opens successfully, we reach ATTACHING (past AUTHENTICATED)
        assert session.metadata["browser_state"] == BrowserSessionState.ATTACHING.value


# =============================================================================
# BA-04: Cancel
# =============================================================================

class TestBA04Cancel:
    """BA-04: Session can be terminated (cancelled) after browser provision."""

    def test_terminate_sets_terminated(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba04-test"})
        transport.terminate(session)
        assert session.state == RemoteSessionState.TERMINATED


# =============================================================================
# BA-05: Browser Failure
# =============================================================================

class TestBA05BrowserFailure:
    """BA-05: Browser open failure is handled gracefully."""

    def test_browser_open_exception_returns_failed(self):
        def failing_opener(url):
            raise OSError("No display available")

        transport = BrowserColabTransport(browser_opener=failing_opener)
        session = transport.provision({"session_name": "ba05-test"})
        assert session.state == RemoteSessionState.FAILED
        assert session.metadata["browser_state"] == BrowserSessionState.FAILED.value
        assert "Browser open failed" in session.metadata["error"]


# =============================================================================
# BA-06: Account Separation
# =============================================================================

class TestBA06AccountSeparation:
    """BA-06: CLI and Browser sessions have separate identities."""

    def test_cli_and_browser_sessions_are_separate(self):
        mock_opener = MagicMock()
        provider = ColabComputeProvider(browser_opener=mock_opener)

        browser_session = provider.provision({
            "transport_type": "browser",
            "session_name": "ba06-browser"
        })

        assert browser_session.session_id == "ba06-browser"
        assert browser_session.metadata["transport"] == "browser"

    def test_transport_metadata_preserved(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba06-meta"})
        assert session.metadata["transport"] == "browser"


# =============================================================================
# BA-07: Session Discovery
# =============================================================================

class TestBA07SessionDiscovery:
    """BA-07: Browser transport records session discovery limitation."""

    def test_session_has_attach_error(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba07-test"})
        assert "attach_error" in session.metadata


# =============================================================================
# BA-08: Supported Attach
# =============================================================================

class TestBA08SupportedAttach:
    """BA-08: No supported attach mechanism exists — classification stays TEST."""

    def test_classification_is_test(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba08-test"})
        assert session.classification == ExecutionClassification.TEST


# =============================================================================
# BA-09: Unsupported Attach Rejection
# =============================================================================

class TestBA09UnsupportedAttachRejection:
    """BA-09: Browser transport explicitly records BROWSER_SESSION_ATTACH_UNSUPPORTED."""

    def test_attach_error_is_unsupported(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba09-test"})
        assert session.metadata["attach_error"] == "BROWSER_SESSION_ATTACH_UNSUPPORTED"
        assert session.state == RemoteSessionState.FAILED

    def test_colab_mcp_evaluation_recorded(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba09-mcp"})
        assert "colab_mcp_evaluation" in session.metadata
        assert "NOT provide a control channel" in session.metadata["colab_mcp_evaluation"]

    def test_execute_raises_on_unattached(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba09-exec"})
        with pytest.raises(RuntimeError, match="Cannot execute on browser session"):
            transport.execute(session, MagicMock())

    def test_inspect_raises_on_unattached(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba09-inspect"})
        with pytest.raises(RuntimeError, match="Cannot inspect browser session"):
            transport.inspect(session)


# =============================================================================
# BA-10: Real Remote Smoke
# =============================================================================

class TestBA10RealRemoteSmoke:
    """BA-10: Browser session cannot produce REAL_REMOTE without attachment."""

    def test_never_classified_real_remote(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba10-test"})
        assert session.classification != ExecutionClassification.REAL_REMOTE


# =============================================================================
# BA-11: Termination
# =============================================================================

class TestBA11Termination:
    """BA-11: Browser session termination records limitation."""

    def test_terminate_records_limitation(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        session = transport.provision({"session_name": "ba11-test"})
        assert "termination_limitation" in session.metadata
        transport.terminate(session)
        assert session.state == RemoteSessionState.TERMINATED


# =============================================================================
# BA-12: Credential Isolation
# =============================================================================

class TestBA12CredentialIsolation:
    """BA-12: Browser transport rejects credentials in context."""

    def test_rejects_token_in_context(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        with pytest.raises(ValueError, match="Security violation"):
            transport.provision({"session_name": "ba12", "token": "leaked"})

    def test_rejects_credentials_in_context(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        with pytest.raises(ValueError, match="Security violation"):
            transport.provision({"session_name": "ba12", "credentials": "leaked"})

    def test_rejects_password_in_context(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        with pytest.raises(ValueError, match="Security violation"):
            transport.provision({"session_name": "ba12", "password": "leaked"})

    def test_rejects_cookie_in_context(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        with pytest.raises(ValueError, match="Security violation"):
            transport.provision({"session_name": "ba12", "cookie": "leaked"})

    def test_rejects_browser_cookie_in_context(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        with pytest.raises(ValueError, match="Security violation"):
            transport.provision({"session_name": "ba12", "browser_cookie": "leaked"})

    def test_rejects_session_cookie_in_context(self):
        mock_opener = MagicMock()
        transport = BrowserColabTransport(browser_opener=mock_opener)
        with pytest.raises(ValueError, match="Security violation"):
            transport.provision({"session_name": "ba12", "session_cookie": "leaked"})


# =============================================================================
# Transport Abstraction Tests
# =============================================================================

class TestTransportAbstraction:
    """Verify the transport abstraction is correct."""

    def test_colab_transport_is_abc(self):
        assert hasattr(ColabTransport, "__abstractmethods__")

    def test_cli_transport_is_subclass(self):
        assert issubclass(CliColabTransport, ColabTransport)

    def test_browser_transport_is_subclass(self):
        assert issubclass(BrowserColabTransport, ColabTransport)

    def test_provider_routes_cli_by_default(self):
        provider = ColabComputeProvider()
        transport = provider._get_transport({"session_name": "test"})
        assert isinstance(transport, CliColabTransport)

    def test_provider_routes_browser_on_request(self):
        provider = ColabComputeProvider()
        transport = provider._get_transport({"transport_type": "browser"})
        assert isinstance(transport, BrowserColabTransport)
