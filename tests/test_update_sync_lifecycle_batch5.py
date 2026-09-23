"""Batch 5 truthfulness tests for update discovery and Sync lifecycle limits."""
from __future__ import annotations

import hashlib
import io
import tarfile
import threading
import time
from pathlib import Path

import pytest

from runtime.admin.routes import AdminRouter
from runtime.sync.models import SyncState
from runtime.sync.service import SyncService
from runtime.sync.verifier import CandidateVerifier
from runtime.updater.manager import (
    UpdateChannel,
    UpdateInfo,
    UpdateManager,
    UpdateNotImplementedError,
    UpdateState,
)


SOURCE_COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40
ARTIFACT_NAME = "ANNY-RUNTIME-v0.5.0-aaaaaaa.tar.gz"


def _runtime_archive(commit: str = SOURCE_COMMIT, version: str = "0.5.0") -> bytes:
    version_source = (
        f'__version__ = "{version}"\n'
        f'__commit__ = "{commit}"\n'
        '__build_time__ = "2026-09-23T12:00:00Z"\n'
    ).encode("utf-8")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        info = tarfile.TarInfo("ANNY-RUNTIME-v0.5.0-aaaaaaa_build/runtime/core/version.py")
        info.size = len(version_source)
        archive.addfile(info, io.BytesIO(version_source))
    return output.getvalue()


def _release_discovery(payload: bytes, **overrides):
    discovered = {
        "source": "test-authority",
        "revision": "release-001",
        "candidate_version": "v0.5.0",
        "authorized": True,
        "candidate_kind": "RUNTIME_RELEASE",
        "artifact_name": ARTIFACT_NAME,
        "source_commit": SOURCE_COMMIT,
    }
    discovered.update(overrides)
    verifier = CandidateVerifier(
        expected_digest=hashlib.sha256(payload).hexdigest(),
        source_commit_resolver=lambda commit: commit if commit == SOURCE_COMMIT else None,
    )
    return discovered, lambda candidate, trace_id: verifier.verify(candidate, trace_id, payload)


def test_update_manager_operations_are_not_implemented_not_failed():
    manager = UpdateManager({}, "v0.4.0")
    candidate = UpdateInfo("v0.5.0", UpdateChannel.STABLE, "https://invalid.example", "a" * 64, "", "")
    for operation in (
        manager.check,
        lambda: manager.download(candidate),
        lambda: manager.verify(Path("/candidate"), "a" * 64),
        lambda: manager.stage(Path("/candidate")),
        manager.activate,
        manager.rollback,
        manager.health_check,
    ):
        with pytest.raises(UpdateNotImplementedError, match="NOT_IMPLEMENTED"):
            operation()
        assert manager.state is UpdateState.NOT_IMPLEMENTED


def test_update_check_distinguishes_unavailable_source_and_never_mutates(tmp_path: Path):
    service = SyncService(tmp_path, local_version="v0.4.0")
    response = service.update_check()
    assert response["status"] == "UPDATE_SOURCE_UNAVAILABLE"
    assert response["activation_performed"] is False
    assert service.status()["operation_type"] == "UPDATE_CHECK"
    assert service.status()["sync_state"] == SyncState.BLOCKED.value


def test_update_check_distinguishes_malformed_metadata(tmp_path: Path):
    service = SyncService(tmp_path, local_version="v0.4.0", discover=lambda: [])
    response = service.update_check()
    assert response["status"] == "UPDATE_METADATA_INVALID"
    assert response["error_classification"] == "UPDATE_METADATA_INVALID"


def test_update_check_reports_no_update_only_after_authoritative_discovery(tmp_path: Path):
    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "release-000",
            "candidate_version": "v0.4.0",
            "authorized": True,
        },
    )
    response = service.update_check()
    assert response["status"] == "UPDATE_NOT_AVAILABLE"
    assert response["verification"] == "NOT_REQUIRED"
    assert response["activation_performed"] is False


def test_update_check_reports_available_only_after_strict_release_verification(tmp_path: Path):
    payload = _runtime_archive()
    discovered, verify = _release_discovery(payload)
    service = SyncService(tmp_path, local_version="v0.4.0", discover=lambda: discovered, verify=verify)
    response = service.update_check()
    assert response["status"] == "UPDATE_AVAILABLE"
    assert response["verification"] == "VERIFIED"
    assert response["activation_performed"] is False
    assert service.status()["candidate_digest"] == hashlib.sha256(payload).hexdigest()


def test_update_check_rejects_a_generic_candidate_even_when_its_bytes_verify(tmp_path: Path):
    payload = b"candidate"
    verifier = CandidateVerifier(expected_digest=hashlib.sha256(payload).hexdigest())
    service = SyncService(
        tmp_path,
        local_version="v0.4.0",
        discover=lambda: {
            "source": "test-authority",
            "revision": "generic-001",
            "candidate_version": "v0.5.0",
            "authorized": True,
        },
        verify=lambda candidate, trace_id: verifier.verify(candidate, trace_id, payload),
    )
    response = service.update_check()
    assert response["status"] == "UPDATE_METADATA_INVALID"
    assert response["activation_performed"] is False


@pytest.mark.parametrize(
    ("payload", "overrides", "expected_error"),
    [
        (_runtime_archive(), {"source_commit": OTHER_COMMIT}, "FILENAME_SOURCE_COMMIT_MISMATCH"),
        (_runtime_archive(OTHER_COMMIT), {}, "EMBEDDED_SOURCE_COMMIT_MISMATCH"),
    ],
)
def test_runtime_release_verification_rejects_source_or_embedded_mismatch(payload, overrides, expected_error):
    discovered, verify = _release_discovery(payload, **overrides)
    result = verify(discovered, "trace-test")
    assert result.status.value == "INVALID"
    assert result.error == expected_error


def test_runtime_release_verification_rejects_invalid_digest():
    payload = _runtime_archive()
    discovered, _ = _release_discovery(payload)
    verifier = CandidateVerifier(
        expected_digest="0" * 64,
        source_commit_resolver=lambda commit: commit if commit == SOURCE_COMMIT else None,
    )
    result = verifier.verify(discovered, "trace-test", payload)
    assert result.status.value == "INVALID"
    assert result.error == "CHECKSUM_MISMATCH"


def test_stage_apply_and_rollback_are_blocked_with_transaction_metadata(tmp_path: Path):
    payload = _runtime_archive()
    discovered, verify = _release_discovery(payload)
    service = SyncService(tmp_path, local_version="v0.4.0", discover=lambda: discovered, verify=verify)
    service.start()
    service.wait()
    verified = service.status()
    assert verified["sync_state"] == SyncState.VERIFIED.value

    stage = service.stage()
    duplicate_stage = service.stage()
    apply = service.activate()
    rollback = service.rollback()
    assert stage["error"] == duplicate_stage["error"] == "STAGING_NOT_IMPLEMENTED"
    assert stage["operation_id"] != duplicate_stage["operation_id"]
    assert apply["error"] == "APPLY_REQUIRES_PHYSICAL_STAGE"
    assert rollback["error"] == "ROLLBACK_REQUIRES_PHYSICAL_APPLY"
    assert service.status()["activation_performed"] is False
    assert service.status()["target"] == "RUNTIME_INSTALLATION_UNKNOWN"
    assert service.status()["sync_state"] == SyncState.BLOCKED.value
    assert service.status()["post_state"] == SyncState.BLOCKED.value
    assert service.status()["sync_state"] != SyncState.ROLLED_BACK.value


def test_concurrent_update_check_is_visible_not_a_second_operation(tmp_path: Path):
    entered = threading.Event()

    def slow_discover():
        entered.set()
        time.sleep(0.2)
        return {"source": "test-authority", "candidate_version": "v0.4.0", "authorized": True}

    service = SyncService(tmp_path, local_version="v0.4.0", discover=slow_discover)
    holder = []
    thread = threading.Thread(target=lambda: holder.append(service.update_check()))
    thread.start()
    assert entered.wait(timeout=1)
    concurrent = service.update_check()
    thread.join(timeout=1)
    assert concurrent["status"] == "UPDATE_CHECK_IN_PROGRESS"
    assert holder[0]["status"] == "UPDATE_NOT_AVAILABLE"


def test_admin_update_check_uses_sync_service_result_without_stage_or_apply(tmp_path: Path):
    service = SyncService(tmp_path, local_version="v0.4.0")
    router = AdminRouter({"sync_service": service})
    assert router.handle_admin_update_check({}) == "/"
    response = router.context["direct_json_response"]
    assert response["status"] == "UPDATE_SOURCE_UNAVAILABLE"
    assert response["activation_performed"] is False
