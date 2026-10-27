"""Sanitized, on-demand inventory of local inference capacity.

This module only reads host facts and fixed model-cache locations.  It never
starts a model runtime, contacts a provider, or downloads a model.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CAPACITY_SCHEMA_VERSION = 1
_CACHE_LOCATIONS = {
    "ollama": Path.home() / ".ollama" / "models",
    "huggingface": Path.home() / ".cache" / "huggingface" / "hub",
    "llama_cpp": Path.home() / ".cache" / "llama.cpp",
    "lm_studio": Path.home() / ".local" / "share" / "LM Studio" / "models",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _run(command: list[str], timeout_seconds: float = 2.0) -> dict[str, str]:
    """Return bounded stdout facts without retaining command environment data."""
    if not shutil.which(command[0]):
        return {"status": "NOT_AVAILABLE"}
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT"}
    except OSError:
        return {"status": "ERROR"}
    if completed.returncode != 0:
        return {"status": "ERROR", "exit_code": str(completed.returncode)}
    return {"status": "AVAILABLE", "stdout": completed.stdout[:4096]}


def _meminfo() -> dict[str, int | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            match = re.match(r"^(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+)\s+kB$", line)
            if match:
                values[match.group(1)] = int(match.group(2)) * 1024
    except OSError:
        pass
    return {
        "total_bytes": values.get("MemTotal"), "available_bytes": values.get("MemAvailable"),
        "swap_total_bytes": values.get("SwapTotal"), "swap_free_bytes": values.get("SwapFree"),
    }


def _cpu() -> dict[str, Any]:
    model = None
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()[:160]
                break
    except OSError:
        pass
    return {"architecture": platform.machine() or "UNKNOWN", "logical_cpus": os.cpu_count(), "model": model}


def _cache_report(label: str, path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"location": label, "status": "NOT_PRESENT", "file_count": 0, "bytes": 0, "model_entries": []}
    count = total = 0
    seen_inodes: set[tuple[int, int]] = set()
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                count += 1
                metadata = entry.stat()
                inode = (metadata.st_dev, metadata.st_ino)
                if inode not in seen_inodes:
                    seen_inodes.add(inode)
                    total += metadata.st_size
    except OSError:
        return {"location": label, "status": "UNVERIFIED", "file_count": count, "bytes": total, "model_entries": []}
    entries: list[str] = []
    if label == "huggingface":
        entries = sorted(item.name.removeprefix("models--").replace("--", "/") for item in path.glob("models--*") if item.is_dir())
    # Blob/cache presence proves only a local artifact, never runtime loadability.
    return {"location": label, "status": "PRESENT", "file_count": count, "bytes": total, "model_entries": entries}


def _gpu() -> dict[str, Any]:
    nvidia = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    if nvidia["status"] == "AVAILABLE":
        rows = [line.strip() for line in nvidia.get("stdout", "").splitlines() if line.strip()]
        return {"status": "DETECTED", "provider": "nvidia", "devices": rows}
    rocm = _run(["rocm-smi", "--showproductname", "--showmeminfo", "vram"])
    if rocm["status"] == "AVAILABLE":
        return {"status": "DETECTED", "provider": "amd", "devices": [line.strip() for line in rocm.get("stdout", "").splitlines() if line.strip()][:20]}
    return {"status": "NOT_AVAILABLE", "provider": None, "devices": []}


def _runtime_versions() -> dict[str, Any]:
    values: dict[str, Any] = {"python": platform.python_version()}
    for name, command in {
        "ollama": ["ollama", "--version"], "podman": ["podman", "version", "--format", "{{.Client.Version}}"],
        "llama_server": ["llama-server", "--version"], "lm_studio": ["lmstudio", "--version"],
    }.items():
        report = _run(command)
        values[name] = {"status": report["status"], "version": report.get("stdout", "").strip().splitlines()[-1][:160] if report.get("stdout") else None}
    return values


def _container_facts() -> dict[str, Any]:
    rootless = _run(["podman", "info", "--format", "{{.Host.Security.Rootless}}"])
    value = rootless.get("stdout", "").strip().lower() if rootless["status"] == "AVAILABLE" else None
    return {
        "podman_rootless": value == "true" if value is not None else None,
        "probe_status": rootless["status"],
        "network_note": "No container was started during capacity collection.",
    }


def collect_local_capacity() -> dict[str, Any]:
    """Collect read-only capacity facts suitable for durable sanitized evidence."""
    disk = shutil.disk_usage(Path.cwd())
    report = {
        "schema_version": CAPACITY_SCHEMA_VERSION, "collected_at": _now(), "collection_mode": "EXPLICIT_READ_ONLY",
        "cpu": _cpu(), "memory": _meminfo(),
        "disk": {"workspace_filesystem": {"total_bytes": disk.total, "free_bytes": disk.free}},
        "gpu": _gpu(), "runtimes": _runtime_versions(),
        "container": _container_facts(),
        "model_caches": [_cache_report(label, path) for label, path in _CACHE_LOCATIONS.items()],
        "model_verification": "NO_INFERENCE_ATTEMPTED",
    }
    report["result_hash"] = _hash(report)
    return report


def persist_capacity(data_dir: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    """Store a sanitized durable capacity report alongside planning evidence."""
    root = Path(data_dir) / "native-executions" / "planning"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "local-model-capacity.json"
    persisted = dict(report)
    persisted["evidence_ref"] = "local://native-executions/planning/local-model-capacity.json"
    persisted["result_hash"] = _hash({key: value for key, value in persisted.items() if key not in {"result_hash", "evidence_ref"}})
    path.write_text(json.dumps(persisted, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return persisted
