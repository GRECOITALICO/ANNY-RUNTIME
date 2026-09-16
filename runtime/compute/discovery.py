"""Runtime Resource Discovery.

Runs remote Python code via MCP transport to observe hardware and software
resources on a remote compute session. Returns a structured profile dict.

Uses the proven AUDIT_JSON: prefix pattern from missions 001C-B R1/R2.
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Single remote snippet that probes everything in one call
_DISCOVERY_CODE = '''
import json, platform, os, subprocess, sys

result = {}

# CPU
try:
    result["cpu"] = platform.platform()
    result["cpu_count"] = os.cpu_count()
except Exception as e:
    result["cpu"] = f"ERROR: {e}"
    result["cpu_count"] = None

# RAM
try:
    import psutil
    result["ram_gb"] = round(psutil.virtual_memory().total / (1024**3), 2)
except Exception:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    result["ram_gb"] = round(kb / (1024**2), 2)
                    break
    except Exception:
        result["ram_gb"] = None

# GPU via nvidia-smi
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                          "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=10)
    if out.returncode == 0 and out.stdout.strip():
        parts = out.stdout.strip().split(", ")
        result["gpu_present"] = True
        result["gpu_name"] = parts[0] if len(parts) > 0 else "UNKNOWN"
        try:
            result["vram_gb"] = round(float(parts[1]) / 1024, 2) if len(parts) > 1 else None
        except (ValueError, IndexError):
            result["vram_gb"] = None
        result["driver_version"] = parts[2] if len(parts) > 2 else "UNKNOWN"
        result["gpu_count"] = out.stdout.strip().count("\\n") + 1
    else:
        result["gpu_present"] = False
except FileNotFoundError:
    result["gpu_present"] = False
except Exception:
    result["gpu_present"] = False

# TPU
try:
    tpu_present = os.path.exists("/dev/accel0") or "TPU" in os.environ.get("COLAB_TPU_ADDR", "")
    result["tpu_present"] = tpu_present
    if tpu_present:
        result["tpu_type"] = os.environ.get("COLAB_TPU_ADDR", "UNKNOWN")
except Exception:
    result["tpu_present"] = False

# CUDA via PyTorch
try:
    import torch
    result["cuda_available"] = torch.cuda.is_available()
    result["torch_version"] = torch.__version__
    if torch.cuda.is_available():
        result["cuda_version"] = torch.version.cuda
        result["compute_capability"] = ".".join(str(x) for x in torch.cuda.get_device_capability(0))
    else:
        result["cuda_version"] = None
except ImportError:
    result["cuda_available"] = False
    result["torch_version"] = "NOT_INSTALLED"
except Exception as e:
    result["cuda_available"] = False

# Python
result["python_version"] = sys.version.split()[0]

# Software stack
for pkg_name, import_name in [
    ("transformers_version", "transformers"),
    ("peft_version", "peft"),
    ("bitsandbytes_version", "bitsandbytes"),
    ("accelerate_version", "accelerate"),
]:
    try:
        mod = __import__(import_name)
        result[pkg_name] = getattr(mod, "__version__", "UNKNOWN")
    except ImportError:
        result[pkg_name] = "NOT_INSTALLED"
    except Exception:
        result[pkg_name] = "UNKNOWN"

# Remote execution test
result["remote_execution"] = "PASS"

# CausalLM smoke test (optional, lightweight)
try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch as _torch
    model_id = "sshleifer/tiny-gpt2"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id)
    inputs = tokenizer("ANNY runtime", return_tensors="pt")
    outputs = model.generate(**inputs, max_new_tokens=3, pad_token_id=tokenizer.eos_token_id)
    result["causallm_inference"] = "PASS"
    result["causallm_model_class"] = model.__class__.__name__
except Exception as e:
    result["causallm_inference"] = f"FAIL: {e}"
    result["causallm_model_class"] = "UNKNOWN"

print("AUDIT_JSON:", json.dumps(result))
'''


class RuntimeResourceDiscovery:
    """Discovers hardware and software resources on a remote session.

    Runs a single remote Python snippet via the MCP transport and parses
    the structured JSON output. Each field has provenance tracking.
    """

    def discover(self, transport, session) -> Dict[str, Any]:
        """Run discovery on the remote session.

        Args:
            transport: A BrowserColabTransport (or any transport with execute())
            session: The RemoteComputeSession to inspect

        Returns:
            Dict with all discovered resource fields
        """
        from runtime.compute.models import RemoteComputeJob
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        job = RemoteComputeJob(
            job_id=f"discovery-{now.strftime('%Y%m%d%H%M%S')}",
            session_id=session.session_id,
            work_package_ref="runtime_discovery",
            created_at=now,
            status="PENDING",
            deadline=now + timedelta(minutes=5),
        )
        # Attach the code to the job
        job.code = _DISCOVERY_CODE

        try:
            result_job = transport.execute(session, job)

            stdout = getattr(result_job, "stdout", "") or ""
            for line in stdout.splitlines():
                if line.startswith("AUDIT_JSON:"):
                    data = json.loads(line[len("AUDIT_JSON:"):].strip())
                    data["_discovery_timestamp"] = now.isoformat()
                    data["_discovery_status"] = "COMPLETED"
                    logger.info(f"Discovery completed: GPU={data.get('gpu_present')}, "
                                f"TPU={data.get('tpu_present')}, "
                                f"CUDA={data.get('cuda_available')}")
                    return data

            # No AUDIT_JSON line found
            logger.warning(f"Discovery output did not contain AUDIT_JSON. stdout={stdout[:500]}")
            return {
                "_discovery_status": "PARTIAL",
                "_discovery_timestamp": now.isoformat(),
                "remote_execution": "PASS",
                "_raw_output": stdout[:1000],
            }

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return {
                "_discovery_status": "FAILED",
                "_discovery_timestamp": now.isoformat(),
                "_error": str(e),
            }
