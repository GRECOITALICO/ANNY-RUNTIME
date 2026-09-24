"""Governed SYNC transaction service.

The service intentionally fails closed when an authoritative source or verifier is
not available. It never activates a runtime as part of SYNC-only execution.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .models import SyncResult, SyncState


DiscoverFn = Callable[[], Dict[str, Any]]
VerifyFn = Callable[[Dict[str, Any]], Dict[str, Any]]


class SyncService:
    """Execute and persist one governed SYNC transaction at a time."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        local_version: str = "UNKNOWN",
        discover: Optional[DiscoverFn] = None,
        verify: Optional[VerifyFn] = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.local_version = local_version
        self.discover = discover
        self.verify_candidate = verify
        self._active: Optional[SyncResult] = None
        self._active_thread: Optional[threading.Thread] = None
        self._latest: Optional[SyncResult] = self._load_latest()
        self._lock = threading.Lock()

    def wait(self, timeout: Optional[float] = None) -> None:
        if self._active_thread:
            self._active_thread.join(timeout=timeout)

    @property
    def latest(self) -> Optional[SyncResult]:
        return self._latest

    def status(self) -> Dict[str, Any]:
        if self._active is not None:
            return self._active.to_dict()
        if self._latest is not None:
            return self._latest.to_dict()
        return {
            "sync_id": None,
            "trace_id": None,
            "requested_at": None,
            "sync_state": SyncState.IDLE.value,
            "stage": "NONE",
            "source": "UNKNOWN",
            "local_version": self.local_version,
            "candidate_version": None,
            "discovered_revision": None,
            "comparison": "UNKNOWN",
            "verification": "UNKNOWN",
            "activation_performed": False,
            "error_classification": None,
            "evidence_id": None,
            "details": {},
        }

    def start(self) -> Dict[str, Any]:
        with self._lock:
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
                with self._lock:
                    self._active = None
                    self._latest = result
                    self._persist(result)

        self._active_thread = threading.Thread(target=_run_sync, daemon=True)
        self._active_thread.start()

        return {"status": "started", "sync_state": SyncState.SYNCING.value, "sync_id": result.sync_id, "trace_id": result.trace_id}

    def stage(self) -> Dict[str, Any]:
        """Fail closed until physical staging is implemented."""
        with self._lock:
            trace_id = self._latest.trace_id if self._latest is not None else f"trace-{secrets.token_hex(12)}"
            sync_id = self._latest.sync_id if self._latest is not None else None
            return {
                "status": "blocked",
                "sync_state": SyncState.BLOCKED.value,
                "sync_id": sync_id,
                "trace_id": trace_id,
                "error": "Physical staging is not implemented",
                "error_classification": "STAGE_NOT_IMPLEMENTED",
            }

    def activate(self) -> Dict[str, Any]:
        with self._lock:
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
                # Activation is not physically implemented yet.
                # Must fail-closed and leave explicitly blocked to avoid faking state.
                result.sync_state = SyncState.BLOCKED
                result.error_classification = "ACTIVATION_NOT_IMPLEMENTED"
            except Exception as exc:
                result.sync_state = SyncState.FAILED
                result.error_classification = exc.__class__.__name__
                result.details = {"message": str(exc)[:500]}
            finally:
                with self._lock:
                    self._active = None
                    self._persist(result)

        self._active_thread = threading.Thread(target=_run_activate, daemon=True)
        self._active_thread.start()

        return {"status": "activating", "sync_state": SyncState.ACTIVATING.value, "sync_id": result.sync_id}

    def rollback(self) -> Dict[str, Any]:
        """Fail closed until physical rollback is implemented."""
        with self._lock:
            trace_id = self._latest.trace_id if self._latest is not None else f"trace-{secrets.token_hex(12)}"
            sync_id = self._latest.sync_id if self._latest is not None else None
            return {
                "status": "blocked",
                "sync_state": SyncState.BLOCKED.value,
                "sync_id": sync_id,
                "trace_id": trace_id,
                "error": "Physical rollback is not implemented",
                "error_classification": "ROLLBACK_NOT_IMPLEMENTED",
            }

    def _discover_compare_verify(self, result: SyncResult) -> None:
        result.stage = "DISCOVER"
        if self.discover is None:
            result.sync_state = SyncState.BLOCKED
            result.source = "UNKNOWN"
            result.error_classification = "AUTHORITATIVE_SOURCE_UNAVAILABLE"
            result.stage = "REPORT"
            result.details = {"reason": "No authoritative discovery provider is configured."}
            return

        discovered = self.discover() or {}
        result.source = str(discovered.get("source", "UNKNOWN"))
        result.discovered_revision = discovered.get("revision")
        result.candidate_version = discovered.get("candidate_version")

        if not discovered.get("authorized", False):
            result.sync_state = SyncState.BLOCKED
            result.error_classification = "AUTHORITY_UNVERIFIED"
            result.stage = "REPORT"
            result.details = {"reason": "Source was discovered without sufficient authority evidence."}
            return

        result.stage = "COMPARE"
        candidate = result.candidate_version
        if not candidate or candidate == self.local_version:
            result.comparison = "NO_CHANGE"
            result.verification = "NOT_REQUIRED"
            result.sync_state = SyncState.VERIFIED
            result.stage = "REPORT"
            result.details = {"reason": "No verified candidate requiring change was discovered."}
            return

        result.comparison = "CANDIDATE_AVAILABLE"

        result.stage = "VERIFY"
        if self.verify_candidate is None:
            result.sync_state = SyncState.UNKNOWN
            result.error_classification = "CANDIDATE_VERIFIER_UNAVAILABLE"
            result.stage = "REPORT"
            return

        try:
            # We assume verify_candidate can take (discovered, trace_id)
            verification = self.verify_candidate(discovered, result.trace_id)
            v_dict = verification.to_dict() if hasattr(verification, "to_dict") else (verification or {})
        except Exception as exc:
            result.sync_state = SyncState.FAILED
            result.error_classification = "VERIFIER_EXCEPTION"
            result.verification = "ERROR"
            result.stage = "REPORT"
            result.details = {"message": str(exc)[:500], "activation_performed": False}
            return
            
        result.candidate_identity = v_dict.get("candidate_identity")
        result.digest_algorithm = v_dict.get("digest_algorithm")
        result.digest = v_dict.get("digest")
        result.proof_reference = v_dict.get("proof_reference")
        result.verifier_identity = v_dict.get("verifier_identity")

        if not v_dict.get("verified", False):
            status_val = v_dict.get("status", "FAILED")
            result.sync_state = SyncState.BLOCKED if status_val != "UNKNOWN" else SyncState.UNKNOWN
            result.verification = str(status_val)
            result.error_classification = str(v_dict.get("error", "CANDIDATE_NOT_VERIFIED"))
            result.stage = "REPORT"
            result.details = {"activation_performed": False}
            return

        result.verification = "VERIFIED"
        result.sync_state = SyncState.VERIFIED
        result.stage = "REPORT"
        result.details = {"activation_performed": False}

    def _persist(self, result: SyncResult) -> None:
        path = self.data_dir / "sync"
        path.mkdir(parents=True, exist_ok=True)
        record = path / "sync_records.jsonl"
        with record.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
            handle.flush()

    def _load_latest(self) -> Optional[SyncResult]:
        record = self.data_dir / "sync" / "sync_records.jsonl"
        if not record.exists():
            return None
        try:
            line = next((line for line in reversed(record.read_text(encoding="utf-8").splitlines()) if line.strip()), None)
            if not line:
                return None
            raw = json.loads(line)
            raw["sync_state"] = SyncState(raw["sync_state"])
            return SyncResult(**raw)
        except Exception:
            return None
