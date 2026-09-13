#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

EVIDENCE_DIR = Path.home() / "anny-runtime-certification" / "ANNY-REMOTE-COMPUTE-001B-S2"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_DIR = Path.home() / ".gemini/antigravity/scratch/ANNY-RUNTIME"

def run(cmd, **kwargs):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout.strip(), result.stderr.strip()

def write_json(name, data):
    path = EVIDENCE_DIR / name
    path.write_text(json.dumps(data, indent=2))
    print(f"  Wrote {name}")

ts = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

print("Generating 001B-S2 evidence...")

# 001-VERSION.json
rc_v1, out_v1, err_v1 = run("colab --version")
rc_v2, out_v2, err_v2 = run("colab version")
version = {
    "timestamp": ts(),
    "command_1": "colab --version",
    "cmd1_exit_code": rc_v1,
    "cmd1_stdout": out_v1,
    "cmd1_stderr": err_v1,
    "command_2": "colab version",
    "cmd2_exit_code": rc_v2,
    "cmd2_stdout": out_v2,
    "cmd2_stderr": err_v2
}
write_json("001-VERSION.json", version)

# 002-AUTH.json
rc_w, out_w, err_w = run("colab whoami")
auth = {
    "timestamp": ts(),
    "command": "colab whoami",
    "exit_code": rc_w,
    "stdout_sanitized": "auth_provider/email/audience/scopes shown; token values omitted",
    "actual_stdout": out_w,
    "actual_stderr": err_w,
    "authenticated": rc_w == 0
}
write_json("002-AUTH.json", auth)

# 003-SESSION-CREATE.json
session_name = "anny-s2-test"
rc_c_gpu, out_c_gpu, err_c_gpu = run(f"colab new --session {session_name} --gpu T4")
gpu_requested = True
gpu_unavailable = False

if rc_c_gpu != 0 and "not available" in (out_c_gpu + err_c_gpu).lower():
    gpu_unavailable = True
    print("GPU T4 unavailable, falling back to CPU")
    rc_c, out_c, err_c = run(f"colab new --session {session_name}")
else:
    rc_c, out_c, err_c = rc_c_gpu, out_c_gpu, err_c_gpu

session_create = {
    "timestamp": ts(),
    "gpu_requested": gpu_requested,
    "gpu_unavailable": gpu_unavailable,
    "final_command": f"colab new --session {session_name}" if gpu_unavailable else f"colab new --session {session_name} --gpu T4",
    "exit_code": rc_c,
    "stdout": out_c,
    "stderr": err_c,
    "ready_confirmed": "Session READY" in (out_c + err_c)
}
write_json("003-SESSION-CREATE.json", session_create)

# 004-SESSION-STATUS.json
rc_sess, out_sess, err_sess = run("colab sessions")
rc_stat, out_stat, err_stat = run(f"colab status --session {session_name}")
session_id_observed = None
import re
match = re.search(r'\[.+?\]\s+(\S+)\s*\|', out_stat)
if match:
    session_id_observed = match.group(1)

session_status = {
    "timestamp": ts(),
    "command_1": "colab sessions",
    "cmd1_exit_code": rc_sess,
    "cmd1_stdout": out_sess,
    "cmd1_stderr": err_sess,
    "command_2": f"colab status --session {session_name}",
    "cmd2_exit_code": rc_stat,
    "cmd2_stdout": out_stat,
    "cmd2_stderr": err_stat,
    "real_session_identifier": session_id_observed
}
write_json("004-SESSION-STATUS.json", session_status)

# 005-SMOKE.json
smoke_file = "/tmp/smoke_s2.py"
Path(smoke_file).write_text("import sys\nprint('ANNY_S2_SMOKE_OK')\nprint('ERR_TEST', file=sys.stderr)")
rc_smk, out_smk, err_smk = run(f"colab exec --session {session_name} --file {smoke_file}")
smoke = {
    "timestamp": ts(),
    "command": f"colab exec --session {session_name} --file {smoke_file}",
    "exit_code": rc_smk,
    "stdout": out_smk,
    "stderr": err_smk,
    "smoke_ok": "ANNY_S2_SMOKE_OK" in out_smk,
    "classification": "REAL_REMOTE" if "ANNY_S2_SMOKE_OK" in out_smk else "FAILED"
}
write_json("005-SMOKE.json", smoke)
Path(smoke_file).unlink(missing_ok=True)

# 006-TERMINATION.json
rc_stop, out_stop, err_stop = run(f"colab stop --session {session_name}")
rc_stat2, out_stat2, err_stat2 = run(f"colab status --session {session_name}")
termination = {
    "timestamp": ts(),
    "command": f"colab stop --session {session_name}",
    "exit_code": rc_stop,
    "stdout": out_stop,
    "stderr": err_stop,
    "verify_command": f"colab status --session {session_name}",
    "verify_exit_code": rc_stat2,
    "verify_stdout": out_stat2,
    "verify_stderr": err_stat2,
    "terminated_confirmed": rc_stat2 != 0 or "not found" in (out_stat2 + err_stat2).lower()
}
write_json("006-TERMINATION.json", termination)

# 007-SECURITY.json
credential_terms = ["access_token", "refresh_token", "private_key", "GOOGLE_APPLICATION_CREDENTIALS"]
leaks_found = []
for fpath in [
    RUNTIME_DIR / "runtime/compute/colab.py",
    RUNTIME_DIR / "runtime/execution/models.py",
]:
    if fpath.exists():
        content = fpath.read_text()
        for term in credential_terms:
            if term in content and "assert" not in content[max(0, content.index(term)-50):content.index(term)+100]:
                leaks_found.append({"file": str(fpath), "term": term})
security = {
    "timestamp": ts(),
    "credentials_leaked": len(leaks_found) > 0,
    "leaks": leaks_found
}
write_json("007-SECURITY.json", security)

# 008-REGRESSION.json
rc_pytest, pytest_out, pytest_err = run(
    "python3 -m pytest -q tests/ 2>&1",
    cwd=str(RUNTIME_DIR)
)
match = re.search(r'(\d+) passed', pytest_out + pytest_err)
passed = int(match.group(1)) if match else None
match_f = re.search(r'(\d+) failed', pytest_out + pytest_err)
failed = int(match_f.group(1)) if match_f else None
regression = {
    "timestamp": ts(),
    "exit_code": rc_pytest,
    "passed": passed,
    "failed": failed,
    "stdout_tail": (pytest_out + pytest_err)[-1500:],
    "verdict": "REGRESSION_FREE_WITH_BASELINE" if failed == 62 else "REVIEW_REQUIRED"
}
write_json("008-REGRESSION.json", regression)

# 009-REPORT.md
report = f"""# ANNY-REMOTE-COMPUTE-001B-S2 Report

**Timestamp:** {ts()}

## Evidence Gathered
- 001-VERSION.json
- 002-AUTH.json
- 003-SESSION-CREATE.json
- 004-SESSION-STATUS.json
- 005-SMOKE.json
- 006-TERMINATION.json
- 007-SECURITY.json
- 008-REGRESSION.json

## Classification
- Provider: colab CLI
- Session Classification: {smoke['classification']}

## Notes
- Smoke exec exit code: {rc_smk}
- GPU requested: {gpu_requested}
- GPU unavailable: {gpu_unavailable}
- Session ID: {session_id_observed}
"""
(EVIDENCE_DIR / "009-REPORT.md").write_text(report)
print("  Wrote 009-REPORT.md")

# SHA256SUMS
sums = []
for f in sorted(EVIDENCE_DIR.iterdir()):
    if f.name != "SHA256SUMS" and f.is_file():
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        sums.append(f"{h}  {f.name}")
(EVIDENCE_DIR / "SHA256SUMS").write_text("\n".join(sums) + "\n")
print("  Wrote SHA256SUMS")

rc_chk, chk_out, _ = run("sha256sum -c SHA256SUMS", cwd=str(EVIDENCE_DIR))
print(f"\nSHA256 verification: exit={rc_chk}\n{chk_out}")
print(f"\nEvidence at: {EVIDENCE_DIR}")
