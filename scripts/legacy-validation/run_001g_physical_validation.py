#!/usr/bin/env python3
"""
MISSION-001G-P Physical Validation Script.
Executes the specific GPU/CPU audits required by the user via Colab MCP.
"""

import sys
import os
import time
import json
import hashlib
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from runtime.compute.colab import ColabComputeProvider
from runtime.compute.models import RemoteComputeJob, RemoteSessionState

def run():
    print("--- 001G-P PHYSICAL VALIDATION ---")
    provider = ColabComputeProvider()

    print("Provisioning session (please log into Colab in the managed browser)...")
    try:
        session = provider.provision({"transport_type": "browser", "session_name": "001g-val"})
    except Exception as e:
        print(f"Provision failed: {e}")
        return

    if session.state != RemoteSessionState.READY:
        print(f"Session not ready: {session.state}")
        return

    print("Session READY. Running tests...")

    def run_code(name, code):
        print(f"\n--- Running {name} ---")
        job = RemoteComputeJob(
            job_id=f"job_{name}",
            session_id=session.session_id,
            work_package_ref="test",
            created_at=datetime.now(timezone.utc),
            status="PENDING",
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        job.code = code
        res = provider.execute(session, job)
        out = getattr(res, "stdout", "")
        err = getattr(res, "stderr", "")
        status = getattr(res, "status", "UNKNOWN")
        print(f"Status: {status}")
        if out: print(f"STDOUT:\n{out}")
        if err: print(f"STDERR:\n{err}")
        return out

    # PASO 5: ANNY_COLAB_MCP_OK
    code_paso5 = 'print("ANNY_COLAB_MCP_OK")'
    out5 = run_code("PASO5", code_paso5)

    # PASO 7: CPU/RAM
    code_paso7 = """
import os, platform, psutil
print("CPU:", platform.processor())
print("MACHINE:", platform.machine())
print("PYTHON:", platform.python_version())
print("CPU_COUNT_LOGICAL:", psutil.cpu_count(logical=True))
print("RAM_GB:", round(psutil.virtual_memory().total / (1024**3), 2))
"""
    out7 = run_code("PASO7", code_paso7)

    # Check GPU availability first via torch
    code_check_gpu = """
try:
    import torch
    print("TORCH_CUDA:", torch.cuda.is_available())
except:
    print("TORCH_CUDA: False")
"""
    out_gpu = run_code("CHECK_GPU", code_check_gpu)
    has_gpu = "TORCH_CUDA: True" in out_gpu

    if has_gpu:
        # PASO 6: GPU Audit
        code_paso6 = """
import platform, torch
print("PLATFORM:", platform.platform())
print("TORCH_VERSION:", torch.__version__)
print("CUDA_AVAILABLE:", torch.cuda.is_available())
print("GPU_NAME:", torch.cuda.get_device_name(0))
props = torch.cuda.get_device_properties(0)
print("VRAM_BYTES:", props.total_memory)
print("VRAM_GB:", round(props.total_memory / (1024**3), 2))
print("COMPUTE_CAPABILITY:", f"{props.major}.{props.minor}")
"""
        run_code("PASO6", code_paso6)

        # PASO 8: CUDA Tensor test
        code_paso8 = """
import torch
print("CUDA_AVAILABLE:", torch.cuda.is_available())
device = torch.device("cuda")
x = torch.randn((1024, 1024), device=device)
y = torch.randn((1024, 1024), device=device)
z = x @ y
torch.cuda.synchronize()
print("CUDA_TENSOR_TEST: PASS")
print("RESULT_SHAPE:", tuple(z.shape))
"""
        run_code("PASO8", code_paso8)
    else:
        print("\nNo GPU detected. Skipping GPU tests.")

    print("\nCleaning up...")
    provider.terminate(session)
    print("Done.")

if __name__ == "__main__":
    run()
