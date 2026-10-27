from __future__ import annotations

import copy
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
    load_discovery,
    persist_discovery,
)


def _ready() -> LocalModelDiscovery:
    return LocalModelDiscovery(LOCAL_MODEL_READY, "mock-local", "test", "http://127.0.0.1:9999", ("fixture-model",), ("MOCK_ONLY",), "2026-10-27T00:00:00+00:00")


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
    proposal = {"status": "PROPOSED", "task_spec": spec, "provider_id": "mock-local", "model_id": "fixture-model", "raw_output": "{}", "raw_output_hash": __import__("hashlib").sha256(b"{}").hexdigest()}
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
