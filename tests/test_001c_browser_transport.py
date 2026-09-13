"""
ANNY-REMOTE-COMPUTE-001C-A: Browser-Assisted Colab Transport Tests

Tests:
  BA-01 provision uses SyncMCPBridge
  BA-02 auth success sets READY and REAL_REMOTE
  BA-03 auth failure sets FAILED
  BA-04 execute uses bridge call_tool
  BA-05 health checks bridge list_tools
  BA-06 account separation
  BA-12 credential isolation
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import timedelta

from runtime.compute.colab import (
    ColabComputeProvider,
    BrowserColabTransport,
    BrowserSessionState,
    ColabTransport,
    CliColabTransport
)
from runtime.compute.models import (
    RemoteSessionState,
    ExecutionClassification,
    RemoteComputeJob
)


@pytest.fixture
def mock_bridge():
    with patch('runtime.compute.colab.SyncMCPBridge') as mock_class:
        instance = mock_class.return_value
        
        # Proper mock for open_colab_browser_connection response
        mock_open_res = MagicMock()
        mock_open_res.isError = False
        mock_open_res.content = [MagicMock(text="true")]
        
        # Proper mock for call_tool (default for execute)
        mock_exec_res = MagicMock()
        mock_exec_res.isError = False
        mock_exec_res.content = [MagicMock(text="test output")]
        
        # Make call_tool return open_res for open_colab, else exec_res
        def call_tool_side_effect(name, args):
            if name == "open_colab_browser_connection":
                return mock_open_res
            return mock_exec_res
            
        instance.call_tool.side_effect = call_tool_side_effect
        
        mock_tools = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "python"
        mock_tools.tools = [mock_tool]
        instance.list_tools.return_value = mock_tools
        
        yield instance


# =============================================================================
# BA-01: Provision uses SyncMCPBridge
# =============================================================================

class TestBA01Provision:
    def test_browser_opens_mcp_bridge(self, mock_bridge):
        transport = BrowserColabTransport()
        session = transport.provision({"session_name": "ba01-test"})
        
        mock_bridge.start.assert_called_once()
        mock_bridge.call_tool.assert_called_with("open_colab_browser_connection", {})
        
        assert session.state == RemoteSessionState.READY
        assert session.classification == ExecutionClassification.REAL_REMOTE


# =============================================================================
# BA-03: Auth Failure
# =============================================================================

class TestBA03AuthFailure:
    def test_auth_denied_returns_failed(self, mock_bridge):
        mock_res = MagicMock()
        mock_res.isError = False
        mock_res.content = [MagicMock(text="false")]
        mock_bridge.call_tool.side_effect = lambda n, a: mock_res
        
        transport = BrowserColabTransport()
        session = transport.provision({"session_name": "ba03-test"})
        
        assert session.state == RemoteSessionState.FAILED
        assert "timeout or denied" in session.metadata["error"]

    def test_bridge_start_exception_returns_failed(self, mock_bridge):
        mock_bridge.start.side_effect = Exception("Bridge exploded")
        
        transport = BrowserColabTransport()
        session = transport.provision({"session_name": "ba03-test"})
        
        assert session.state == RemoteSessionState.FAILED
        assert "Bridge exploded" in session.metadata["error"]


# =============================================================================
# BA-04: Execute
# =============================================================================

class TestBA04Execute:
    def test_execute_calls_bridge_tool(self, mock_bridge):
        from datetime import datetime
        transport = BrowserColabTransport()
        session = transport.provision({"session_name": "ba04-test"})
        
        job = RemoteComputeJob(
            job_id="test", 
            session_id="ba04-test", 
            work_package_ref="wp", 
            created_at=datetime.now(), 
            status="PENDING", 
            deadline=datetime.now()
        )
        job.code = "print('hi')"
        
        completed_job = transport.execute(session, job)
        
        mock_bridge.call_tool.assert_any_call("python", {"code": "print('hi')"})
        assert completed_job.status == "COMPLETED"
        assert completed_job.stdout == "test output"

    def test_execute_raises_on_unattached(self, mock_bridge):
        from datetime import datetime
        transport = BrowserColabTransport()
        session = transport.provision({"session_name": "ba04-test2"})
        session.state = RemoteSessionState.TERMINATED
        
        job = RemoteComputeJob(
            job_id="t", 
            session_id="ba04-test2", 
            work_package_ref="wp", 
            created_at=datetime.now(), 
            status="PENDING", 
            deadline=datetime.now()
        )
        job.code = "print('hi')"
        
        with pytest.raises(RuntimeError, match="Cannot execute on browser session"):
            transport.execute(session, job)


# =============================================================================
# BA-05: Health
# =============================================================================

class TestBA05Health:
    def test_health_polls_bridge(self, mock_bridge):
        transport = BrowserColabTransport()
        session = transport.provision({"session_name": "ba05"})
        
        assert transport.health(session) == RemoteSessionState.READY
        mock_bridge.list_tools.assert_called()

    def test_health_terminated_if_bridge_fails(self, mock_bridge):
        transport = BrowserColabTransport()
        session = transport.provision({"session_name": "ba05"})
        
        mock_bridge.list_tools.side_effect = Exception("Disconnected")
        assert transport.health(session) == RemoteSessionState.TERMINATED


# =============================================================================
# BA-06: Account Separation
# =============================================================================

class TestBA06AccountSeparation:
    def test_cli_and_browser_sessions_are_separate(self, mock_bridge):
        provider = ColabComputeProvider()
        browser_session = provider.provision({
            "transport_type": "browser",
            "session_name": "ba06-browser"
        })
        assert browser_session.session_id == "ba06-browser"
        assert browser_session.metadata["transport"] == "browser"


# =============================================================================
# BA-12: Credential Isolation
# =============================================================================

class TestBA12CredentialIsolation:
    def test_rejects_credentials_in_context(self):
        transport = BrowserColabTransport()
        for key in ["token", "credentials", "password", "cookie", "browser_cookie", "session_cookie"]:
            with pytest.raises(ValueError, match="Security violation"):
                transport.provision({"session_name": "ba12", key: "leaked"})


# =============================================================================
# Transport Abstraction Tests
# =============================================================================

class TestTransportAbstraction:
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

