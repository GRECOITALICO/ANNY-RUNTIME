from __future__ import annotations

import hashlib
import json

from runtime.execution.local_task_specs import repository_change_task_spec
from runtime.admin.routes import AdminRouter
from runtime.admin.templates_cc import control_center_page
from runtime.planning.local_planner import (
    LOCAL_MODEL_PLANNER,
    LOCAL_MODEL_READY,
    LOCAL_RUNTIME_WITHOUT_MODEL,
    PLANNER_UNAVAILABLE,
    LocalModelDiscovery,
    LocalPlanValidator,
    LocalPlanner,
    LocalPlanningOrchestrator,
    OllamaLocalProvider,
    MAX_MODEL_RESPONSE_BYTES,
    load_discovery,
    persist_discovery,
    inspect_local_model_runtime,
    verify_local_inference,
)
import runtime.planning.local_planner as local_planner_module


def _ready() -> LocalModelDiscovery:
    return LocalModelDiscovery(LOCAL_MODEL_READY, "mock-local", "test", "http://127.0.0.1:9999", ("fixture-model",), ("MOCK_ONLY",), "2026-10-27T00:00:00+00:00", "VERIFIED", "2026-10-27T00:00:01+00:00")


class _Provider:
    provider_id = "mock-local"
    model_id = "fixture-model"

    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls = 0

    def complete(self, prompt: str, *, timeout_seconds: float) -> str:
        self.calls += 1
        assert "credentials" in prompt and timeout_seconds == 15
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_unavailable_local_runtime_is_explicit_and_never_calls_provider(tmp_path):
    provider = _Provider("{}")
    unavailable = LocalModelDiscovery(LOCAL_RUNTIME_WITHOUT_MODEL, "ollama", "0.32.5", "http://127.0.0.1:11434", (), ("OLLAMA_LOOPBACK_UNAVAILABLE",), "now")
    proposal = LocalPlanner(unavailable, provider).propose("Change the isolated fixture.")

    assert proposal["status"] == PLANNER_UNAVAILABLE
    assert proposal["reason"] == LOCAL_RUNTIME_WITHOUT_MODEL
    assert provider.calls == 0
    persisted = persist_discovery(tmp_path, unavailable)
    assert load_discovery(tmp_path)["result_hash"] == persisted["result_hash"]


def test_detected_ollama_model_is_unverified_until_explicit_inference(monkeypatch):
    class _Version:
        stdout, stderr = "ollama version is 0.32.5\n", ""
    class _Tags(_Response):
        def __init__(self): super().__init__(b'{"models":[{"name":"fixture-model"}]}', url="http://127.0.0.1:11434/api/tags")
    class _Opener:
        def open(self, request, timeout): return _Tags()
    monkeypatch.setattr(local_planner_module.shutil, "which", lambda name: "/usr/local/bin/ollama")
    monkeypatch.setattr(local_planner_module.subprocess, "run", lambda *args, **kwargs: _Version())
    monkeypatch.setattr(local_planner_module, "build_opener", lambda *args: _Opener())
    discovery = inspect_local_model_runtime()
    assert discovery.status == "LOCAL_MODEL_UNVERIFIED"
    assert discovery.models == ("fixture-model",)
    assert discovery.inference_status == "NOT_ATTEMPTED"


def test_invalid_or_oversized_ollama_catalog_is_not_a_ready_model(monkeypatch):
    class _Version:
        stdout, stderr = "ollama version is 0.32.5\n", ""
    class _Opener:
        def __init__(self, response): self.response = response
        def open(self, request, timeout): return self.response
    monkeypatch.setattr(local_planner_module.shutil, "which", lambda name: "/usr/local/bin/ollama")
    monkeypatch.setattr(local_planner_module.subprocess, "run", lambda *args, **kwargs: _Version())
    monkeypatch.setattr(local_planner_module, "build_opener", lambda *args: _Opener(_Response(b'{"models":"wrong"}', url="http://127.0.0.1:11434/api/tags")))
    assert inspect_local_model_runtime().status == "LOCAL_MODEL_UNVERIFIED"
    monkeypatch.setattr(local_planner_module, "build_opener", lambda *args: _Opener(_Response(b"x" * (MAX_MODEL_RESPONSE_BYTES + 1), url="http://127.0.0.1:11434/api/tags")))
    assert inspect_local_model_runtime().status == "LOCAL_MODEL_UNVERIFIED"


def test_inference_verification_requires_expected_structured_response(monkeypatch):
    class _VerifiedProvider:
        def __init__(self, model_id): self.model_id = model_id
        def complete(self, prompt, *, timeout_seconds): return '{"ok":true}'
    monkeypatch.setattr(local_planner_module, "OllamaLocalProvider", _VerifiedProvider)
    detected = LocalModelDiscovery("LOCAL_MODEL_UNVERIFIED", "ollama", "0.32.5", "http://127.0.0.1:11434", ("fixture-model",), (), "now")
    verified = verify_local_inference(detected)
    assert verified.status == LOCAL_MODEL_READY and verified.inference_status == "VERIFIED"
    class _FailingProvider(_VerifiedProvider):
        def complete(self, prompt, *, timeout_seconds): return "not-json"
    monkeypatch.setattr(local_planner_module, "OllamaLocalProvider", _FailingProvider)
    failed = verify_local_inference(detected)
    assert failed.status == "LOCAL_MODEL_UNVERIFIED" and failed.inference_status == "FAILED"


def test_malformed_error_and_timeout_responses_do_not_execute(tmp_path):
    planner = LocalPlanner(_ready(), _Provider("not json"))
    malformed = planner.propose("Change fixture")
    assert malformed["status"] == "PLANNER_ERROR"
    assert LocalPlanValidator(tmp_path).validate(malformed)["decision"] == "DENY"

    timeout = LocalPlanner(_ready(), _Provider(TimeoutError())).propose("Change fixture")
    assert timeout["reason"] == "LOCAL_MODEL_TIMEOUT"
    assert not list((tmp_path / "native-executions" / "workspaces").iterdir())


def test_independent_validator_blocks_model_permission_expansion_without_execution(tmp_path):
    spec = repository_change_task_spec()
    spec["allowed_files"][0] = "../../escape.py"
    raw = json.dumps({"task_spec": spec})
    proposal = {"status": "PROPOSED", "request": "test", "task_spec": spec, "provider_id": "mock-local", "model_id": "fixture-model", "raw_output": raw, "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest(), "raw_task_spec_hash": hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    decision = LocalPlanValidator(tmp_path).validate(proposal)

    assert decision["decision"] == "DENY"
    assert not list((tmp_path / "native-executions" / "workspaces").iterdir())


def test_valid_mocked_local_model_plan_is_validated_then_uses_existing_dispatcher(tmp_path):
    spec = repository_change_task_spec()
    raw = json.dumps({"task_spec": spec})
    orchestrator = LocalPlanningOrchestrator(LocalPlanner(_ready(), _Provider(raw)), LocalPlanValidator(tmp_path))

    result = orchestrator.plan_and_execute("Add display-name normalization to the isolated Python fixture.")

    assert result["validation"]["decision"] == "ALLOW"
    assert result["execution"]["status"] == "PASS"
    assert result["execution"]["planner"] == LOCAL_MODEL_PLANNER
    assert result["execution"]["planning_evidence"]["provider_id"] == "mock-local"
    assert result["execution"]["test"]["exit_code"] == 0


def test_model_cannot_select_unknown_capability_or_remote_command(tmp_path):
    unknown = repository_change_task_spec()
    unknown["requested_capabilities"] = ["remote.shell.v1"]
    raw = json.dumps({"task_spec": unknown})
    result = LocalPlanningOrchestrator(LocalPlanner(_ready(), _Provider(raw)), LocalPlanValidator(tmp_path)).plan_and_execute("unsafe")

    assert result["status"] == "BLOCKED"
    assert result["execution"] is None
    assert not list((tmp_path / "native-executions" / "workspaces").iterdir())


def test_control_center_exposes_persisted_planner_state_without_starting_a_model(tmp_path, monkeypatch):
    monkeypatch.setenv("ANNY_DATA_DIR", str(tmp_path))
    router = AdminRouter({})
    router.handle_local_planner_status(None)

    assert router.context["direct_json_response"]["status"] in {"LOCAL_RUNTIME_WITHOUT_MODEL", "LOCAL_MODEL_UNAVAILABLE", "LOCAL_MODEL_UNVERIFIED", "LOCAL_MODEL_READY"}
    assert "/api/local-planner/status" in control_center_page("csrf-test")


class _Response:
    def __init__(self, body: bytes, *, status: int = 200, url: str = "http://127.0.0.1:11434/api/generate", length: str | None = None) -> None:
        self._body, self.status, self._url = body, status, url
        self.headers = {} if length is None else {"Content-Length": length}

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def geturl(self) -> str:
        return self._url

    def __enter__(self): return self
    def __exit__(self, *args): return False


def test_ollama_adapter_uses_fixed_loopback_json_contract_and_bounds_response(monkeypatch):
    provider = OllamaLocalProvider("fixture-model")
    seen = {}
    def open_request(request, timeout):
        seen["url"], seen["timeout"], seen["body"] = request.full_url, timeout, json.loads(request.data)
        return _Response(b'{"response":"{\\"ok\\": true}"}')
    monkeypatch.setattr(provider._opener, "open", open_request)

    assert provider.complete("small prompt", timeout_seconds=8) == '{"ok": true}'
    assert seen["url"] == "http://127.0.0.1:11434/api/generate"
    assert seen["timeout"] == 8
    assert seen["body"] == {"model": "fixture-model", "prompt": "small prompt", "stream": False, "format": "json", "options": {"num_predict": 256, "temperature": 0}}

    monkeypatch.setattr(provider._opener, "open", lambda *args, **kwargs: _Response(b"{}", status=302, url="http://example.invalid/"))
    with __import__("pytest").raises(RuntimeError, match="OLLAMA_HTTP_302"):
        provider.complete("small prompt", timeout_seconds=8)
    monkeypatch.setattr(provider._opener, "open", lambda *args, **kwargs: _Response(b"{}", length=str(MAX_MODEL_RESPONSE_BYTES + 1)))
    with __import__("pytest").raises(RuntimeError, match="TOO_LARGE"):
        provider.complete("small prompt", timeout_seconds=8)


def test_validator_rejects_tampered_model_plan_or_unverified_provider_before_workspace(tmp_path):
    spec = repository_change_task_spec()
    raw = json.dumps({"task_spec": spec})
    proposal = LocalPlanner(_ready(), _Provider(raw)).propose("fixture change")
    proposal["task_spec"] = repository_change_task_spec()
    proposal["task_spec"]["request"] = "tampered after inference"
    decision = LocalPlanValidator(tmp_path, _ready()).validate(proposal)
    assert decision["reason"] == "MODEL_OUTPUT_AND_SUBMITTED_PLAN_DIFFER"
    assert not list((tmp_path / "native-executions" / "workspaces").iterdir())

    proposal = LocalPlanner(_ready(), _Provider(raw)).propose("fixture change")
    wrong = LocalModelDiscovery(LOCAL_MODEL_READY, "ollama", "x", "http://127.0.0.1:11434", ("other",), (), "now", "VERIFIED", "now")
    assert LocalPlanValidator(tmp_path, wrong).validate(proposal)["reason"] == "PROVIDER_OR_MODEL_NOT_VERIFIED_BY_DISCOVERY"
