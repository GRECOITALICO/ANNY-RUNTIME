"""Governed SYNC transaction service.

The service intentionally fails closed when an authoritative source or verifier is
not available. It never activates a runtime as part of SYNC-only execution.
"""

from __future__ import annotations

import json
import secrets
import threading
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
        self._last_verified: Optional[SyncResult] = (
            self._latest if self._latest and self._latest.sync_state == SyncState.VERIFIED else None
        )
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

    def update_check(self) -> Dict[str, Any]:
        """Run discovery and verification only; never stage, apply, or roll back.

        The admin surface uses this synchronous result so it can report a
        truthful update-check outcome rather than treating handler existence or
        request acceptance as success.
        """
        with self._lock:
            if self._active is not None:
                return {
                    "status": "UPDATE_CHECK_IN_PROGRESS",
                    "sync_state": self._active.sync_state.value,
                    "sync_id": self._active.sync_id,
                    "operation_id": self._active.operation_id,
                }
            result = self._new_result("UPDATE_CHECK")
            self._active = result
            self._persist(result)

        try:
            self._discover_compare_verify(result)
        except Exception as exc:
            result.sync_state = SyncState.FAILED
            result.stage = "REPORT"
            result.error_classification = "UPDATE_CHECK_EXCEPTION"
            result.details = {"message": str(exc)[:500], "activation_performed": False}
        finally:
            with self._lock:
                self._active = None
                self._latest = result
                if result.sync_state == SyncState.VERIFIED and result.candidate_digest:
                    self._last_verified = result
                self._persist(result)
        return self._update_check_response(result)

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._active is not None and self._active.sync_state in (SyncState.SYNCING, SyncState.STAGING, SyncState.ACTIVATING, SyncState.ROLLING_BACK):
                return {
                    "status": "already_running",
                    "sync_state": self._active.sync_state.value,
                    "sync_id": self._active.sync_id,
                    "trace_id": self._active.trace_id,
                }

            result = self._new_result("DISCOVER_VERIFY")
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
                    if result.sync_state == SyncState.VERIFIED and result.candidate_digest:
                        self._last_verified = result
                    self._persist(result)

        self._active_thread = threading.Thread(target=_run_sync, daemon=True)
        self._active_thread.start()

        return {
            "status": "started",
            "sync_state": SyncState.SYNCING.value,
            "sync_id": result.sync_id,
            "trace_id": result.trace_id,
            "operation_id": result.operation_id,
        }

    def stage(self) -> Dict[str, Any]:
        with self._lock:
            if self._active is not None:
                return {"status": "already_running", "sync_state": self._active.sync_state.value}
            prior = self._last_verified
            if prior is None or prior.sync_state != SyncState.VERIFIED or not prior.candidate_digest:
                return {"status": "blocked", "error": "STAGING_REQUIRES_VERIFIED_ARTIFACT"}

            result = self._new_operation_result("STAGE", prior)
            result.sync_state = SyncState.BLOCKED
            result.stage = "REPORT"
            result.error_classification = "STAGING_NOT_IMPLEMENTED"
            result.post_state = SyncState.BLOCKED.value
            result.details = {
                "reason": "No physical staging implementation, stage location, or receipt is configured.",
                "physical_stage_created": False,
            }
            self._latest = result
            self._persist(result)
            return {
                "status": "blocked",
                "error": "STAGING_NOT_IMPLEMENTED",
                "sync_id": result.sync_id,
                "operation_id": result.operation_id,
            }

    def activate(self) -> Dict[str, Any]:
        with self._lock:
            if self._active is not None:
                return {"status": "already_running", "sync_state": self._active.sync_state.value}
            prior = self._latest
            if (
                prior is None
                or prior.sync_state != SyncState.STAGED
                or not prior.details.get("physical_stage_created")
                or not prior.details.get("stage_location")
            ):
                return {"status": "blocked", "error": "APPLY_REQUIRES_PHYSICAL_STAGE"}
            result = self._new_operation_result("APPLY", prior)
            result.sync_state = SyncState.BLOCKED
            result.stage = "REPORT"
            result.error_classification = "APPLY_NOT_IMPLEMENTED"
            result.post_state = SyncState.BLOCKED.value
            result.details = {
                "reason": "No physical apply implementation, target transition, or receipt is configured.",
                "activation_performed": False,
            }
            self._latest = result
            self._persist(result)
            return {
                "status": "blocked",
                "error": "APPLY_NOT_IMPLEMENTED",
                "sync_id": result.sync_id,
                "operation_id": result.operation_id,
            }

    def rollback(self) -> Dict[str, Any]:
        with self._lock:
            if self._active is not None:
                return {"status": "already_running", "sync_state": self._active.sync_state.value}
            prior = self._latest
            if prior is None or not prior.activation_performed:
                return {"status": "blocked", "error": "ROLLBACK_REQUIRES_PHYSICAL_APPLY"}
            result = self._new_operation_result("ROLLBACK", prior)
            result.sync_state = SyncState.BLOCKED
            result.stage = "REPORT"
            result.error_classification = "ROLLBACK_NOT_IMPLEMENTED"
            result.post_state = SyncState.BLOCKED.value
            result.details = {
                "reason": "No physical rollback implementation, prior-state restoration, or receipt is configured.",
                "activation_performed": False,
            }
            self._latest = result
            self._persist(result)
            return {
                "status": "blocked",
                "error": "ROLLBACK_NOT_IMPLEMENTED",
                "sync_id": result.sync_id,
                "operation_id": result.operation_id,
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

        try:
            discovered = self.discover()
            if discovered is None:
                discovered = {}
        except Exception as exc:
            result.sync_state = SyncState.UNKNOWN
            result.error_classification = "UPDATE_SOURCE_UNKNOWN"
            result.stage = "REPORT"
            result.details = {"reason": f"Discovery failed: {type(exc).__name__}", "activation_performed": False}
            return
        if not isinstance(discovered, dict):
            result.sync_state = SyncState.FAILED
            result.error_classification = "UPDATE_METADATA_INVALID"
            result.stage = "REPORT"
            result.details = {"reason": "Discovery provider returned non-mapping metadata.", "activation_performed": False}
            return
        result.source = str(discovered.get("source", "UNKNOWN"))
        result.discovered_revision = discovered.get("revision")
        result.candidate_version = discovered.get("candidate_version")

        if result.source == "UNKNOWN":
            result.sync_state = SyncState.UNKNOWN
            result.error_classification = "UPDATE_SOURCE_UNKNOWN"
            result.stage = "REPORT"
            result.details = {"reason": "Discovery metadata did not identify a source.", "activation_performed": False}
            return

        if not discovered.get("authorized", False):
            result.sync_state = SyncState.BLOCKED
            result.error_classification = "AUTHORITY_UNVERIFIED"
            result.stage = "REPORT"
            result.details = {"reason": "Source was discovered without sufficient authority evidence."}
            return

        result.stage = "COMPARE"
        candidate = result.candidate_version
        if not candidate or not isinstance(candidate, str):
            result.comparison = "UNKNOWN"
            result.verification = "INVALID"
            result.sync_state = SyncState.FAILED
            result.error_classification = "UPDATE_METADATA_INVALID"
            result.stage = "REPORT"
            result.details = {"reason": "Authoritative discovery did not provide a candidate version.", "activation_performed": False}
            return
        if candidate == self.local_version:
            result.comparison = "NO_UPDATE"
            result.verification = "NOT_REQUIRED"
            result.sync_state = SyncState.VERIFIED
            result.stage = "REPORT"
            result.details = {"reason": "Authoritative source reports the current version; no candidate is available.", "activation_performed": False}
            return

        # A different version is merely discovered. No filename ordering is
        # used to infer that it is newer or safe to apply.
        result.comparison = "CANDIDATE_DISCOVERED"

        # The admin update-check is a Runtime release check, not a generic
        # synchronization assertion.  It therefore requires release-shaped
        # metadata before a verifier may report UPDATE_AVAILABLE.
        if (
            result.operation_type == "UPDATE_CHECK"
            and discovered.get("candidate_kind") != "RUNTIME_RELEASE"
        ):
            result.sync_state = SyncState.FAILED
            result.verification = "INVALID"
            result.error_classification = "UPDATE_METADATA_INVALID"
            result.stage = "REPORT"
            result.details = {
                "reason": "Update candidate is not declared as a Runtime release artifact.",
                "activation_performed": False,
            }
            return

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
        result.candidate_id = (
            (result.candidate_identity or {}).get("release_id")
            or result.discovered_revision
        )
        result.candidate_digest = result.digest
        result.target = "RUNTIME_INSTALLATION_UNKNOWN"

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

    def _new_result(self, operation_type: str) -> SyncResult:
        now = datetime.now(timezone.utc).isoformat()
        sync_id = f"sync-{secrets.token_hex(12)}"
        return SyncResult(
            sync_id=sync_id,
            trace_id=f"trace-{secrets.token_hex(12)}",
            requested_at=now,
            sync_state=SyncState.SYNCING,
            local_version=self.local_version,
            operation_id=f"op-{secrets.token_hex(12)}",
            operation_type=operation_type,
            prior_state=SyncState.IDLE.value,
        )

    def _new_operation_result(self, operation_type: str, prior: Optional[SyncResult]) -> SyncResult:
        result = self._new_result(operation_type)
        result.source = prior.source if prior else "UNKNOWN"
        result.candidate_version = prior.candidate_version if prior else None
        result.discovered_revision = prior.discovered_revision if prior else None
        result.candidate_identity = prior.candidate_identity if prior else None
        result.digest_algorithm = prior.digest_algorithm if prior else None
        result.digest = prior.digest if prior else None
        result.candidate_id = prior.candidate_id if prior else None
        result.candidate_digest = prior.candidate_digest if prior else None
        result.target = prior.target if prior else "RUNTIME_INSTALLATION_UNKNOWN"
        result.prior_state = prior.sync_state.value if prior else SyncState.IDLE.value
        return result

    @staticmethod
    def _update_check_response(result: SyncResult) -> Dict[str, Any]:
        if result.comparison == "NO_UPDATE" and result.sync_state == SyncState.VERIFIED:
            status = "UPDATE_NOT_AVAILABLE"
        elif result.comparison == "CANDIDATE_DISCOVERED" and result.sync_state == SyncState.VERIFIED:
            status = "UPDATE_AVAILABLE"
        elif result.error_classification == "UPDATE_METADATA_INVALID":
            status = "UPDATE_METADATA_INVALID"
        elif result.error_classification in {"AUTHORITATIVE_SOURCE_UNAVAILABLE", "UPDATE_SOURCE_UNKNOWN", "AUTHORITY_UNVERIFIED"}:
            status = "UPDATE_SOURCE_UNAVAILABLE"
        else:
            status = "UPDATE_VERIFICATION_UNAVAILABLE"
        return {
            "status": status,
            "sync_state": result.sync_state.value,
            "sync_id": result.sync_id,
            "trace_id": result.trace_id,
            "operation_id": result.operation_id,
            "candidate_version": result.candidate_version,
            "verification": result.verification,
            "error_classification": result.error_classification,
            "activation_performed": False,
        }

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
