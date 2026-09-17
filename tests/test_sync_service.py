from pathlib import Path
import json

from runtime.sync.models import SyncState
from runtime.sync.service import SyncService
from runtime.sync.verifier import CandidateVerifier, VerificationResult


def test_sync_without_authority_fails_closed(tmp_path: Path):
    service = SyncService(tmp_path, local_version="v0.4.0")

    response = service.start()
    status = service.status()

    assert response["status"] == "started"
    assert status["sync_state"] == SyncState.BLOCKED.value
    assert status["error_classification"] == "AUTHORITATIVE_SOURCE_UNAVAILABLE"
    assert status["activation_performed"] is False
    assert (tmp_path / "sync" / "sync_records.jsonl").exists()


def test_sync_no_change_is_verified_without_activation(tmp_path: Path):
    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "abc123",
            "candidate_version": "v0.4.0",
            "authorized": True,
        },
    )

    service.start()
    service.wait()
    status = service.status()

    assert status["sync_state"] == SyncState.VERIFIED.value
    assert status["comparison"] == "NO_CHANGE"
    assert status["verification"] == "NOT_REQUIRED"
    assert status["activation_performed"] is False


def test_sync_candidate_requires_verifier(tmp_path: Path):
    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "def456",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
    )

    service.start()
    service.wait()
    status = service.status()

    assert status["sync_state"] == SyncState.UNKNOWN.value
    assert status["comparison"] == "CANDIDATE_AVAILABLE"
    assert status["error_classification"] == "CANDIDATE_VERIFIER_UNAVAILABLE"
    assert status["activation_performed"] is False


def test_valid_candidate_with_valid_checksum_is_verified(tmp_path: Path):
    expected_hash = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae" # hash of "foo"
    verifier = CandidateVerifier(expected_digest=expected_hash)
    
    # We monkeypatch _fetch_bytes instead of mocking the whole verifier
    # to test the real contract boundary
    def _mock_verify(discovered, trace_id):
        return verifier.verify(discovered, trace_id, b"foo")

    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "ghi789",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=_mock_verify,
    )

    service.start()
    service.wait()
    status = service.status()

    assert status["sync_state"] == SyncState.VERIFIED.value
    assert status["verification"] == "VERIFIED"
    assert status["activation_performed"] is False
    assert status["digest"] == expected_hash
    
    # Verify evidence has no secrets and matches expectations
    record_line = list((tmp_path / "sync" / "sync_records.jsonl").open())[-1]
    record = json.loads(record_line)
    assert record["sync_state"] == "VERIFIED"
    assert record["digest"] == expected_hash
    assert "token" not in json.dumps(record).lower()


def test_valid_candidate_with_invalid_checksum_is_blocked(tmp_path: Path):
    expected_hash = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae" # hash of "foo"
    verifier = CandidateVerifier(expected_digest=expected_hash)
    
    def _mock_verify(discovered, trace_id):
        return verifier.verify(discovered, trace_id, b"bar") # different bytes

    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "ghi789",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=_mock_verify,
    )

    service.start()
    service.wait()
    status = service.status()

    assert status["sync_state"] == SyncState.BLOCKED.value
    assert status["verification"] == "INVALID"
    assert status["error_classification"] == "CHECKSUM_MISMATCH"
    assert status["activation_performed"] is False


def test_candidate_with_missing_proof_is_blocked(tmp_path: Path):
    # No expected digest passed
    verifier = CandidateVerifier(expected_digest=None)
    
    def _mock_verify(discovered, trace_id):
        return verifier.verify(discovered, trace_id, b"foo")

    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "ghi789",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=_mock_verify,
    )

    service.start()
    service.wait()
    status = service.status()

    assert status["sync_state"] == SyncState.BLOCKED.value
    assert status["verification"] == "MISSING_PROOF"
    assert status["error_classification"] == "NO_PROVENANCE_AVAILABLE"
    assert status["activation_performed"] is False


def test_verifier_exception_fails_closed(tmp_path: Path):
    def _mock_verify(discovered, trace_id):
        raise ValueError("Something unexpected broke")

    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "ghi789",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=_mock_verify,
    )

    service.start()
    service.wait()
    status = service.status()

    assert status["sync_state"] == SyncState.FAILED.value
    assert status["verification"] == "ERROR"
    assert status["error_classification"] == "VERIFIER_EXCEPTION"
    assert status["activation_performed"] is False


def test_corrupted_artifact_missing_bytes(tmp_path: Path):
    expected_hash = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
    verifier = CandidateVerifier(expected_digest=expected_hash)
    
    # None bytes instead of bytes
    def _mock_verify(discovered, trace_id):
        return verifier.verify(discovered, trace_id, None)

    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "ghi789",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=_mock_verify,
    )

    service.start()
    service.wait()
    status = service.status()

    assert status["sync_state"] == SyncState.BLOCKED.value
    assert status["verification"] == "ERROR"
    assert status["error_classification"] == "NO_CANDIDATE_BYTES_AVAILABLE"


def test_different_bytes_same_version_does_not_collapse(tmp_path: Path):
    expected_hash_foo = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
    expected_hash_bar = "fcde2b2edba56bf408601fb721fe9b5c338d10ee429ea04fae5511b68fbf8fb9"
    
    # First sync: foo
    verifier1 = CandidateVerifier(expected_digest=expected_hash_foo)
    service1 = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {"source": "test-authority", "candidate_version": "v0.5.0", "authorized": True},
        verify=lambda discovered, trace_id: verifier1.verify(discovered, trace_id, b"foo"),
    )
    service1.start()
    status1 = service1.status()
    
    # Second sync: same version, but artifact is bar
    verifier2 = CandidateVerifier(expected_digest=expected_hash_bar)
    service2 = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {"source": "test-authority", "candidate_version": "v0.5.0", "authorized": True},
        verify=lambda discovered, trace_id: verifier2.verify(discovered, trace_id, b"bar"),
    )
    service2.start()
    status2 = service2.status()

    assert status1["sync_state"] == SyncState.VERIFIED.value
    assert status1["digest"] == expected_hash_foo
    
    assert status2["sync_state"] == SyncState.VERIFIED.value
    assert status2["digest"] == expected_hash_bar
    
    assert status1["digest"] != status2["digest"]
    assert status1["candidate_identity"]["content_digest"] != status2["candidate_identity"]["content_digest"]


def test_repeated_identical_verification(tmp_path: Path):
    expected_hash = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
    verifier = CandidateVerifier(expected_digest=expected_hash)
    
    def _mock_verify(discovered, trace_id):
        return verifier.verify(discovered, trace_id, b"foo")
        
    discover_fn = lambda: {"source": "test", "candidate_version": "v0.5.0", "authorized": True}

    service = SyncService(tmp_path, local_version="v0.4.0", discover=discover_fn, verify=_mock_verify)
    service.start()
    service.wait()
    status1 = service.status()
    
    service.start()
    service.wait()
    status2 = service.status()
    
    assert status1["sync_state"] == SyncState.VERIFIED.value
    assert status2["sync_state"] == SyncState.VERIFIED.value
    assert status1["candidate_identity"]["content_digest"] == status2["candidate_identity"]["content_digest"]
    assert status1["digest"] == status2["digest"]
    assert status1["trace_id"] != status2["trace_id"] # different runs but same deterministic identity logic


def test_sync_stage_activate_rollback(tmp_path: Path):
    expected_hash = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
    verifier = CandidateVerifier(expected_digest=expected_hash)
    
    def _mock_verify(discovered, trace_id):
        return verifier.verify(discovered, trace_id, b"foo")

    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "ghi789",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=_mock_verify,
    )

    # 1. Sync
    service.start()
    service.wait()
    status = service.status()
    assert status["sync_state"] == SyncState.VERIFIED.value

    # 2. Stage
    res = service.stage()
    assert res["status"] == "staging"
    service.wait()
    status = service.status()
    assert status["sync_state"] == SyncState.STAGED.value
    assert status["stage"] == "STAGE"

    # 3. Activate
    res = service.activate()
    assert res["status"] == "activating"
    service.wait()
    status = service.status()
    assert status["sync_state"] == SyncState.ACTIVATED.value
    assert status["activation_performed"] is True
    assert service.local_version == "v0.5.0"

    # 4. Rollback
    res = service.rollback()
    assert res["status"] == "rolling_back"
    service.wait()
    status = service.status()
    assert status["sync_state"] == SyncState.ROLLED_BACK.value
    assert status["activation_performed"] is False
    assert service.local_version == "v0.4.0"

def test_stage_blocked_if_not_verified(tmp_path: Path):
    service = SyncService(tmp_path)
    res = service.stage()
    assert res["status"] == "blocked"

def test_activate_blocked_if_not_staged(tmp_path: Path):
    service = SyncService(tmp_path)
    res = service.activate()
    assert res["status"] == "blocked"

def test_rollback_blocked_if_not_activated(tmp_path: Path):
    service = SyncService(tmp_path)
    res = service.rollback()
    assert res["status"] == "blocked"
