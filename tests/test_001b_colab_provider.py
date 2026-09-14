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



def test_B_05_provision_cli_error_on_fake_binary():
    # CLI surface is now VERIFIED (001B-S). provision() attempts real CLI call.
    # With a fake binary, _run_cli_raw raises ColabCLINotFoundError (FileNotFoundError caught).
    p = ColabComputeProvider(cli_path="fake-cli")
    p._availability = ProviderAvailability.AVAILABLE
    with pytest.raises(ColabCLINotFoundError, match="Colab CLI not available"):
        p.provision({})

def test_B_06_inspect_raises_on_missing_cli(provider):
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    with pytest.raises(ColabCLINotFoundError):
        provider.inspect(s)

def test_B_07_inspect_cli_error_on_fake_binary():
    # CLI surface is now VERIFIED (001B-S). inspect() attempts real CLI call.
    # With a fake binary, _run_cli_raw raises ColabCLINotFoundError.
    p = ColabComputeProvider(cli_path="fake-cli")
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    p._availability = ProviderAvailability.AVAILABLE
    with pytest.raises(ColabCLINotFoundError, match="Colab CLI not available"):
        p.inspect(s)

def test_B_08_health_raises_on_missing_cli(provider):
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    with pytest.raises(ColabCLINotFoundError):
        provider.health(s)

def test_B_09_health_cli_error_on_fake_binary():
    # CLI surface is now VERIFIED (001B-S). health() attempts real CLI call.
    # With a fake binary, _run_cli_raw raises ColabCLINotFoundError.
    p = ColabComputeProvider(cli_path="fake-cli")
    s = RemoteComputeSession(session_id="s1", provider_id="google-colab", state=RemoteSessionState.CONNECTED, classification=ExecutionClassification.TEST, lease=None)
    p._availability = ProviderAvailability.AVAILABLE
    with pytest.raises(ColabCLINotFoundError, match="Colab CLI not available"):
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
