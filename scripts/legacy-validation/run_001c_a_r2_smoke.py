import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from runtime.compute.colab import ColabComputeProvider
from runtime.compute.models import RemoteComputeJob
from datetime import datetime, timezone
import time

def run_smoke():
    provider = ColabComputeProvider()
    print("Provisioning BROWSER-assisted Colab Session...")
    session = provider.provision({"transport_type": "browser", "session_name": "anny-smoke-test-001c"})
    
    if session.state.name != "READY":
        print(f"FAILED TO PROVISION: {session.state.name} - {session.error} - {session.metadata}")
        sys.exit(1)
        
    print(f"Session state: {session.state.name}")
    print(f"Session classification: {session.classification.name}")
    
    job = RemoteComputeJob(
        job_id="smoke_job_001",
        session_id=session.session_id,
        work_package_ref="smoke",
        created_at=datetime.now(timezone.utc),
        status="PENDING",
        deadline=datetime.now(timezone.utc)
    )
    
    # Python code to execute on the remote machine
    # Prints the required output and checks GPU details
    job.code = """
import sys
import subprocess
print("ANNY_COLAB_MCP_OK")
print("Python version:", sys.version.replace('\\n', ''))
try:
    smi = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader']).decode('utf-8')
    print("GPU Info:", smi.strip())
except Exception as e:
    print("GPU Info: None or failed:", e)
"""
    print("Executing remote code...")
    completed_job = provider.execute(session, job)
    
    print("=== REMOTE OUTPUT ===")
    print(completed_job.stdout or "")
    if completed_job.stderr or completed_job.error:
        print("=== REMOTE ERROR ===")
        print(completed_job.stderr or completed_job.error)
        
    print("=====================")
    print("Job status:", completed_job.status)
    
    print("Terminating session...")
    provider.terminate(session)
    print("Done.")

if __name__ == "__main__":
    run_smoke()
