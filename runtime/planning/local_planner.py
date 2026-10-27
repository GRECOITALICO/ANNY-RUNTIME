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
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from runtime.execution.local_native import LocalNativeTaskError, LocalNativeTaskExecutor, PROFILE

LOCAL_MODEL_READY = "LOCAL_MODEL_READY"
LOCAL_RUNTIME_WITHOUT_MODEL = "LOCAL_RUNTIME_WITHOUT_MODEL"
LOCAL_MODEL_UNAVAILABLE = "LOCAL_MODEL_UNAVAILABLE"
LOCAL_MODEL_UNVERIFIED = "LOCAL_MODEL_UNVERIFIED"
PLANNER_UNAVAILABLE = "PLANNER_UNAVAILABLE"
LOCAL_MODEL_PLANNER = "LOCAL_MODEL_INFERENCE"
OLLAMA_LOOPBACK = "http://127.0.0.1:11434"
OLLAMA_TAGS_PATH = "/api/tags"
OLLAMA_GENERATE_PATH = "/api/generate"
MAX_MODEL_RESPONSE_BYTES = 64 * 1024
MAX_INFERENCE_TIMEOUT_SECONDS = 60
LOCAL_INFERENCE_TASK_ID = "ANNY-RUNTIME-LOCAL-INFERENCE-008"


class _NoRedirect(HTTPRedirectHandler):
    """Return redirect responses to the caller instead of following them."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


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
    inference_status: str = "NOT_ATTEMPTED"
    inference_checked_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "provider_id": self.provider_id,
            "client_version": self.client_version, "endpoint": self.endpoint,
            "models": list(self.models), "evidence": list(self.evidence),
            "checked_at": self.checked_at, "inference_status": self.inference_status,
            "inference_checked_at": self.inference_checked_at,
        }


@dataclass(frozen=True)
class LocalInferenceVerification:
    """Sanitized result of one explicit, non-planning local inference probe."""

    discovery: LocalModelDiscovery
    task_id: str
    model_id: str
    initial_discovery: dict[str, Any]
    started_at: str
    completed_at: str
    duration_ms: int
    timeout_seconds: float
    http_status: int | None
    validation: str
    response_hash: str | None
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "provider_id": self.discovery.provider_id,
            "model_id": self.model_id,
            "initial_discovery": self.initial_discovery,
            "inference_status": self.discovery.inference_status,
            "inference_checked_at": self.discovery.inference_checked_at,
            "http_status": self.http_status,
            "validation": self.validation,
            "duration_ms": self.duration_ms,
            "timeout_seconds": self.timeout_seconds,
            "response_hash": self.response_hash,
            "failure_reason": self.failure_reason,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "discovery": self.discovery.to_dict(),
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
    endpoint = OLLAMA_LOOPBACK + OLLAMA_TAGS_PATH
    request = Request(endpoint, headers={"Accept": "application/json"}, method="GET")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout_seconds) as response:
            if response.status != 200 or response.geturl() != endpoint:
                raise RuntimeError("OLLAMA_TAGS_REDIRECT_OR_BAD_STATUS")
            body = response.read(MAX_MODEL_RESPONSE_BYTES + 1)
            if len(body) > MAX_MODEL_RESPONSE_BYTES:
                raise RuntimeError("OLLAMA_TAGS_RESPONSE_TOO_LARGE")
            payload = json.loads(body.decode("utf-8"))
    except (HTTPError, ValueError, RuntimeError, json.JSONDecodeError):
        return LocalModelDiscovery(LOCAL_MODEL_UNVERIFIED, "ollama", version, OLLAMA_LOOPBACK, (), ("OLLAMA_TAGS_UNVERIFIED",), checked_at)
    except (URLError, OSError):
        return LocalModelDiscovery(LOCAL_RUNTIME_WITHOUT_MODEL, "ollama", version, OLLAMA_LOOPBACK, (), ("OLLAMA_CLIENT_PRESENT", "OLLAMA_LOOPBACK_UNAVAILABLE"), checked_at)
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return LocalModelDiscovery(LOCAL_MODEL_UNVERIFIED, "ollama", version, OLLAMA_LOOPBACK, (), ("OLLAMA_TAGS_RESPONSE_INVALID",), checked_at)
    names = tuple(str(item.get("name")) for item in models if isinstance(item, dict) and isinstance(item.get("name"), str))
    if not names:
        return LocalModelDiscovery(LOCAL_RUNTIME_WITHOUT_MODEL, "ollama", version, OLLAMA_LOOPBACK, (), ("OLLAMA_NO_LOCAL_MODELS",), checked_at)
    # A listed model is only detected.  It has not proved that it can infer.
    return LocalModelDiscovery(LOCAL_MODEL_UNVERIFIED, "ollama", version, OLLAMA_LOOPBACK, names, ("OLLAMA_LOOPBACK_MODELS_LISTED",), checked_at)


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


def persist_inference_verification(data_dir: str | Path, verification: LocalInferenceVerification) -> dict[str, Any]:
    """Persist probe evidence without retaining its prompt or raw model output."""
    root = Path(data_dir) / "native-executions" / "planning"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "local-inference-verification.json"
    payload = verification.to_dict()
    payload["evidence_ref"] = "local://native-executions/planning/local-inference-verification.json"
    payload["result_hash"] = _hash(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return payload


def load_inference_verification(data_dir: str | Path) -> dict[str, Any] | None:
    path = Path(data_dir) / "native-executions" / "planning" / "local-inference-verification.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


class OllamaLocalProvider:
    """Bounded Ollama adapter for the fixed local loopback API only."""
    provider_id = "ollama"

    def __init__(self, model_id: str) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("Ollama model_id must be a non-empty local catalog name")
        self.model_id = model_id
        self._opener = build_opener(_NoRedirect())
        self.last_http_status: int | None = None

    @staticmethod
    def _read_json(response: Any) -> dict[str, Any]:
        length = response.headers.get("Content-Length")
        if length and (not length.isdigit() or int(length) > MAX_MODEL_RESPONSE_BYTES):
            raise RuntimeError("OLLAMA_RESPONSE_TOO_LARGE")
        body = response.read(MAX_MODEL_RESPONSE_BYTES + 1)
        if len(body) > MAX_MODEL_RESPONSE_BYTES:
            raise RuntimeError("OLLAMA_RESPONSE_TOO_LARGE")
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("OLLAMA_INVALID_JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeError("OLLAMA_RESPONSE_NOT_OBJECT")
        return value

    def complete(self, prompt: str, *, timeout_seconds: float) -> str:
        if not isinstance(prompt, str) or not prompt or timeout_seconds <= 0 or timeout_seconds > MAX_INFERENCE_TIMEOUT_SECONDS:
            raise ValueError("Invalid bounded local-model request")
        self.last_http_status = None
        payload = json.dumps({
            "model": self.model_id, "prompt": prompt, "stream": False,
            "format": "json", "options": {"num_predict": 256, "temperature": 0},
        }).encode("utf-8")
        request = Request(
            OLLAMA_LOOPBACK + OLLAMA_GENERATE_PATH, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                self.last_http_status = response.status
                if response.status != 200 or response.geturl() != OLLAMA_LOOPBACK + OLLAMA_GENERATE_PATH:
                    raise RuntimeError(f"OLLAMA_HTTP_{response.status}")
                value = self._read_json(response)
        except HTTPError as exc:
            self.last_http_status = exc.code
            raise RuntimeError(f"OLLAMA_HTTP_{exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("OLLAMA_CONNECTION_ERROR") from exc
        answer = value.get("response")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("OLLAMA_EMPTY_RESPONSE")
        if len(answer.encode("utf-8")) > MAX_MODEL_RESPONSE_BYTES:
            raise RuntimeError("OLLAMA_RESPONSE_TOO_LARGE")
        return answer


def verify_local_inference_attempt(
    discovery: LocalModelDiscovery,
    *,
    model_id: str,
    timeout_seconds: float = MAX_INFERENCE_TIMEOUT_SECONDS,
) -> LocalInferenceVerification:
    """Probe one catalogued model without proposing or executing any task."""
    started_at = _now()
    started = datetime.now(timezone.utc)
    initial_discovery = discovery.to_dict()
    http_status: int | None = None
    response_hash: str | None = None
    validation = "NOT_RUN"
    failure_reason: str | None = None

    if not isinstance(model_id, str) or not model_id.strip():
        failure_reason = "MODEL_ID_REQUIRED"
    elif not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= MAX_INFERENCE_TIMEOUT_SECONDS:
        failure_reason = "INVALID_TIMEOUT"
    elif discovery.provider_id != "ollama" or discovery.status != LOCAL_MODEL_UNVERIFIED:
        failure_reason = "LOCAL_RUNTIME_NOT_READY"
    elif model_id not in discovery.models:
        failure_reason = "MODEL_NOT_FOUND_IN_LOCAL_CATALOG"
    else:
        provider = OllamaLocalProvider(model_id)
        try:
            response = provider.complete('Return exactly {"ok":true}.', timeout_seconds=float(timeout_seconds))
            http_status = getattr(provider, "last_http_status", None)
            response_hash = hashlib.sha256(response.encode("utf-8")).hexdigest()
            structured = json.loads(response)
            if structured != {"ok": True}:
                raise RuntimeError("OLLAMA_INFERENCE_RESPONSE_NOT_EXPECTED_JSON")
            validation = "JSON_EXACT_OK"
        except Exception as exc:
            http_status = getattr(provider, "last_http_status", None)
            failure_reason = str(exc) if str(exc).startswith("OLLAMA_") else type(exc).__name__

    completed_at = _now()
    duration_ms = max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))
    if validation == "JSON_EXACT_OK":
        result = LocalModelDiscovery(
            LOCAL_MODEL_READY, discovery.provider_id, discovery.client_version, discovery.endpoint,
            discovery.models, discovery.evidence + (f"OLLAMA_INFERENCE_VERIFIED:{model_id}",),
            discovery.checked_at, "VERIFIED", completed_at,
        )
    else:
        result = LocalModelDiscovery(
            LOCAL_MODEL_UNVERIFIED if model_id in discovery.models else discovery.status,
            discovery.provider_id, discovery.client_version, discovery.endpoint, discovery.models,
            discovery.evidence + ((f"OLLAMA_INFERENCE_FAILED:{failure_reason}",) if failure_reason else ()),
            discovery.checked_at, "FAILED", completed_at,
        )
    return LocalInferenceVerification(
        discovery=result, task_id=LOCAL_INFERENCE_TASK_ID, model_id=model_id,
        initial_discovery=initial_discovery, started_at=started_at, completed_at=completed_at,
        duration_ms=duration_ms, timeout_seconds=float(timeout_seconds), http_status=http_status,
        validation=validation, response_hash=response_hash, failure_reason=failure_reason,
    )


def verify_local_inference(discovery: LocalModelDiscovery) -> LocalModelDiscovery:
    """Backward-compatible small explicit probe used by the planning entry point."""
    if discovery.status != LOCAL_MODEL_UNVERIFIED or not discovery.models or discovery.provider_id != "ollama":
        return discovery
    return verify_local_inference_attempt(discovery, model_id=discovery.models[0], timeout_seconds=8).discovery


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
        if self.discovery.status != LOCAL_MODEL_READY or self.discovery.inference_status != "VERIFIED" or self.provider is None:
            return {"status": PLANNER_UNAVAILABLE, "reason": self.discovery.status, "discovery": self.discovery.to_dict()}
        prompt = (
            "Return JSON only: {\"task_spec\": {...}}. The task_spec must be a bounded "
            "experimental.local.repository_change.v1 plan. Never request credentials, network, "
            "remote repositories, shell commands, or paths outside its fixture workspace. The allowed "
            "test command is python-unittest-q and fixed limits are timeout_seconds=30,memory_mb=256,"
            "cpus=1,pids=64. Request: " + request
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
        return {"status": "PROPOSED", "request": request, "task_spec": task_spec, "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output": raw, "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest(), "raw_task_spec_hash": _hash(task_spec)}


class LocalPlanValidator:
    """Independently validate a proposal against the existing dispatcher contract."""

    def __init__(self, data_dir: str | Path, discovery: LocalModelDiscovery | None = None) -> None:
        self.executor = LocalNativeTaskExecutor(data_dir)
        self.discovery = discovery

    def validate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        required = {"status", "request", "task_spec", "provider_id", "model_id", "raw_output", "raw_output_hash", "raw_task_spec_hash"}
        if not isinstance(proposal, dict) or not required.issubset(proposal) or proposal.get("status") != "PROPOSED" or not isinstance(proposal.get("task_spec"), dict):
            return {"decision": "DENY", "reason": "NO_VALID_PROPOSAL"}
        if not isinstance(proposal["raw_output"], str) or len(proposal["raw_output"].encode("utf-8")) > MAX_MODEL_RESPONSE_BYTES:
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_NOT_BOUNDED"}
        if hashlib.sha256(proposal["raw_output"].encode()).hexdigest() != proposal["raw_output_hash"]:
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_HASH_MISMATCH"}
        try:
            raw_task_spec = json.loads(proposal["raw_output"])["task_spec"]
        except (KeyError, TypeError, json.JSONDecodeError):
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_NO_TASK_SPEC"}
        if not isinstance(raw_task_spec, dict) or _hash(raw_task_spec) != proposal["raw_task_spec_hash"] or _hash(raw_task_spec) != _hash(proposal["task_spec"]):
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_AND_SUBMITTED_PLAN_DIFFER"}
        if self.discovery is not None and (
            self.discovery.status != LOCAL_MODEL_READY or self.discovery.inference_status != "VERIFIED"
            or proposal["provider_id"] != self.discovery.provider_id or proposal["model_id"] not in self.discovery.models
        ):
            return {"decision": "DENY", "reason": "PROVIDER_OR_MODEL_NOT_VERIFIED_BY_DISCOVERY"}
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
            "raw_output": proposal["raw_output"], "raw_output_hash": proposal["raw_output_hash"], "task_spec_hash": _hash(validated),
            "validator": "LOCAL_PLAN_VALIDATOR_V1", "decision": "ALLOW",
        }
        return {"decision": "ALLOW", "task_spec": validated, "specification_hash": spec_hash}


class LocalPlanningOrchestrator:
    """Connect proposal, independent validation, and the existing executor."""

    def __init__(self, planner: LocalPlanner, validator: LocalPlanValidator) -> None:
        self.planner, self.validator = planner, validator

    def plan_and_execute(self, request: str) -> dict[str, Any]:
        proposal = self.planner.propose(request)
        if proposal.get("status") == PLANNER_UNAVAILABLE:
            return {"status": PLANNER_UNAVAILABLE, "proposal": proposal, "validation": None, "execution": None}
        validation = self.validator.validate(proposal)
        if validation["decision"] != "ALLOW":
            return {"status": "BLOCKED", "proposal": proposal, "validation": validation, "execution": None}
        result = self.validator.executor.execute(validation["task_spec"])
        return {"status": result["status"], "proposal": proposal, "validation": validation, "execution": result}
