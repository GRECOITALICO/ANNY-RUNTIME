import os

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/tests/test_sync_service.py", "r") as f:
    code = f.read()

# Replace service.start() \n    status = service.status() with service.wait()
code = code.replace("    service.start()\n    status = service.status()", "    service.start()\n    service.wait()\n    status = service.status()")

# In test_repeated_identical_verification
old_repeated = """    service.start()
    status1 = service.status()
    
    service.start()
    status2 = service.status()"""

new_repeated = """    service.start()
    service.wait()
    status1 = service.status()
    
    service.start()
    service.wait()
    status2 = service.status()"""

code = code.replace(old_repeated, new_repeated)

# Add tests for stage, activate, rollback
new_tests = """

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
"""

if "test_sync_stage_activate_rollback" not in code:
    code += new_tests

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/tests/test_sync_service.py", "w") as f:
    f.write(code)

print("Updated tests successfully.")
