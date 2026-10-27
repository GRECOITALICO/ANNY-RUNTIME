"""Fail-closed local-model planning boundary.

Model output is untrusted data.  This module can propose a task specification,
but it never grants authority, registers a capability, starts a shell, or
executes a task.  A separate validator must accept a proposal before the
existing native dispatcher is called.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from runtime.execution.local_native import LocalNativeTaskError, LocalNativeTaskExecutor, PROFILE

LOCAL_MODEL_READY = "LOCAL_MODEL_READY"
LOCAL_RUNTIME_WITHOUT_MODEL = "LOCAL_RUNTIME_WITHOUT_MODEL"
LOCAL_MODEL_UNAVAILABLE = "LOCAL_MODEL_UNAVAILABLE"
LOCAL_MODEL_UNVERIFIED = "LOCAL_MODEL_UNVERIFIED"
PLANNER_UNAVAILABLE = "PLANNER_UNAVAILABLE"
LOCAL_MODEL_PLANNER = "LOCAL_MODEL_INFERENCE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class LocalModelDiscovery:
    status: str
    provider_id: str | None
    client_version: str | None
    endpoint: str | None
    models: tuple[str, ...]
    evidence: tuple[str, ...]
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "provider_id": self.provider_id,
            "client_version": self.client_version, "endpoint": self.endpoint,
            "models": list(self.models), "evidence": list(self.evidence),
            "checked_at": self.checked_at,
        }


def inspect_local_model_runtime(*, timeout_seconds: float = 2.0) -> LocalModelDiscovery:
    """Inspect only the already-installed Ollama client and loopback service."""
    checked_at = _now()
    executable = shutil.which("ollama")
    if not executable:
        return LocalModelDiscovery(LOCAL_MODEL_UNAVAILABLE, None, None, None, (), ("OLLAMA_EXECUTABLE_NOT_FOUND",), checked_at)
    try:
        version_process = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=timeout_seconds, check=False)
        version = (version_process.stdout or version_process.stderr).strip().splitlines()[-1][:120] or None
    except (OSError, subprocess.SubprocessError):
        return LocalModelDiscovery(LOCAL_MODEL_UNVERIFIED, "ollama", None, "http://127.0.0.1:11434", (), ("OLLAMA_VERSION_CHECK_FAILED",), checked_at)
    endpoint = "http://127.0.0.1:11434/api/tags"
    request = Request(endpoint, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return LocalModelDiscovery(LOCAL_RUNTIME_WITHOUT_MODEL, "ollama", version, "http://127.0.0.1:11434", (), ("OLLAMA_CLIENT_PRESENT", "OLLAMA_LOOPBACK_UNAVAILABLE"), checked_at)
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return LocalModelDiscovery(LOCAL_MODEL_UNVERIFIED, "ollama", version, "http://127.0.0.1:11434", (), ("OLLAMA_TAGS_RESPONSE_INVALID",), checked_at)
    names = tuple(str(item.get("name")) for item in models if isinstance(item, dict) and isinstance(item.get("name"), str))
    if not names:
        return LocalModelDiscovery(LOCAL_RUNTIME_WITHOUT_MODEL, "ollama", version, "http://127.0.0.1:11434", (), ("OLLAMA_NO_LOCAL_MODELS",), checked_at)
    return LocalModelDiscovery(LOCAL_MODEL_READY, "ollama", version, "http://127.0.0.1:11434", names, ("OLLAMA_LOOPBACK_MODELS_LISTED",), checked_at)


def persist_discovery(data_dir: str | Path, discovery: LocalModelDiscovery) -> dict[str, Any]:
    """Persist sanitized inspection facts; no environment or credential data is stored."""
    root = Path(data_dir) / "native-executions" / "planning"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "local-model-discovery.json"
    payload = discovery.to_dict()
    payload["evidence_ref"] = "local://native-executions/planning/local-model-discovery.json"
    payload["result_hash"] = _hash(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return payload


def load_discovery(data_dir: str | Path) -> dict[str, Any] | None:
    path = Path(data_dir) / "native-executions" / "planning" / "local-model-discovery.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


class LocalModelProvider(Protocol):
    provider_id: str
    model_id: str

    def complete(self, prompt: str, *, timeout_seconds: float) -> str: ...


class LocalPlanner:
    """Obtain a proposal from a verified local provider, never an execution."""

    def __init__(self, discovery: LocalModelDiscovery, provider: LocalModelProvider | None = None) -> None:
        self.discovery, self.provider = discovery, provider

    def propose(self, request: str) -> dict[str, Any]:
        if not isinstance(request, str) or not request.strip():
            return {"status": "PLANNER_INVALID_REQUEST", "reason": "REQUEST_MUST_BE_NON_EMPTY"}
        if self.discovery.status != LOCAL_MODEL_READY or self.provider is None:
            return {"status": PLANNER_UNAVAILABLE, "reason": self.discovery.status, "discovery": self.discovery.to_dict()}
        prompt = (
            "Return JSON only: {\"task_spec\": {...}}. The task_spec must be a bounded "
            "experimental.local.repository_change.v1 plan. Never request credentials, network, "
            "remote repositories, shell commands, or paths outside its fixture workspace. Request: " + request
        )
        try:
            raw = self.provider.complete(prompt, timeout_seconds=15)
        except TimeoutError:
            return {"status": "PLANNER_ERROR", "reason": "LOCAL_MODEL_TIMEOUT", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id}
        except Exception as exc:
            return {"status": "PLANNER_ERROR", "reason": f"LOCAL_MODEL_ERROR:{type(exc).__name__}", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id}
        try:
            payload = json.loads(raw)
            task_spec = payload["task_spec"]
        except (TypeError, KeyError, json.JSONDecodeError):
            return {"status": "PLANNER_ERROR", "reason": "MALFORMED_LOCAL_MODEL_RESPONSE", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output_hash": hashlib.sha256(str(raw).encode()).hexdigest()}
        if not isinstance(task_spec, dict):
            return {"status": "PLANNER_ERROR", "reason": "MODEL_PLAN_NOT_OBJECT", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest()}
        return {"status": "PROPOSED", "request": request, "task_spec": task_spec, "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output": raw, "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest()}


class LocalPlanValidator:
    """Independently validate a proposal against the existing dispatcher contract."""

    def __init__(self, data_dir: str | Path) -> None:
        self.executor = LocalNativeTaskExecutor(data_dir)

    def validate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        if proposal.get("status") != "PROPOSED" or not isinstance(proposal.get("task_spec"), dict):
            return {"decision": "DENY", "reason": "NO_VALID_PROPOSAL"}
        spec = dict(proposal["task_spec"])
        # Validate all executable fields under the pre-existing closed contract
        # before attaching provenance controlled by this boundary.
        spec["planner"] = "STRUCTURED_AUTHORIZED_PLAN"
        try:
            validated, capability, spec_hash = self.executor._validate_spec(spec)
        except LocalNativeTaskError as exc:
            return {"decision": "DENY", "reason": str(exc)}
        if capability["id"] != "experimental.local.repository_change.v1":
            return {"decision": "DENY", "reason": "LOCAL_PLANNER_CAPABILITY_NOT_ALLOWED"}
        validated["planner"] = LOCAL_MODEL_PLANNER
        validated["planning_evidence"] = {
            "provider_id": proposal["provider_id"], "model_id": proposal["model_id"],
            "raw_output": proposal["raw_output"], "raw_output_hash": proposal["raw_output_hash"],
            "validator": "LOCAL_PLAN_VALIDATOR_V1", "decision": "ALLOW",
        }
        return {"decision": "ALLOW", "task_spec": validated, "specification_hash": spec_hash}


class LocalPlanningOrchestrator:
    """Connect proposal, independent validation, and the existing executor."""

    def __init__(self, planner: LocalPlanner, validator: LocalPlanValidator) -> None:
        self.planner, self.validator = planner, validator

    def plan_and_execute(self, request: str) -> dict[str, Any]:
        proposal = self.planner.propose(request)
        validation = self.validator.validate(proposal)
        if validation["decision"] != "ALLOW":
            return {"status": "BLOCKED", "proposal": proposal, "validation": validation, "execution": None}
        result = self.validator.executor.execute(validation["task_spec"])
        return {"status": result["status"], "proposal": proposal, "validation": validation, "execution": result}
