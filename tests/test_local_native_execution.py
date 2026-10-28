from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from runtime.execution.local_native import LocalNativeTaskError, LocalNativeTaskExecutor
from runtime.execution.local_task_specs import json_manifest_validation_task_spec, repository_change_task_spec, safe_slug_task_spec


def _executor(tmp_path) -> LocalNativeTaskExecutor:
    return LocalNativeTaskExecutor(tmp_path)


def test_two_registered_tasks_execute_through_generic_dispatcher_and_recover(tmp_path):
    executor = _executor(tmp_path)
    safe_slug = executor.execute(safe_slug_task_spec())
    manifest = executor.execute(json_manifest_validation_task_spec())

    assert [safe_slug["status"], manifest["status"]] == ["PASS", "PASS"]
    assert safe_slug["planner"] == manifest["planner"] == "STRUCTURED_AUTHORIZED_PLAN"
    assert safe_slug["model_provenance"] == manifest["model_provenance"] == "NO_MODEL_AVAILABLE_OR_USED"
    assert safe_slug["runner_identity"] == manifest["runner_identity"]
    assert safe_slug["runner_isolation"]["network"] == "DISABLED"
    assert safe_slug["runner_isolation"]["root_filesystem"] == "READ_ONLY"
    assert safe_slug["task_specification"]["planner"] == "STRUCTURED_AUTHORIZED_PLAN"
    assert manifest["authorization_decision"] == "ALLOW_LOCAL_DEVELOPMENT_ONLY"
    assert safe_slug["test"]["exit_code"] == manifest["test"]["exit_code"] == 0
    assert len(_executor(tmp_path).list_results()) == 2
    assert _executor(tmp_path).latest()["task_id"] == manifest["task_id"]
    assert all(Path(item["workspace"]).is_relative_to(tmp_path / "native-executions" / "workspaces") for item in (safe_slug, manifest))
    assert all(entry["change"] == "CREATED" and entry["sha256"] for item in (safe_slug, manifest) for entry in item["diff"])
    events = [json.loads(line) for line in (tmp_path / "native-executions" / "events.jsonl").read_text().splitlines()]
    assert {event["stage"] for event in events} >= {"RECEIVED", "AUTHORIZED", "WRITE_FILE", "RUN_TESTS", "VERIFIED"}


def test_safe_slug_compatibility_fixture_uses_generic_dispatcher(tmp_path):
    result = _executor(tmp_path).execute_safe_slug_demo("Implement safe_slug(text) with Unicode-safe separator normalization and unit tests.")
    assert result["task_id"] == "ANNY-RUNTIME-NATIVE-SAFE-SLUG-001"
    assert result["status"] == "PASS"


@pytest.mark.parametrize("mutate", [
    lambda spec: spec["allowed_files"].__setitem__(0, "../../outside.txt"),
    lambda spec: spec["allowed_files"].__setitem__(0, "/tmp/outside.txt"),
    lambda spec: spec.__setitem__("requested_capabilities", ["unregistered.operation.v1"]),
    lambda spec: spec["steps"].__setitem__(-1, {"operation": "run_tests", "arguments": {"command": "sh -c id"}}),
    lambda spec: spec.__setitem__("execution_profile", "PRODUCTION_PRIVILEGED"),
    lambda spec: spec.__setitem__("requested_capabilities", ["experimental.local.credentials.read.v1"]),
    lambda spec: spec.__setitem__("requested_capabilities", ["experimental.local.podman_socket.v1"]),
    lambda spec: spec.__setitem__("evidence_references", ["https://remote.invalid/evidence"]),
    lambda spec: spec.__setitem__("unexpected_permission_expansion", True),
])
def test_generic_dispatcher_denies_explicitly_prohibited_requests_without_workspace_writes(tmp_path, mutate):
    spec = safe_slug_task_spec()
    mutate(spec)
    executor = _executor(tmp_path)
    with pytest.raises(LocalNativeTaskError):
        executor.execute(spec)
    assert not list((tmp_path / "native-executions" / "workspaces").iterdir())


def test_symlink_escape_is_denied_without_external_write(tmp_path):
    executor = _executor(tmp_path)
    workspace = tmp_path / "native-executions" / "workspaces" / "probe"
    workspace.mkdir(parents=True)
    external = tmp_path / "outside.txt"
    external.write_text("unchanged", encoding="utf-8")
    (workspace / "escape.py").symlink_to(external)
    with pytest.raises(LocalNativeTaskError, match="escapes the workspace"):
        executor._safe_path(workspace, "escape.py")
    assert external.read_text(encoding="utf-8") == "unchanged"


def test_reused_task_id_with_changed_request_is_denied_and_preserves_original_result(tmp_path):
    executor = _executor(tmp_path)
    original = executor.execute(safe_slug_task_spec())
    changed = copy.deepcopy(safe_slug_task_spec())
    changed["request"] = "A different request must not reuse this task id."
    with pytest.raises(LocalNativeTaskError, match="already been used"):
        executor.execute(changed)
    restored = _executor(tmp_path).latest()
    assert restored["result_hash"] == original["result_hash"]


def test_incomplete_result_is_not_reported_as_success(tmp_path):
    spec = safe_slug_task_spec()
    spec["steps"] = [step for step in spec["steps"] if step["operation"] != "run_tests"]
    with pytest.raises(LocalNativeTaskError, match="without its required test result"):
        _executor(tmp_path).execute(spec)


def test_repository_change_executes_in_private_fixture_workspace_with_reviewable_diff(tmp_path):
    result = _executor(tmp_path).execute(repository_change_task_spec())

    assert result["status"] == "PASS"
    assert result["capability_id"] == "experimental.local.repository_change.v1"
    assert result["fixture_id"] == "local.python.text-normalizer.fixture.v1"
    assert result["fixture_initial_hash"]
    assert result["test"]["exit_code"] == 0
    assert {item["path"] for item in result["diff"]} == {"text_normalizer.py", "test_text_normalizer.py"}
    assert all(item["change"] == "MODIFIED" and item["unified_diff"].startswith("--- a/") for item in result["diff"])
    assert Path(result["workspace"]).is_relative_to(tmp_path / "native-executions" / "workspaces")
    recovered = _executor(tmp_path).list_results()
    assert recovered[0]["result_hash"] == result["result_hash"]
    events = [json.loads(line) for line in (tmp_path / "native-executions" / "events.jsonl").read_text().splitlines()]
    assert {event["stage"] for event in events} >= {"RECEIVED", "AUTHORIZED", "CREATE_FIXTURE", "APPLY_PATCH", "RUN_TESTS", "VERIFIED"}


@pytest.mark.parametrize("mutate", [
    lambda spec: spec.__setitem__("fixture_initial_hash", "0" * 64),
    lambda spec: spec["changes"][0].__setitem__("path", "../canonical.py"),
    lambda spec: spec["changes"][0].__setitem__("path", "/tmp/canonical.py"),
    lambda spec: spec["changes"].append({"path": "secret.txt", "expected_sha256": "0" * 64, "content": "no"}),
    lambda spec: spec["steps"].__setitem__(1, {"operation": "shell", "arguments": {}}),
    lambda spec: spec["steps"].__setitem__(-1, {"operation": "run_tests", "arguments": {"command": "git push"}}),
    lambda spec: spec.__setitem__("requested_capabilities", ["experimental.local.remote_repository_change.v1"]),
])
def test_repository_change_rejects_bad_fixture_patch_or_remote_authority_before_workspace_write(tmp_path, mutate):
    spec = repository_change_task_spec()
    mutate(spec)
    with pytest.raises(LocalNativeTaskError):
        _executor(tmp_path).execute(spec)
    assert not list((tmp_path / "native-executions" / "workspaces").iterdir())


def test_repository_patch_rejects_preimage_hash_change_without_modifying_target(tmp_path):
    executor = _executor(tmp_path)
    workspace = tmp_path / "native-executions" / "workspaces" / "private-repository"
    workspace.mkdir(parents=True)
    spec = repository_change_task_spec()
    _, initial = executor._create_fixture(workspace, set(spec["allowed_files"]), spec["steps"][0]["arguments"])
    target = workspace / "text_normalizer.py"
    original = target.read_text(encoding="utf-8")
    target.write_text("changed outside plan", encoding="utf-8")
    with pytest.raises(LocalNativeTaskError, match="preimage"):
        executor._apply_patch(workspace, set(spec["allowed_files"]), spec["changes"][0])
    assert target.read_text(encoding="utf-8") == "changed outside plan"
    assert initial["text_normalizer.py"] == original


def test_repository_patch_rejects_swapped_symlink_without_external_modification(tmp_path):
    executor = _executor(tmp_path)
    workspace = tmp_path / "native-executions" / "workspaces" / "private-repository"
    workspace.mkdir(parents=True)
    spec = repository_change_task_spec()
    executor._create_fixture(workspace, set(spec["allowed_files"]), spec["steps"][0]["arguments"])
    external = tmp_path / "external.py"
    external.write_text("outside unchanged", encoding="utf-8")
    target = workspace / "text_normalizer.py"
    target.unlink(); target.symlink_to(external)
    with pytest.raises(LocalNativeTaskError):
        executor._apply_patch(workspace, set(spec["allowed_files"]), spec["changes"][0])
    assert external.read_text(encoding="utf-8") == "outside unchanged"


def test_repository_change_failure_timeout_and_incomplete_are_never_success(tmp_path, monkeypatch):
    failing = repository_change_task_spec()
    failing["changes"][1]["content"] = "import unittest\nclass Broken(unittest.TestCase):\n    def test_nope(self): self.fail('expected failure')\n"
    failing["steps"][2]["arguments"] = failing["changes"][1]
    failed = _executor(tmp_path / "failed").execute(failing)
    assert failed["status"] == "FAIL" and failed["test"]["exit_code"] != 0

    timeout_executor = _executor(tmp_path / "timeout")
    monkeypatch.setattr(timeout_executor, "_run_tests", lambda *args: {"status": "FAIL", "command": "python-unittest-q", "exit_code": None, "duration_ms": 30000, "stdout": "", "stderr": "", "reason": "RUNNER_TIMEOUT"})
    timed_out = timeout_executor.execute(repository_change_task_spec())
    assert timed_out["status"] == "FAIL" and timed_out["test"]["reason"] == "RUNNER_TIMEOUT"

    incomplete = repository_change_task_spec()
    incomplete["steps"] = incomplete["steps"][:-1]
    with pytest.raises(LocalNativeTaskError, match="without its required test result"):
        _executor(tmp_path / "incomplete").execute(incomplete)
