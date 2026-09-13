import pytest
import datetime
from unittest.mock import patch, MagicMock
from runtime.compute.colab import ColabComputeProvider, ColabCLIError
from runtime.compute.models import (
    RemoteSessionState, ExecutionClassification, RemoteComputeJob, TrustLevel
)

@pytest.fixture
def provider():
    return ColabComputeProvider(cli_path="fake-google-colab-cli")

def test_B_01_authentication(provider):
    with patch.object(provider, '_run_cli', return_value={"status": "success"}) as mock_run:
        assert provider.authenticate("secret-token") is True
        mock_run.assert_called_with(["auth", "login", "--token", "secret-token"])
        
    with patch.object(provider, '_run_cli', side_effect=ColabCLIError("Failed")):
        assert provider.authenticate("bad-token") is False

def test_B_02_provision(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        # Mock classification to REAL_REMOTE
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123", "assigned_accelerator": "T4"} # session create
        ]
        session = provider.provision({"accelerator": "T4"})
        
        assert session.classification == ExecutionClassification.REAL_REMOTE
        assert session.session_id == "colab-123"
        assert session.state == RemoteSessionState.PROVISIONING

def test_B_03_real_remote_requires_actual_backend():
    # B-03: Provider should NOT be REAL_REMOTE if the CLI doesn't exist
    real_provider = ColabComputeProvider(cli_path="this-cli-definitely-does-not-exist")
    session = real_provider.provision({"accelerator": "T4"})
    assert session.classification == ExecutionClassification.TEST
    assert session.state == RemoteSessionState.PROVISIONING

def test_B_04_connected_state(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123", "assigned_accelerator": "T4"} # session create
        ]
        session = provider.provision({"accelerator": "T4"})
        
        # Mock health returning connected
        with patch.object(provider, '_run_cli', return_value={"status": "connected"}):
            state = provider.health(session)
            assert state == RemoteSessionState.CONNECTED
            assert session.state == RemoteSessionState.CONNECTED

def test_B_05_connected_cannot_execute(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123"} # session create
        ]
        session = provider.provision({})
        session.state = RemoteSessionState.CONNECTED
        
        job = RemoteComputeJob(
            job_id="job-1",
            session_id=session.session_id,
            work_package_ref="pkg-1",
            created_at=datetime.datetime.now(datetime.timezone.utc),
            status="PENDING",
            deadline=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        )
        with pytest.raises(RuntimeError, match="CONNECTED != READY|Must be READY"):
            provider.execute(session, job)

def test_B_06_inspection(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123"} # create
        ]
        session = provider.provision({})
        
        with patch.object(provider, '_run_cli', return_value={"hardware": {"accelerator": "T4"}}):
            profile = provider.inspect(session)
            assert profile.gpu_present is True
            assert profile.accelerator_type == "T4"
            assert profile.trust_levels.accelerator_type == TrustLevel.OBSERVED

def test_B_07_health(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123"} # create
        ]
        session = provider.provision({})
        
        with patch.object(provider, '_run_cli', return_value={"status": "ready"}):
            assert provider.health(session) == RemoteSessionState.READY
            
        with patch.object(provider, '_run_cli', return_value={"status": "degraded"}):
            assert provider.health(session) == RemoteSessionState.DEGRADED

def test_B_08_termination(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123"} # create
        ]
        session = provider.provision({})
        
        with patch.object(provider, '_run_cli') as term_mock:
            provider.terminate(session)
            assert session.state == RemoteSessionState.TERMINATED
            term_mock.assert_called_with(["session", "terminate", "colab-123"])

def test_B_09_expired_lease(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123"} # create
        ]
        session = provider.provision({})
        
        # Force expiration
        session.lease.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        
        # Health check should enforce the lease before asking the CLI
        provider.health(session)
        assert session.state == RemoteSessionState.EXPIRED
        
        job = RemoteComputeJob(
            job_id="j1", 
            session_id="s1", 
            work_package_ref="p1",
            created_at=datetime.datetime.now(datetime.timezone.utc),
            status="PENDING",
            deadline=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        )
        with pytest.raises(RuntimeError):
            provider.execute(session, job)

def test_B_10_terminated_session_cannot_execute(provider):
    with patch.object(provider, '_run_cli') as mock_run:
        mock_run.side_effect = [
            {"status": "ready"}, # info
            {"session_id": "colab-123"} # create
        ]
        session = provider.provision({})
        session.state = RemoteSessionState.TERMINATED
        
        job = RemoteComputeJob(
            job_id="j1", 
            session_id="s1", 
            work_package_ref="p1",
            created_at=datetime.datetime.now(datetime.timezone.utc),
            status="PENDING",
            deadline=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        )
        with pytest.raises(RuntimeError, match="TERMINATED"):
            provider.execute(session, job)
