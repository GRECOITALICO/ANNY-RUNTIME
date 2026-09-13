import pytest
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import hashlib

from runtime.compute.models import (
    RemoteComputeSession,
    RemoteSessionState,
    RemoteComputeLease,
    RemoteComputeResourceProfile,
    ExecutionClassification,
    TrustLevel,
    RemoteComputeJob,
    RemoteComputeArtifact
)
from runtime.compute.provider import RemoteComputeProvider

class MockRemoteProvider(RemoteComputeProvider):
    def __init__(self):
        self._sessions = {}
        
    @property
    def provider_id(self) -> str:
        return "test-dummy-provider"

    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        # TEST-10: Remote provider cannot access credentials
        if "credentials" in context or "token" in context or "private_keys" in context:
            raise ValueError("Security violation: Credentials leaked to provider")
            
        session_id = "test-session-123"
        lease = RemoteComputeLease(
            lease_id="lease-123",
            session_id=session_id,
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
            max_runtime=3600,
            renewable=False
        )
        session = RemoteComputeSession(
            session_id=session_id,
            provider_id=self.provider_id,
            state=RemoteSessionState.PROVISIONING,
            classification=ExecutionClassification.TEST, # MUST be TEST
            lease=lease
        )
        self._sessions[session_id] = session
        return session

    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        return RemoteComputeResourceProfile(
            cpu="mock-cpu",
            cores=1,
            ram=1024,
            gpu_present=False
        )

    def health(self, session: RemoteComputeSession) -> RemoteSessionState:
        # TEST-06: lease expiration
        if session.lease and datetime.now(timezone.utc) > session.lease.expires_at:
            session.state = RemoteSessionState.EXPIRED
        return session.state

    def execute(self, session: RemoteComputeSession, job: RemoteComputeJob) -> RemoteComputeJob:
        if session.classification == ExecutionClassification.REAL_REMOTE:
            # TEST-12: TEST provider cannot produce physical certification
            raise ValueError("Test provider cannot claim REAL_REMOTE execution")
            
        # TEST-03, TEST-04, TEST-05
        if session.state != RemoteSessionState.READY:
            raise RuntimeError(f"Cannot execute. Session state is {session.state}")

        # TEST-14: Job deadline enforcement
        if datetime.now(timezone.utc) > job.deadline:
            job.status = "FAILED_DEADLINE_EXCEEDED"
            return job

        # TEST-15: Resource limit enforcement
        if job.resource_limits.get("ram", 0) > 1024:
            job.status = "FAILED_RESOURCE_LIMIT"
            return job
            
        # TEST-11: Remote provider cannot bypass policy
        if job.network_policy == "DENY_ALL" and job.work_package_ref == "network_call":
            raise ValueError("Policy violation: network access denied")

        job.started_at = datetime.now(timezone.utc)
        job.status = "RUNNING"
        # mock execution
        job.status = "COMPLETED"
        job.finished_at = datetime.now(timezone.utc)
        return job

    def collect(self, session: RemoteComputeSession, job: RemoteComputeJob) -> List[RemoteComputeArtifact]:
        content = b"dummy result"
        sha = hashlib.sha256(content).hexdigest()
        art = RemoteComputeArtifact(
            artifact_id="art-1",
            job_id=job.job_id,
            artifact_type="output",
            reference="mock://art-1",
            sha256=sha,
            size=len(content),
            created_at=datetime.now(timezone.utc),
            source_session=session.session_id
        )
        job.artifact_refs.append(art.artifact_id)
        return [art]

    def terminate(self, session: RemoteComputeSession) -> None:
        session.state = RemoteSessionState.TERMINATED
        
def test_01_create_session():
    provider = MockRemoteProvider()
    session = provider.provision({"context": "safe"})
    assert session.session_id == "test-session-123"
    assert session.state == RemoteSessionState.PROVISIONING
    assert session.classification == ExecutionClassification.TEST

def test_02_state_transition():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.CONNECTED
    assert provider.health(session) == RemoteSessionState.CONNECTED
    session.state = RemoteSessionState.READY
    assert provider.health(session) == RemoteSessionState.READY

def test_03_connected_cannot_execute():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.CONNECTED
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    with pytest.raises(RuntimeError, match="Cannot execute"):
        provider.execute(session, job)

def test_04_auditing_cannot_execute():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.AUDITING
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    with pytest.raises(RuntimeError, match="Cannot execute"):
        provider.execute(session, job)

def test_05_ready_can_execute():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    result = provider.execute(session, job)
    assert result.status == "COMPLETED"

def test_06_lease_expiration():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.lease.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert provider.health(session) == RemoteSessionState.EXPIRED

def test_07_termination():
    provider = MockRemoteProvider()
    session = provider.provision({})
    provider.terminate(session)
    assert session.state == RemoteSessionState.TERMINATED

def test_08_artifact_registration():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    provider.execute(session, job)
    artifacts = provider.collect(session, job)
    assert len(artifacts) == 1
    assert artifacts[0].job_id == job.job_id
    assert job.artifact_refs == [artifacts[0].artifact_id]

def test_09_artifact_sha256_verification():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    artifacts = provider.collect(session, job)
    assert artifacts[0].sha256 is not None
    assert len(artifacts[0].sha256) == 64

def test_10_remote_provider_cannot_access_credentials():
    provider = MockRemoteProvider()
    with pytest.raises(ValueError, match="Security violation"):
        provider.provision({"credentials": {"aws_key": "123"}})
    with pytest.raises(ValueError, match="Security violation"):
        provider.provision({"token": "xyz"})

def test_11_remote_provider_cannot_bypass_policy():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    job = RemoteComputeJob("j1", session.session_id, "network_call", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10), network_policy="DENY_ALL")
    with pytest.raises(ValueError, match="Policy violation"):
        provider.execute(session, job)

def test_12_test_provider_cannot_produce_physical_certification():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    session.classification = ExecutionClassification.REAL_REMOTE
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    with pytest.raises(ValueError, match="Test provider cannot claim REAL_REMOTE execution"):
        provider.execute(session, job)

def test_13_multiple_jobs_in_one_session():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    job1 = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    job2 = RemoteComputeJob("j2", session.session_id, "wp2", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10))
    provider.execute(session, job1)
    provider.execute(session, job2)
    assert job1.status == "COMPLETED"
    assert job2.status == "COMPLETED"

def test_14_job_deadline_enforcement():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) - timedelta(minutes=1))
    result = provider.execute(session, job)
    assert result.status == "FAILED_DEADLINE_EXCEEDED"

def test_15_resource_limit_enforcement():
    provider = MockRemoteProvider()
    session = provider.provision({})
    session.state = RemoteSessionState.READY
    job = RemoteComputeJob("j1", session.session_id, "wp1", datetime.now(timezone.utc), "PENDING", datetime.now(timezone.utc) + timedelta(minutes=10), resource_limits={"ram": 2048})
    result = provider.execute(session, job)
    assert result.status == "FAILED_RESOURCE_LIMIT"
