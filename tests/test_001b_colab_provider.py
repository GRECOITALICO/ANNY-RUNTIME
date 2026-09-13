import pytest
import datetime
from unittest.mock import patch
from runtime.compute.colab import ColabComputeProvider, ColabCLINotFoundError, ProviderAvailability
from runtime.compute.models import (
    RemoteSessionState, ExecutionClassification, RemoteComputeJob, TrustLevel, RemoteComputeSession
)

@pytest.fixture
def provider():
    # Use a binary name that is guaranteed not to exist
    return ColabComputeProvider(cli_path="this-cli-definitely-does-not-exist")

def test_B_01_availability_probe(provider):
    # Missing CLI means UNAVAILABLE
    assert provider.probe_availability() == ProviderAvailability.UNAVAILABLE
    
def test_B_02_provision_raises_on_missing_cli(provider):
    with pytest.raises(ColabCLINotFoundError):
        provider.provision({})

def test_B_03_provision_blocks_credentials(provider):
    with pytest.raises(ValueError, match="Security violation: forbidden keys"):
        provider.provision({"credentials": "xyz"})

def test_B_04_classification_test_when_missing(provider):
    assert provider._determine_classification() == ExecutionClassification.TEST

def test_B_05_provision_unverified_surface():
    p = ColabComputeProvider(cli_path="fake-cli")
    # Mock probe to return AVAILABLE
    with patch.object(p, 'probe_availability', return_value=ProviderAvailability.AVAILABLE):
        p._availability = ProviderAvailability.AVAILABLE
        with pytest.raises(NotImplementedError, match="Session creation requires a verified CLI command surface"):
            p.provision({})

def test_B_06_inspect_raises_on_missing_cli(provider):
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    with pytest.raises(ColabCLINotFoundError):
        provider.inspect(s)

def test_B_07_inspect_unverified_surface():
    p = ColabComputeProvider(cli_path="fake-cli")
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    p._availability = ProviderAvailability.AVAILABLE
    
    profile = p.inspect(s)
    # Should return all UNKNOWN since command is unverified
    assert profile.cpu is None
    assert profile.gpu_present is None
    assert profile.trust_levels.accelerator_type == TrustLevel.UNKNOWN

def test_B_08_health_raises_on_missing_cli(provider):
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    with pytest.raises(ColabCLINotFoundError):
        provider.health(s)

def test_B_09_health_unverified_surface():
    p = ColabComputeProvider(cli_path="fake-cli")
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    p._availability = ProviderAvailability.AVAILABLE
    with pytest.raises(NotImplementedError, match="health.. requires a verified CLI status command"):
        p.health(s)

def test_B_10_terminate_forces_state(provider):
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    # terminate catches the missing CLI error and forces state locally
    provider.terminate(s)
    assert s.state == RemoteSessionState.TERMINATED

def test_B_11_terminated_session_cannot_execute(provider):
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.TERMINATED, classification=ExecutionClassification.TEST, lease=None)
    job = RemoteComputeJob(
        job_id="j1", session_id="s1", work_package_ref="p1",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        status="PENDING",
        deadline=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    )
    with pytest.raises(RuntimeError, match="Cannot execute on TERMINATED session"):
        provider.execute(s, job)

def test_B_12_connected_cannot_execute(provider):
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    job = RemoteComputeJob(
        job_id="j1", session_id="s1", work_package_ref="p1",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        status="PENDING",
        deadline=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    )
    with pytest.raises(RuntimeError, match="Must be READY"):
        provider.execute(s, job)
