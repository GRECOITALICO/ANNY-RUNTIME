import os
import re

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/runtime/sync/service.py", "r") as f:
    code = f.read()

# Add import threading and import time if not present
if "import threading" not in code:
    code = code.replace("import secrets", "import secrets\nimport threading\nimport time")

# Add _active_thread to __init__
init_patch = """        self._active: Optional[SyncResult] = None
        self._active_thread: Optional[threading.Thread] = None
        self._latest: Optional[SyncResult] = self._load_latest()"""
code = code.replace("        self._active: Optional[SyncResult] = None\n        self._latest: Optional[SyncResult] = self._load_latest()", init_patch)

# Add wait method
wait_method = """    def wait(self, timeout: Optional[float] = None) -> None:
        if self._active_thread:
            self._active_thread.join(timeout=timeout)

    @property"""
code = code.replace("    @property", wait_method)

# Replace start method entirely
start_method_old = """    def start(self) -> Dict[str, Any]:
        if self._active is not None and self._active.sync_state == SyncState.SYNCING:
            return {
                "status": "already_running",
                "sync_state": SyncState.SYNCING.value,
                "sync_id": self._active.sync_id,
                "trace_id": self._active.trace_id,
            }

        now = datetime.now(timezone.utc).isoformat()
        result = SyncResult(
            sync_id=f"sync-{secrets.token_hex(12)}",
            trace_id=f"trace-{secrets.token_hex(12)}",
            requested_at=now,
            sync_state=SyncState.SYNCING,
            local_version=self.local_version,
        )
        self._active = result
        self._persist(result)
        try:
            self._discover_compare_verify(result)
        except Exception as exc:  # fail closed and persist the failure
            result.sync_state = SyncState.FAILED
            result.stage = "REPORT"
            result.error_classification = exc.__class__.__name__
            result.details = {"message": str(exc)[:500]}
        finally:
            self._active = None
            self._latest = result
            self._persist(result)

        return {"status": "started", "sync_state": SyncState.SYNCING.value, "sync_id": result.sync_id, "trace_id": result.trace_id}"""

start_method_new = """    def start(self) -> Dict[str, Any]:
        if self._active is not None and self._active.sync_state in (SyncState.SYNCING, SyncState.STAGING, SyncState.ACTIVATING, SyncState.ROLLING_BACK):
            return {
                "status": "already_running",
                "sync_state": self._active.sync_state.value,
                "sync_id": self._active.sync_id,
                "trace_id": self._active.trace_id,
            }

        now = datetime.now(timezone.utc).isoformat()
        result = SyncResult(
            sync_id=f"sync-{secrets.token_hex(12)}",
            trace_id=f"trace-{secrets.token_hex(12)}",
            requested_at=now,
            sync_state=SyncState.SYNCING,
            local_version=self.local_version,
        )
        self._active = result
        self._persist(result)

        def _run_sync():
            try:
                self._discover_compare_verify(result)
            except Exception as exc:
                result.sync_state = SyncState.FAILED
                result.stage = "REPORT"
                result.error_classification = exc.__class__.__name__
                result.details = {"message": str(exc)[:500]}
            finally:
                self._active = None
                self._latest = result
                self._persist(result)

        self._active_thread = threading.Thread(target=_run_sync, daemon=True)
        self._active_thread.start()

        return {"status": "started", "sync_state": SyncState.SYNCING.value, "sync_id": result.sync_id, "trace_id": result.trace_id}

    def stage(self) -> Dict[str, Any]:
        if self._active is not None:
            return {"status": "already_running", "sync_state": self._active.sync_state.value}
        if self._latest is None or self._latest.sync_state != SyncState.VERIFIED:
            return {"status": "blocked", "error": "Cannot stage without a VERIFIED candidate"}

        result = self._latest
        result.sync_state = SyncState.STAGING
        result.stage = "STAGE"
        self._active = result
        self._persist(result)

        def _run_stage():
            try:
                time.sleep(0.1) # Stub implementation
                result.sync_state = SyncState.STAGED
            except Exception as exc:
                result.sync_state = SyncState.FAILED
                result.error_classification = exc.__class__.__name__
                result.details = {"message": str(exc)[:500]}
            finally:
                self._active = None
                self._persist(result)

        self._active_thread = threading.Thread(target=_run_stage, daemon=True)
        self._active_thread.start()

        return {"status": "staging", "sync_state": SyncState.STAGING.value, "sync_id": result.sync_id}

    def activate(self) -> Dict[str, Any]:
        if self._active is not None:
            return {"status": "already_running", "sync_state": self._active.sync_state.value}
        if self._latest is None or self._latest.sync_state != SyncState.STAGED:
            return {"status": "blocked", "error": "Cannot activate without a STAGED candidate"}

        result = self._latest
        result.sync_state = SyncState.ACTIVATING
        result.stage = "ACTIVATE"
        self._active = result
        self._persist(result)

        def _run_activate():
            try:
                time.sleep(0.1) # Stub implementation
                result.sync_state = SyncState.ACTIVATED
                result.activation_performed = True
                self.local_version = result.candidate_version
            except Exception as exc:
                result.sync_state = SyncState.FAILED
                result.error_classification = exc.__class__.__name__
                result.details = {"message": str(exc)[:500]}
            finally:
                self._active = None
                self._persist(result)

        self._active_thread = threading.Thread(target=_run_activate, daemon=True)
        self._active_thread.start()

        return {"status": "activating", "sync_state": SyncState.ACTIVATING.value, "sync_id": result.sync_id}

    def rollback(self) -> Dict[str, Any]:
        if self._active is not None:
            return {"status": "already_running", "sync_state": self._active.sync_state.value}
        if self._latest is None or not self._latest.activation_performed:
            return {"status": "blocked", "error": "Cannot rollback when not activated"}

        result = self._latest
        result.sync_state = SyncState.ROLLING_BACK
        result.stage = "ROLLBACK"
        self._active = result
        self._persist(result)

        def _run_rollback():
            try:
                time.sleep(0.1) # Stub implementation
                result.sync_state = SyncState.ROLLED_BACK
                result.activation_performed = False
                if result.local_version:
                    self.local_version = result.local_version
            except Exception as exc:
                result.sync_state = SyncState.FAILED
                result.error_classification = exc.__class__.__name__
                result.details = {"message": str(exc)[:500]}
            finally:
                self._active = None
                self._persist(result)

        self._active_thread = threading.Thread(target=_run_rollback, daemon=True)
        self._active_thread.start()

        return {"status": "rolling_back", "sync_state": SyncState.ROLLING_BACK.value, "sync_id": result.sync_id}"""

code = code.replace(start_method_old, start_method_new)

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/runtime/sync/service.py", "w") as f:
    f.write(code)

print("Updated runtime/sync/service.py")
