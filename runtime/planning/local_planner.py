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
LOCAL_PLAN_TASK_ID_PREFIX = "ANNY-RUNTIME-LOCAL-PLAN-009"
LOCAL_PLAN_MAX_TOKENS = 1024
LOCAL_PLAN_FILE_MAX_BYTES = 16 * 1024
LOCAL_PLAN_REQUEST = (
    "Implementar initials(value: str) -> str: debe devolver en mayúsculas la primera letra de cada palabra, "
    "ignorar espacios iniciales, finales y repetidos, devolver una cadena vacía cuando la entrada esté vacía "
    "o contenga solamente espacios y lanzar TypeError para valores que no sean cadenas. Añadir pruebas "
    "unitarias para todos esos casos y conservar las pruebas preexistentes."
)


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

    def __init__(self, model_id: str, *, max_tokens: int = 256) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("Ollama model_id must be a non-empty local catalog name")
        if not isinstance(max_tokens, int) or not 1 <= max_tokens <= LOCAL_PLAN_MAX_TOKENS:
            raise ValueError("Ollama max_tokens is outside the bounded local contract")
        self.model_id = model_id
        self.max_tokens = max_tokens
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
            "format": "json", "options": {"num_predict": self.max_tokens, "temperature": 0},
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


def _fixture_plan_prompt(request: str) -> str:
    """Give the model only immutable fixture facts and a content-only contract."""
    from runtime.execution.local_repository_fixtures import get_fixture
    fixture = get_fixture("local.python.text-normalizer.fixture.v1")
    assert fixture is not None
    initial = fixture["files"]
    hashes = {path: hashlib.sha256(content.encode()).hexdigest() for path, content in initial.items()}
    return (
        "Return JSON only, with exactly this shape: "
        '{"summary":"short description","changes":[{"path":"text_normalizer.py","content":"..."},'
        '{"path":"test_text_normalizer.py","content":"..."}]}. '
        "Do not return a task_spec, commands, permissions, markdown, or extra keys. Preserve the existing "
        "test_collapses_whitespace test and add real unittest coverage for the request. Both files must be complete.\n"
        f"REQUEST:\n{request}\nFIXTURE_ID: {fixture['id']}\nFIXTURE_INITIAL_HASH: {fixture['initial_hash']}\n"
        f"INITIAL_FILE_SHA256: {json.dumps(hashes, sort_keys=True)}\n"
        f"INITIAL text_normalizer.py:\n{initial['text_normalizer.py']}\n"
        f"INITIAL test_text_normalizer.py:\n{initial['test_text_normalizer.py']}"
    )


def _build_authorized_spec(request: str, proposal: dict[str, Any]) -> dict[str, Any]:
    """Runtime, never the model, owns every executable field of the plan."""
    from runtime.execution.local_repository_fixtures import get_fixture
    fixture = get_fixture("local.python.text-normalizer.fixture.v1")
    assert fixture is not None
    task_id = f"{LOCAL_PLAN_TASK_ID_PREFIX}-{hashlib.sha256((request + fixture['initial_hash']).encode()).hexdigest()[:16]}"
    changes = [{"path": item["path"], "expected_sha256": hashlib.sha256(fixture["files"][item["path"]].encode()).hexdigest(), "content": item["content"]} for item in proposal["changes"]]
    paths = ["text_normalizer.py", "test_text_normalizer.py"]
    return {
        "task_id": task_id, "request": request, "objective": proposal["summary"],
        "execution_profile": PROFILE, "requested_capabilities": ["experimental.local.repository_change.v1"],
        "fixture_id": fixture["id"], "fixture_initial_hash": fixture["initial_hash"], "changes": changes,
        "execution_limits": {"timeout_seconds": 30, "memory_mb": 256, "cpus": 1, "pids": 64},
        "steps": [
            {"operation": "create_fixture", "arguments": {"fixture_id": fixture["id"], "initial_hash": fixture["initial_hash"]}},
            *[{"operation": "apply_patch", "arguments": change} for change in changes],
            {"operation": "read_file", "arguments": {"path": "text_normalizer.py"}},
            {"operation": "inspect_structure", "arguments": {"paths": paths}},
            {"operation": "sha256", "arguments": {"paths": paths}},
            {"operation": "run_tests", "arguments": {"command": "python-unittest-q"}},
        ], "allowed_files": paths, "allowed_test_commands": ["python-unittest-q"],
        "acceptance_criteria": ["Existing whitespace test remains", "Initials behavior has real unit tests", "Containerized unittest runner passes"],
        "evidence_references": [f"local://native-executions/{task_id}.json"], "planner": LOCAL_MODEL_PLANNER,
    }


class LocalPlanner:
    """Obtain a bounded content proposal from a verified local provider."""

    def __init__(self, discovery: LocalModelDiscovery, provider: LocalModelProvider | None = None) -> None:
        self.discovery, self.provider = discovery, provider

    def propose(self, request: str) -> dict[str, Any]:
        if not isinstance(request, str) or not request.strip():
            return {"status": "PLANNER_INVALID_REQUEST", "reason": "REQUEST_MUST_BE_NON_EMPTY"}
        if self.discovery.status != LOCAL_MODEL_READY or self.discovery.inference_status != "VERIFIED" or self.provider is None:
            return {"status": PLANNER_UNAVAILABLE, "reason": self.discovery.status, "discovery": self.discovery.to_dict()}
        try:
            raw = self.provider.complete(_fixture_plan_prompt(request), timeout_seconds=60)
        except TimeoutError:
            return {"status": "PLANNER_ERROR", "reason": "LOCAL_MODEL_TIMEOUT", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id}
        except Exception as exc:
            return {"status": "PLANNER_ERROR", "reason": f"LOCAL_MODEL_ERROR:{type(exc).__name__}", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id}
        raw_hash = hashlib.sha256(raw.encode()).hexdigest()
        if len(raw.encode()) > MAX_MODEL_RESPONSE_BYTES:
            return {"status": "PLANNER_ERROR", "reason": "MODEL_OUTPUT_TOO_LARGE", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output_hash": raw_hash}
        try:
            content_proposal = json.loads(raw)
        except json.JSONDecodeError:
            return {"status": "PLANNER_ERROR", "reason": "MALFORMED_LOCAL_MODEL_RESPONSE", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output_hash": raw_hash}
        if not isinstance(content_proposal, dict) or set(content_proposal) != {"summary", "changes"} or not isinstance(content_proposal["summary"], str) or not content_proposal["summary"].strip():
            return {"status": "PLANNER_ERROR", "reason": "MODEL_PROPOSAL_CONTRACT_INVALID", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output_hash": raw_hash}
        changes = content_proposal["changes"]
        if not isinstance(changes, list) or len(changes) != 2 or any(not isinstance(item, dict) or set(item) != {"path", "content"} or not isinstance(item["path"], str) or not isinstance(item["content"], str) or not item["content"].strip() or len(item["content"].encode()) > LOCAL_PLAN_FILE_MAX_BYTES for item in changes):
            return {"status": "PLANNER_ERROR", "reason": "MODEL_PROPOSAL_FILES_INVALID", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output_hash": raw_hash}
        if {item["path"] for item in changes} != {"text_normalizer.py", "test_text_normalizer.py"}:
            return {"status": "PLANNER_ERROR", "reason": "MODEL_PROPOSAL_FILES_NOT_ALLOWLISTED", "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output_hash": raw_hash}
        return {"status": "PROPOSED", "request": request, "content_proposal": content_proposal, "task_spec": _build_authorized_spec(request, content_proposal), "provider_id": self.provider.provider_id, "model_id": self.provider.model_id, "raw_output": raw, "raw_output_hash": raw_hash, "raw_task_spec_hash": _hash(content_proposal)}


class LocalPlanValidator:
    """Independently validate a proposal against the existing dispatcher contract."""

    def __init__(self, data_dir: str | Path, discovery: LocalModelDiscovery | None = None) -> None:
        self.executor = LocalNativeTaskExecutor(data_dir)
        self.discovery = discovery

    def validate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        required = {"status", "request", "content_proposal", "task_spec", "provider_id", "model_id", "raw_output", "raw_output_hash", "raw_task_spec_hash"}
        if not isinstance(proposal, dict) or not required.issubset(proposal) or proposal.get("status") != "PROPOSED" or not isinstance(proposal.get("task_spec"), dict):
            return {"decision": "DENY", "reason": "NO_VALID_PROPOSAL"}
        if not isinstance(proposal["raw_output"], str) or len(proposal["raw_output"].encode("utf-8")) > MAX_MODEL_RESPONSE_BYTES:
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_NOT_BOUNDED"}
        if hashlib.sha256(proposal["raw_output"].encode()).hexdigest() != proposal["raw_output_hash"]:
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_HASH_MISMATCH"}
        try:
            raw_content = json.loads(proposal["raw_output"])
        except (TypeError, json.JSONDecodeError):
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_NOT_JSON"}
        if raw_content != proposal["content_proposal"] or _hash(raw_content) != proposal["raw_task_spec_hash"]:
            return {"decision": "DENY", "reason": "MODEL_OUTPUT_AND_SUBMITTED_PROPOSAL_DIFFER"}
        changes = raw_content.get("changes") if isinstance(raw_content, dict) else None
        if not isinstance(changes, list) or {item.get("path") for item in changes if isinstance(item, dict)} != {"text_normalizer.py", "test_text_normalizer.py"} or len(changes) != 2:
            return {"decision": "DENY", "reason": "MODEL_PROPOSAL_FILES_NOT_ALLOWLISTED"}
        proposed_tests = next((item["content"] for item in changes if item["path"] == "test_text_normalizer.py"), "")
        if "test_collapses_whitespace" not in proposed_tests:
            return {"decision": "DENY", "reason": "MODEL_PROPOSAL_REMOVES_EXISTING_TEST"}
        if "initials(" not in proposed_tests:
            return {"decision": "DENY", "reason": "MODEL_PROPOSAL_LACKS_INITIALS_TEST"}
        expected_spec = _build_authorized_spec(proposal["request"], raw_content)
        if _hash(expected_spec) != _hash(proposal["task_spec"]):
            return {"decision": "DENY", "reason": "RUNTIME_PLAN_DOES_NOT_MATCH_CONTENT_PROPOSAL"}
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


def persist_plan_attempt(data_dir: str | Path, result: dict[str, Any]) -> dict[str, Any]:
    """Durably retain either an allowed execution or a blocked model proposal."""
    root = Path(data_dir) / "native-executions" / "planning"
    root.mkdir(parents=True, exist_ok=True)
    proposal = result.get("proposal", {})
    request = proposal.get("request", LOCAL_PLAN_REQUEST)
    task_id = proposal.get("task_spec", {}).get("task_id") if isinstance(proposal, dict) else None
    if not isinstance(task_id, str) or not task_id.startswith(f"{LOCAL_PLAN_TASK_ID_PREFIX}-"):
        task_id = f"{LOCAL_PLAN_TASK_ID_PREFIX}-{hashlib.sha256(str(request).encode()).hexdigest()[:16]}"
    path = root / f"{task_id}.json"
    payload = {
        "task_id": task_id, "attempt_status": result.get("status"), "request_hash": hashlib.sha256(str(request).encode()).hexdigest(),
        "proposal": result.get("proposal"), "validator": result.get("validation"), "execution": result.get("execution"),
        "evidence_ref": f"local://native-executions/planning/{task_id}.json", "completed_at": _now(),
    }
    payload["result_hash"] = _hash(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return payload


def load_plan_attempt(data_dir: str | Path) -> dict[str, Any] | None:
    root = Path(data_dir) / "native-executions" / "planning"
    candidates = sorted(root.glob(f"{LOCAL_PLAN_TASK_ID_PREFIX}-*.json"))
    if not candidates:
        return None
    try:
        value = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
