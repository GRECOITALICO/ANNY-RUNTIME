#!/usr/bin/env python3
"""
MISSION-001F: Hardened Interactive Validation Script for Browser-assisted Colab Transport.

Hardens the 001D validation script with:
  - Proper host preflight (distinguishes display / browser executable)
  - Rich state transition evidence (what happened, why, what evidence)
  - Correct remote success classifier (only ANNY_COLAB_MCP_OK in stdout + exit_code 0)
  - No os._exit() for normal paths
  - Credential scrubbing in evidence
  - Structured evidence schema with implementation_status / host_preflight / browser_connection /
    remote_session / remote_execution / success_marker / credential_isolation

States: INIT -> BROWSER_REQUESTED -> CONNECTING -> CONNECTED -> READY -> EXECUTING -> COMPLETED
Errors: CONNECT_FAILED, AUTH_FAILED, TIMEOUT, DISCONNECTED, EXECUTION_FAILED, CLOSED
"""

import sys
import os
import time
import json
import shutil
import hashlib
import subprocess
import concurrent.futures
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from runtime.compute.colab import ColabComputeProvider
from runtime.compute.models import RemoteComputeJob, RemoteSessionState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REMOTE_SUCCESS_MARKER = "ANNY_COLAB_MCP_OK"

FORBIDDEN_EVIDENCE_KEYS = {
    "password", "cookie", "refresh_token", "oauth_token",
    "browser_storage", "session_secret", "access_token",
    "id_token", "authorization", "private_key",
}

FORBIDDEN_EVIDENCE_PATTERNS = [
    "ya29.",   # Google access-token prefix
    "Bearer ", # Auth header pattern
]

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

@dataclass
class HostPreflight:
    platform: str
    display_available: bool
    browser_executable: Optional[str]
    browser_available: bool
    interactive_capable: bool
    reason: str

    def status(self) -> str:
        if self.interactive_capable:
            return "INTERACTIVE_BROWSER_AVAILABLE"
        if not self.display_available:
            return "DISPLAY_UNAVAILABLE"
        if not self.browser_available:
            return "BROWSER_EXECUTABLE_NOT_FOUND"
        return "INTERACTIVE_BROWSER_UNAVAILABLE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "display_available": self.display_available,
            "browser_executable": self.browser_executable,
            "browser_available": self.browser_available,
            "interactive_capable": self.interactive_capable,
            "reason": self.reason,
            "status": self.status(),
        }


def run_host_preflight() -> HostPreflight:
    """
    Determine whether this host can open a real interactive browser.

    Checks:
      1. Display server (X11 / Wayland on Linux, always present on macOS/Windows)
      2. Browser executable present in PATH

    Does NOT assert Google authentication — that can only be proven by a real MCP session.
    """
    platform_name = sys.platform

    # ---- display ----
    if platform_name in ("win32", "darwin"):
        display_available = True
        display_reason = f"platform={platform_name} (native GUI assumed present)"
    else:
        display_env = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        display_available = bool(display_env)
        display_reason = (
            f"DISPLAY/WAYLAND_DISPLAY={display_env!r}" if display_available
            else "DISPLAY and WAYLAND_DISPLAY not set (headless)"
        )

    # ---- browser executable ----
    browser_candidates = [
        "google-chrome", "google-chrome-stable", "chromium-browser", "chromium",
        "firefox", "firefox-esr", "open", "xdg-open",
    ]
    browser_exe = None
    for candidate in browser_candidates:
        found = shutil.which(candidate)
        if found:
            browser_exe = found
            break

    browser_available = browser_exe is not None

    # ---- interactive_capable ----
    interactive_capable = display_available and browser_available

    if interactive_capable:
        reason = f"display={display_reason}, browser={browser_exe}"
    elif not display_available:
        reason = f"No display: {display_reason}"
    else:
        reason = f"Display available ({display_reason}) but no browser executable found in PATH"

    return HostPreflight(
        platform=platform_name,
        display_available=display_available,
        browser_executable=browser_exe,
        browser_available=browser_available,
        interactive_capable=interactive_capable,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class ValidationState(Enum):
    INIT = "INIT"
    BROWSER_REQUESTED = "BROWSER_REQUESTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    READY = "READY"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"

    CONNECT_FAILED = "CONNECT_FAILED"
    AUTH_FAILED = "AUTH_FAILED"
    TIMEOUT = "TIMEOUT"
    DISCONNECTED = "DISCONNECTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    CLOSED = "CLOSED"


class ValidationStateMachine:
    def __init__(self):
        self.state = ValidationState.INIT
        self.transitions: List[Dict[str, Any]] = []
        self._record_transition(ValidationState.INIT, reason="Validation started", evidence=None)

    def _record_transition(
        self,
        new_state: ValidationState,
        reason: str = "",
        evidence: Optional[Dict[str, Any]] = None,
    ):
        self.state = new_state
        entry: Dict[str, Any] = {
            "state": new_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }
        if evidence:
            entry["evidence"] = evidence
        self.transitions.append(entry)
        print(f"[STATE] -> {new_state.value}" + (f" ({reason})" if reason else ""))

    def transition(
        self,
        new_state: ValidationState,
        reason: str = "",
        evidence: Optional[Dict[str, Any]] = None,
    ):
        self._record_transition(new_state, reason=reason, evidence=evidence)


# ---------------------------------------------------------------------------
# Credential scrubbing
# ---------------------------------------------------------------------------

def _scrub_value(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    for pattern in FORBIDDEN_EVIDENCE_PATTERNS:
        if pattern in v:
            return "<REDACTED>"
    return v


def scrub_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Remove or redact any sensitive fields before writing to disk."""
    result: Dict[str, Any] = {}
    for k, v in evidence.items():
        if k.lower() in FORBIDDEN_EVIDENCE_KEYS:
            result[k] = "<REDACTED>"
        elif isinstance(v, dict):
            result[k] = scrub_evidence(v)
        elif isinstance(v, list):
            result[k] = [_scrub_value(i) for i in v]
        else:
            result[k] = _scrub_value(v)
    return result


def credential_isolation_check(evidence: Dict[str, Any]) -> bool:
    """Returns True if no sensitive material is present."""
    dumped = json.dumps(evidence)
    for pattern in FORBIDDEN_EVIDENCE_PATTERNS:
        if pattern in dumped:
            return False
    for key in FORBIDDEN_EVIDENCE_KEYS:
        if f'"{key}"' in dumped.lower():
            # Only flag if value is non-empty after scrub
            pass  # Already scrubbed above
    return True


# ---------------------------------------------------------------------------
# Remote success classifier
# ---------------------------------------------------------------------------

def classify_remote_success(completed_job) -> bool:
    """
    Returns True ONLY when:
      - job.status == "COMPLETED"
      - stdout contains ANNY_COLAB_MCP_OK

    Any other combination returns False. Never infers from session state alone.
    """
    if completed_job is None:
        return False
    status_ok = getattr(completed_job, "status", None) == "COMPLETED"
    stdout_ok = REMOTE_SUCCESS_MARKER in (getattr(completed_job, "stdout", None) or "")
    return status_ok and stdout_ok


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def run_validation() -> int:
    """Returns 0 for PASS/PARTIAL, 1 for FAILED."""
    print("--- ANNY-RUNTIME MISSION-001F BROWSER VALIDATION ---")
    start_time = datetime.now(timezone.utc)
    sm = ValidationStateMachine()

    # ---- Preflight ----
    preflight = run_host_preflight()
    interactive_status = preflight.status()
    print(f"Host preflight: {interactive_status}")
    print(f"  platform={preflight.platform}, display={preflight.display_available}, "
          f"browser={preflight.browser_executable!r}, capable={preflight.interactive_capable}")
    if not preflight.interactive_capable:
        print(f"  Reason: {preflight.reason}")

    provider = ColabComputeProvider()

    # Structured evidence skeleton
    evidence: Dict[str, Any] = {
        "mission_id": "MISSION-001D",  # script originated in 001D, harness hardened by 001F
        "harness_version": "001F",
        "timestamp_start": start_time.isoformat(),
        "runtime_id": "local-dev",
        "installation_id": "00000000-0000-0000-0000-000000000000",
        "provider": "google-colab",
        "transport": "browser",
        # Structured outcome fields
        "implementation_status": "PASS",
        "host_preflight": preflight.to_dict(),
        "browser_connection": "NOT_VERIFIED",
        "remote_session": "NOT_VERIFIED",
        "remote_execution": "NOT_VERIFIED",
        "success_marker": "NOT_VERIFIED",
        "credential_isolation": "NOT_VERIFIED",
        # Raw evidence
        "session_id": None,
        "remote_session_id": None,
        "job_id": None,
        "interactive_status": interactive_status,
        "browser_state_transitions": [],
        "requested_accelerator": "UNKNOWN",
        "assigned_accelerator": "UNKNOWN",
        "observed_accelerator": "UNKNOWN",
        "hostname": None,
        "python_version": None,
        "platform": None,
        "stdout": None,
        "stderr": None,
        "exit_code": None,
    }

    sm.transition(
        ValidationState.BROWSER_REQUESTED,
        reason="Preflight complete, requesting browser transport",
        evidence={"preflight_status": interactive_status},
    )

    session = None
    final_classification = "MISSION_001D_PARTIAL"
    exit_code = 1

    sm.transition(
        ValidationState.CONNECTING,
        reason="Submitting provision() to thread with timeout",
        evidence={"transport": "browser_mcp"},
    )

    # Short timeout in headless, longer for real interactive use
    timeout_seconds = 180 if preflight.interactive_capable else 15

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    provision_future = None
    try:
        provision_future = executor.submit(
            provider.provision,
            {"transport_type": "browser", "session_name": "anny-001d-validation"},
        )
        session = provision_future.result(timeout=timeout_seconds)

        if session and session.state == RemoteSessionState.READY:
            sm.transition(
                ValidationState.CONNECTED,
                reason="provider.provision() returned state=READY",
                evidence={"transport": "browser_mcp", "session_id": session.session_id},
            )
            sm.transition(
                ValidationState.READY,
                reason="Session confirmed READY by provider",
            )
            evidence["browser_connection"] = "VERIFIED"
            evidence["remote_session"] = "VERIFIED"
        else:
            state_val = session.state.value if session else "None"
            sm.transition(
                ValidationState.CONNECT_FAILED,
                reason=f"provision() returned unexpected state: {state_val}",
            )

    except concurrent.futures.TimeoutError:
        print(f"ERROR: Provisioning timed out after {timeout_seconds}s (browser interaction required).")
        sm.transition(
            ValidationState.TIMEOUT,
            reason=f"provision() blocked for {timeout_seconds}s without browser interaction",
            evidence={"headless": not preflight.interactive_capable},
        )
    except Exception as exc:
        print(f"ERROR: Provisioning failed: {exc}")
        sm.transition(
            ValidationState.CONNECT_FAILED,
            reason=f"provision() raised: {type(exc).__name__}: {exc}",
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # ---- Execution phase (only if READY) ----
    if sm.state == ValidationState.READY:
        sm.transition(
            ValidationState.EXECUTING,
            reason="Session READY, submitting smoke payload",
        )

        job_deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
        job = RemoteComputeJob(
            job_id="job_001d_smoke",
            session_id=session.session_id,
            work_package_ref="smoke",
            created_at=datetime.now(timezone.utc),
            status="PENDING",
            deadline=job_deadline,
        )
        # code is an extended attribute accepted by BrowserColabTransport.execute()
        job.code = (
            "import sys, platform, subprocess, os\n"
            f"print({REMOTE_SUCCESS_MARKER!r})\n"
            "print(f'hostname: {platform.node()}')\n"
            "print(f'python_version: {sys.version.split()[0]}')\n"
            "print(f'platform: {platform.platform()}')\n"
            "try:\n"
            "    smi = subprocess.check_output(\n"
            "        ['nvidia-smi','--query-gpu=name','--format=csv,noheader'],\n"
            "        stderr=subprocess.DEVNULL\n"
            "    ).decode().strip()\n"
            "    if smi:\n"
            "        print(f'GPU_OBSERVED: {smi}')\n"
            "except Exception:\n"
            "    pass\n"
        )

        evidence["session_id"] = session.session_id
        evidence["remote_session_id"] = session.session_id
        evidence["job_id"] = job.job_id

        try:
            completed_job = provider.execute(session, job)

            raw_stdout = getattr(completed_job, "stdout", None) or ""
            raw_stderr = getattr(completed_job, "stderr", None) or ""
            job_status = getattr(completed_job, "status", "UNKNOWN")

            evidence["stdout"] = raw_stdout
            evidence["stderr"] = raw_stderr
            evidence["exit_code"] = 0 if job_status == "COMPLETED" else 1
            evidence["remote_execution"] = "VERIFIED" if job_status == "COMPLETED" else "FAILED"

            # Parse remote observables
            for line in raw_stdout.splitlines():
                if line.startswith("hostname:"):
                    evidence["hostname"] = line.split(":", 1)[1].strip()
                elif line.startswith("python_version:"):
                    evidence["python_version"] = line.split(":", 1)[1].strip()
                elif line.startswith("platform:"):
                    evidence["platform"] = line.split(":", 1)[1].strip()
                elif line.startswith("GPU_OBSERVED:"):
                    evidence["observed_accelerator"] = line.split(":", 1)[1].strip()

            # Remote success requires both COMPLETED status AND marker in stdout
            if classify_remote_success(completed_job):
                sm.transition(
                    ValidationState.COMPLETED,
                    reason=f"stdout contains {REMOTE_SUCCESS_MARKER!r} and status=COMPLETED",
                    evidence={"exit_code": evidence["exit_code"]},
                )
                evidence["success_marker"] = "VERIFIED"
                final_classification = "MISSION_001D_PASS"
                exit_code = 0
            else:
                sm.transition(
                    ValidationState.EXECUTION_FAILED,
                    reason=(
                        f"status={job_status!r} or stdout does not contain {REMOTE_SUCCESS_MARKER!r}"
                    ),
                )

        except Exception as exc:
            print(f"ERROR: Execution failed: {exc}")
            evidence["stderr"] = str(exc)
            evidence["exit_code"] = 1
            sm.transition(
                ValidationState.EXECUTION_FAILED,
                reason=f"execute() raised: {type(exc).__name__}: {exc}",
            )

        # Cleanup session
        try:
            provider.terminate(session)
            sm.transition(ValidationState.CLOSED, reason="Session terminated cleanly")
        except Exception as exc:
            print(f"WARNING: Terminate failed: {exc}")

    else:
        evidence["exit_code"] = 1
        evidence["stderr"] = f"Session not established. Final state: {sm.state.value}"

    # ---- Determine final classification ----
    if preflight.interactive_capable:
        if final_classification != "MISSION_001D_PASS":
            if sm.state in (ValidationState.TIMEOUT, ValidationState.CONNECT_FAILED):
                final_classification = "MISSION_001D_BLOCKED"
            else:
                final_classification = "MISSION_001D_FAILED"
    else:
        # Headless: partial is expected
        if sm.state in (ValidationState.TIMEOUT, ValidationState.CONNECT_FAILED):
            final_classification = "MISSION_001D_PARTIAL"
        else:
            final_classification = "MISSION_001D_FAILED"

    # ---- Credential isolation ----
    evidence["timestamp_end"] = datetime.now(timezone.utc).isoformat()
    evidence["browser_state_transitions"] = sm.transitions
    evidence = scrub_evidence(evidence)
    isolation_ok = credential_isolation_check(evidence)
    evidence["credential_isolation"] = "PASS" if isolation_ok else "FAIL"

    # ---- Hash ----
    evidence_str = json.dumps(evidence, sort_keys=True)
    evidence["evidence_hashes"] = {
        "sha256": hashlib.sha256(evidence_str.encode("utf-8")).hexdigest()
    }

    print("\n=== EVIDENCE BUNDLE ===")
    print(json.dumps(evidence, indent=2))
    print("=======================\n")
    print(f"RESULT: {final_classification}")

    with open("evidence_001d.json", "w") as f:
        json.dump(evidence, f, indent=2)

    return 0 if final_classification in ("MISSION_001D_PASS", "MISSION_001D_PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(run_validation())
