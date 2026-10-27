from __future__ import annotations

import json

from runtime.planning import local_capacity


def test_command_probe_handles_missing_timeout_and_nonzero_without_output(monkeypatch):
    monkeypatch.setattr(local_capacity.shutil, "which", lambda name: None)
    assert local_capacity._run(["missing"]) == {"status": "NOT_AVAILABLE"}

    monkeypatch.setattr(local_capacity.shutil, "which", lambda name: "/fake/tool")
    monkeypatch.setattr(local_capacity.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(local_capacity.subprocess.TimeoutExpired("tool", 2)))
    assert local_capacity._run(["tool"]) == {"status": "TIMEOUT"}

    class _Failed:
        returncode, stdout = 7, "should-not-persist"
    monkeypatch.setattr(local_capacity.subprocess, "run", lambda *args, **kwargs: _Failed())
    assert local_capacity._run(["tool"]) == {"status": "ERROR", "exit_code": "7"}


def test_cache_reports_presence_as_unverified_artifact_not_loadable_model(tmp_path):
    cache = tmp_path / "hub"
    model = cache / "models--Vendor--Candidate"
    model.mkdir(parents=True)
    (model / "blob").write_bytes(b"model-ish")

    report = local_capacity._cache_report("huggingface", cache)

    assert report == {"location": "huggingface", "status": "PRESENT", "file_count": 1, "bytes": 9, "model_entries": ["Vendor/Candidate"]}
    assert local_capacity._cache_report("ollama", tmp_path / "absent")["status"] == "NOT_PRESENT"


def test_persisted_capacity_is_sanitized_and_durable(tmp_path, monkeypatch):
    monkeypatch.setattr(local_capacity, "collect_local_capacity", lambda: {
        "schema_version": 1, "collected_at": "2026-10-27T00:00:00+00:00", "collection_mode": "EXPLICIT_READ_ONLY",
        "cpu": {"architecture": "x86_64", "logical_cpus": 8, "model": "test"},
        "memory": {"total_bytes": 1, "available_bytes": 1, "swap_total_bytes": 0, "swap_free_bytes": 0},
        "disk": {"workspace_filesystem": {"total_bytes": 1, "free_bytes": 1}}, "gpu": {"status": "NOT_AVAILABLE", "provider": None, "devices": []},
        "runtimes": {}, "container": {}, "model_caches": [], "model_verification": "NO_INFERENCE_ATTEMPTED", "result_hash": "old",
    })
    result = local_capacity.persist_capacity(tmp_path, local_capacity.collect_local_capacity())
    raw = (tmp_path / "native-executions" / "planning" / "local-model-capacity.json").read_text()

    assert result["evidence_ref"] == "local://native-executions/planning/local-model-capacity.json"
    assert "home" not in raw.lower() and "/tmp" not in raw
    assert json.loads(raw)["result_hash"] == result["result_hash"]
