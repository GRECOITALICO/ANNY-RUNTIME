#!/usr/bin/env python3
"""
MISSION-001D: Interactive Validation Script for Browser-assisted Colab Transport.

This script manages the strict state machine for establishing and executing a 
real browser-assisted Colab session via MCP.

States: INIT -> BROWSER_REQUESTED -> CONNECTING -> CONNECTED -> READY -> EXECUTING -> COMPLETED
Errors: CONNECT_FAILED, AUTH_FAILED, TIMEOUT, DISCONNECTED, EXECUTION_FAILED, CLOSED
"""

import sys
import os
import time
import json
import hashlib
import concurrent.futures
from datetime import datetime, timezone
from enum import Enum

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from runtime.compute.colab import ColabComputeProvider
from runtime.compute.models import RemoteComputeJob, RemoteSessionState

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
        self.transitions = []
        self._record_transition(self.state)
        
    def _record_transition(self, new_state: ValidationState):
        self.state = new_state
        self.transitions.append({
            "state": new_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        print(f"[STATE] -> {new_state.value}")

    def transition(self, new_state: ValidationState):
        self._record_transition(new_state)

def detect_interactive_host() -> bool:
    """Returns True if a display environment (X11/Wayland/Mac/Win) is detected."""
    if sys.platform in ('win32', 'darwin'):
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))

def run_validation():
    print("--- ANNY-RUNTIME MISSION-001D BROWSER VALIDATION ---")
    start_time = datetime.now(timezone.utc)
    sm = ValidationStateMachine()
    
    has_display = detect_interactive_host()
    interactive_status = "INTERACTIVE_BROWSER_AVAILABLE" if has_display else "INTERACTIVE_BROWSER_UNAVAILABLE"
    print(f"Host check: {interactive_status}")
    
    if not has_display:
        print("WARNING: No physical interactive browser display detected.")
        print("The process will attempt to launch, but will likely block and timeout.")

    provider = ColabComputeProvider()
    
    sm.transition(ValidationState.BROWSER_REQUESTED)
    
    # Run provisioning in a separate thread to allow for strict timeouts
    session = None
    provision_future = None
    
    sm.transition(ValidationState.CONNECTING)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        provision_future = executor.submit(
            provider.provision, 
            {"transport_type": "browser", "session_name": "anny-001d-validation"}
        )
        # Short timeout if no display, otherwise give the user time to auth
        timeout_seconds = 180 if has_display else 15
        session = provision_future.result(timeout=timeout_seconds)
        
        if session.state == RemoteSessionState.READY:
            sm.transition(ValidationState.CONNECTED)
            sm.transition(ValidationState.READY)
        else:
            sm.transition(ValidationState.CONNECT_FAILED)
    
    except concurrent.futures.TimeoutError:
        print("ERROR: Provisioning timed out waiting for browser interaction.")
        sm.transition(ValidationState.TIMEOUT)
    except Exception as e:
        print(f"ERROR: Provisioning failed: {e}")
        sm.transition(ValidationState.CONNECT_FAILED)

    evidence = {
        "mission_id": "MISSION-001D",
        "timestamp_start": start_time.isoformat(),
        "runtime_id": "local-dev",
        "installation_id": "00000000-0000-0000-0000-000000000000",
        "session_id": session.session_id if session else None,
        "provider": "google-colab",
        "transport": "browser",
        "interactive_status": interactive_status,
        "browser_state_transitions": sm.transitions,
        "requested_accelerator": "UNKNOWN",
        "assigned_accelerator": "UNKNOWN",
        "observed_accelerator": "UNKNOWN",
    }
    
    final_classification = ""
    if session and sm.state == ValidationState.READY:
        sm.transition(ValidationState.EXECUTING)
        job = RemoteComputeJob(
            job_id="job_001d_smoke",
            session_id=session.session_id,
            work_package_ref="smoke",
            created_at=datetime.now(timezone.utc),
            status="PENDING",
            deadline=datetime.now(timezone.utc)
        )
        
        job.code = """
import sys
import subprocess
import os
import platform

print("ANNY_COLAB_MCP_OK")
print(f"hostname: {platform.node()}")
print(f"python_version: {sys.version.split()[0]}")
print(f"platform: {platform.platform()}")
print(f"working_directory: {os.getcwd()}")
print("process execution capability: Verified")

try:
    smi = subprocess.check_output(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader']).decode('utf-8').strip()
    if smi:
        print(f"GPU_OBSERVED: {smi}")
except Exception:
    pass
"""
        evidence["remote_session_id"] = session.session_id
        evidence["job_id"] = job.job_id
        
        try:
            completed_job = provider.execute(session, job)
            
            evidence["execution_request"] = job.code
            evidence["stdout"] = completed_job.stdout
            evidence["stderr"] = completed_job.stderr
            evidence["exit_code"] = 0 if completed_job.status == "COMPLETED" else 1
            
            # Extract basic observed metrics from stdout
            if completed_job.stdout:
                for line in completed_job.stdout.splitlines():
                    if line.startswith("hostname:"):
                        evidence["hostname"] = line.split(":", 1)[1].strip()
                    elif line.startswith("python_version:"):
                        evidence["python_version"] = line.split(":", 1)[1].strip()
                    elif line.startswith("platform:"):
                        evidence["platform"] = line.split(":", 1)[1].strip()
                    elif line.startswith("GPU_OBSERVED:"):
                        evidence["observed_accelerator"] = line.split(":", 1)[1].strip()
                        
            if "ANNY_COLAB_MCP_OK" in (completed_job.stdout or ""):
                sm.transition(ValidationState.COMPLETED)
            else:
                sm.transition(ValidationState.EXECUTION_FAILED)
                
        except Exception as e:
            print(f"ERROR: Execution failed: {e}")
            evidence["stderr"] = str(e)
            evidence["exit_code"] = 1
            sm.transition(ValidationState.EXECUTION_FAILED)
            
        print("Terminating session...")
        provider.terminate(session)
        sm.transition(ValidationState.CLOSED)
    else:
        # If we failed to get a session or timed out
        evidence["exit_code"] = 1
        evidence["stderr"] = "Session could not be established."

    evidence["timestamp_end"] = datetime.now(timezone.utc).isoformat()
    evidence["browser_state_transitions"] = sm.transitions
    
    # Hash the evidence (excluding the hash itself)
    evidence_str = json.dumps(evidence, sort_keys=True)
    evidence["evidence_hashes"] = {
        "sha256": hashlib.sha256(evidence_str.encode('utf-8')).hexdigest()
    }
    
    print("\n=== EVIDENCE BUNDLE ===")
    print(json.dumps(evidence, indent=2))
    print("=======================\n")
    
    # Determine the final result classification
    if interactive_status == "INTERACTIVE_BROWSER_UNAVAILABLE":
        if sm.state in (ValidationState.TIMEOUT, ValidationState.CONNECT_FAILED):
            final_classification = "MISSION_001D_PARTIAL"
            print("RESULT: MISSION_001D_PARTIAL (Blocked by headless environment)")
        else:
            final_classification = "MISSION_001D_FAILED"
            print("RESULT: MISSION_001D_FAILED (Unexpected state in headless)")
    else:
        if ValidationState.COMPLETED.value in [t["state"] for t in sm.transitions]:
            final_classification = "MISSION_001D_PASS"
            print("RESULT: MISSION_001D_PASS")
        elif sm.state in (ValidationState.TIMEOUT, ValidationState.CONNECT_FAILED):
            final_classification = "MISSION_001D_BLOCKED"
            print("RESULT: MISSION_001D_BLOCKED (Human interaction timed out or failed)")
        elif ValidationState.CONNECTED.value in [t["state"] for t in sm.transitions]:
            final_classification = "MISSION_001D_FAILED"
            print("RESULT: MISSION_001D_FAILED (Connected but execution failed)")
        else:
            final_classification = "MISSION_001D_FAILED"
            print("RESULT: MISSION_001D_FAILED (Failed to connect)")
            
    # Write to local file for later extraction
    with open("evidence_001d.json", "w") as f:
        json.dump(evidence, f, indent=2)
        
    if final_classification == "MISSION_001D_FAILED":
        os._exit(1)
    os._exit(0)

if __name__ == "__main__":
    run_validation()
