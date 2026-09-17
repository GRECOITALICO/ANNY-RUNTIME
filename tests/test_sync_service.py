from pathlib import Path

from runtime.sync.models import SyncState
from runtime.sync.service import SyncService


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
    status = service.status()

    assert status["sync_state"] == SyncState.UNKNOWN.value
    assert status["comparison"] == "CANDIDATE_AVAILABLE"
    assert status["error_classification"] == "CANDIDATE_VERIFIER_UNAVAILABLE"
    assert status["activation_performed"] is False


def test_verified_candidate_still_does_not_activate(tmp_path: Path):
    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "ghi789",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=lambda candidate: {"verified": True, "status": "VERIFIED"},
    )

    service.start()
    status = service.status()

    assert status["sync_state"] == SyncState.VERIFIED.value
    assert status["verification"] == "VERIFIED"
    assert status["activation_performed"] is False
