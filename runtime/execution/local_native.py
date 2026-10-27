"""Closed-contract local task execution with durable evidence.

This is not a shell wrapper.  It dispatches a small, strict task contract to a
rootless Podman runner; task-specific source belongs in ``local_task_specs``.
"""
from __future__ import annotations

import hashlib
import difflib
import json
import os
import re
import shutil
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE = "LOCAL_DEVELOPMENT_RESTRICTED"
RUNNER_IMAGE = "docker.io/library/python:3.13-slim-bookworm"
RUNNER_IDENTITY = "ANNY_RUNTIME_NATIVE:podman-rootless-python-unittest-allowlist"
PLANNER = "STRUCTURED_AUTHORIZED_PLAN"


class LocalNativeTaskError(RuntimeError):
    """A task violated the local-native execution contract."""


_OPERATIONS = {"write_file", "read_file", "inspect_structure", "sha256", "run_tests"}
_REPOSITORY_OPERATIONS = {"create_fixture", "apply_patch", "read_file", "inspect_structure", "sha256", "run_tests"}
CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "experimental.local.safe_slug.v1": {
        "id": "experimental.local.safe_slug.v1", "version": "v1",
        "input_contract": "structured local task specification", "output_contract": "durable execution result",
        "tools": ["runtime.filesystem.write", "runtime.filesystem.read", "runtime.filesystem.inspect", "runtime.filesystem.sha256", "runtime.python.unittest"],
        "permissions": ["task-workspace:write", "task-workspace:read", "runner:python-unittest"],
        "workspace": "task-private-workspace", "execution_profile": PROFILE, "tests": ["python-unittest-q"],
        "implementation_status": "EXPERIMENTAL_LOCAL_PROVISIONAL", "verification_status": "VERIFIED_BY_DURABLE_LOCAL_EVIDENCE",
        "provenance": "ANNY_RUNTIME_NATIVE", "evidence": "local://native-executions/", "operations": _OPERATIONS,
    },
    "experimental.local.json_manifest_validation.v1": {
        "id": "experimental.local.json_manifest_validation.v1", "version": "v1",
        "input_contract": "structured local task specification", "output_contract": "durable execution result",
        "tools": ["runtime.filesystem.write", "runtime.filesystem.read", "runtime.filesystem.inspect", "runtime.filesystem.sha256", "runtime.python.unittest"],
        "permissions": ["task-workspace:write", "task-workspace:read", "runner:python-unittest"],
        "workspace": "task-private-workspace", "execution_profile": PROFILE, "tests": ["python-unittest-q"],
        "implementation_status": "EXPERIMENTAL_LOCAL_PROVISIONAL", "verification_status": "VERIFIED_BY_DURABLE_LOCAL_EVIDENCE",
        "provenance": "ANNY_RUNTIME_NATIVE", "evidence": "local://native-executions/", "operations": _OPERATIONS,
    },
    "experimental.local.repository_change.v1": {
        "id": "experimental.local.repository_change.v1", "version": "v1",
        "input_contract": "structured isolated repository fixture change plan", "output_contract": "durable repository diff and test result",
        "tools": ["runtime.fixture.copy", "runtime.filesystem.patch", "runtime.filesystem.read", "runtime.filesystem.inspect", "runtime.filesystem.sha256", "runtime.python.unittest"],
        "permissions": ["task-private-fixture:copy", "task-workspace:write", "task-workspace:read", "runner:python-unittest"],
        "workspace": "task-private-repository-workspace", "execution_profile": PROFILE, "tests": ["python-unittest-q"],
        "implementation_status": "EXPERIMENTAL_LOCAL_PROVISIONAL", "verification_status": "VERIFIED_BY_DURABLE_LOCAL_EVIDENCE",
        "provenance": "ANNY_RUNTIME_NATIVE", "evidence": "local://native-executions/", "operations": _REPOSITORY_OPERATIONS,
    },
}
_TASK_FIELDS = {"task_id", "request", "objective", "execution_profile", "requested_capabilities", "steps", "allowed_files", "allowed_test_commands", "acceptance_criteria", "evidence_references", "planner", "fixture_id", "fixture_initial_hash", "changes", "execution_limits", "planning_evidence"}
_COMMON_TASK_FIELDS = _TASK_FIELDS - {"fixture_id", "fixture_initial_hash", "changes", "execution_limits", "planning_evidence"}
_STEP_FIELDS = {"operation", "arguments"}
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,127}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


class LocalNativeTaskExecutor:
    """Execute registered local capabilities through a fail-closed dispatcher."""

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir) / "native-executions"
        self.root.mkdir(parents=True, exist_ok=True)
        self.workspace_root = self.root / "workspaces"
        self.workspace_root.mkdir(exist_ok=True)
        for path in (self.root, self.workspace_root):
            os.chmod(path, 0o700)

    def _event(self, task_id: str, stage: str, result: str, **extra: Any) -> None:
        value = {"task_id": task_id, "stage": stage, "result": result, "timestamp": _utc_now(), "executor": "ANNY_RUNTIME_NATIVE", **extra}
        path = self.root / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n")
        os.chmod(path, 0o600)

    def _deny(self, task_id: str, reason: str) -> None:
        self._event(task_id if _TASK_ID_RE.match(task_id) else "invalid-task", "DENIED", "BLOCKED", reason=reason)
        raise LocalNativeTaskError(reason)

    @staticmethod
    def capability_registry() -> list[dict[str, Any]]:
        return [{key: sorted(value) if isinstance(value, set) else value for key, value in item.items()} for item in CAPABILITY_REGISTRY.values()]

    def _safe_path(self, workspace: Path, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or "\\" in relative:
            raise LocalNativeTaskError("Only non-empty relative POSIX task paths are allowed")
        candidate = workspace / relative
        try:
            candidate.relative_to(workspace)
            candidate.resolve(strict=False).relative_to(workspace.resolve())
        except ValueError as exc:
            raise LocalNativeTaskError("Task path or symlink escapes the workspace") from exc
        return candidate

    def _validate_spec(self, spec: Any) -> tuple[dict[str, Any], dict[str, Any], str]:
        if not isinstance(spec, dict):
            raise LocalNativeTaskError("Task specification must be an object")
        task_id = str(spec.get("task_id", "invalid-task"))
        unknown, missing = set(spec) - _TASK_FIELDS, _COMMON_TASK_FIELDS - set(spec)
        if unknown:
            self._deny(task_id, f"Unknown task fields are not permitted: {sorted(unknown)}")
        if missing:
            self._deny(task_id, f"Missing required task fields: {sorted(missing)}")
        if not _TASK_ID_RE.match(task_id): self._deny(task_id, "task_id is invalid")
        if not all(isinstance(spec[name], str) and spec[name].strip() for name in ("request", "objective")):
            self._deny(task_id, "request and objective must be non-empty strings")
        if spec["execution_profile"] != PROFILE or spec["planner"] not in {PLANNER, "LOCAL_MODEL_INFERENCE"}:
            self._deny(task_id, "Task requests a profile or planner outside the active local contract")
        if spec["planner"] == "LOCAL_MODEL_INFERENCE":
            evidence = spec.get("planning_evidence")
            expected = {"provider_id", "model_id", "raw_output", "raw_output_hash", "validator", "decision"}
            if not isinstance(evidence, dict) or set(evidence) != expected or evidence.get("decision") != "ALLOW" or evidence.get("validator") != "LOCAL_PLAN_VALIDATOR_V1" or not all(isinstance(evidence.get(key), str) and evidence[key] for key in expected - {"decision", "validator"}):
                self._deny(task_id, "Local-model plan is missing independently validated planning evidence")
            if hashlib.sha256(evidence["raw_output"].encode()).hexdigest() != evidence["raw_output_hash"]:
                self._deny(task_id, "Local-model planning evidence hash does not match its output")
        elif "planning_evidence" in spec:
            self._deny(task_id, "Planning evidence is reserved for independently validated local-model plans")
        caps = spec["requested_capabilities"]
        if not isinstance(caps, list) or len(caps) != 1 or not isinstance(caps[0], str): self._deny(task_id, "Exactly one registered local capability must be requested")
        capability = CAPABILITY_REGISTRY.get(caps[0])
        if not capability: self._deny(task_id, "Requested capability is not registered")
        if any(word in caps[0].lower() for word in ("credential", "docker", "podman", "socket", "remote", "network")):
            self._deny(task_id, "Credential, container-socket, network, or remote capability requests are denied")
        is_repository_task = capability["id"] == "experimental.local.repository_change.v1"
        repository_fields = {"fixture_id", "fixture_initial_hash", "changes", "execution_limits"}
        if is_repository_task:
            if repository_fields - set(spec): self._deny(task_id, "Repository task is missing its fixture, patch, or execution limits")
            from runtime.execution.local_repository_fixtures import get_fixture
            fixture = get_fixture(spec["fixture_id"]) if isinstance(spec["fixture_id"], str) else None
            if not fixture or spec["fixture_initial_hash"] != fixture["initial_hash"]:
                self._deny(task_id, "Fixture is unregistered or its declared initial hash does not match")
            limits = spec["execution_limits"]
            if limits != {"timeout_seconds": 30, "memory_mb": 256, "cpus": 1, "pids": 64}:
                self._deny(task_id, "Repository task requests execution limits outside the fixed runner profile")
            changes = spec["changes"]
            if not isinstance(changes, list) or not changes or not all(isinstance(change, dict) and set(change) == {"path", "expected_sha256", "content"} and isinstance(change.get("path"), str) and isinstance(change.get("expected_sha256"), str) and isinstance(change.get("content"), str) for change in changes):
                self._deny(task_id, "Repository changes must be explicit verified content replacements")
        elif repository_fields & set(spec):
            self._deny(task_id, "Fixture and patch fields are restricted to repository-change capability")
        files = spec["allowed_files"]
        if not isinstance(files, list) or not files or len(files) != len(set(files)) or not all(isinstance(path, str) for path in files):
            self._deny(task_id, "allowed_files must be a non-empty unique list of paths")
        if any(Path(path).is_absolute() or path.startswith("../") or "/../" in path or path in {".git", ".git/config"} for path in files):
            self._deny(task_id, "Allowed file path escapes or targets a canonical repository")
        if spec["allowed_test_commands"] != ["python-unittest-q"]: self._deny(task_id, "Only python-unittest-q is allowed")
        if not isinstance(spec["acceptance_criteria"], list) or not spec["acceptance_criteria"]: self._deny(task_id, "acceptance_criteria must be a non-empty list")
        refs = spec["evidence_references"]
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref.startswith("local://") for ref in refs): self._deny(task_id, "Evidence references must be local durable references")
        steps = spec["steps"]
        if not isinstance(steps, list) or not steps: self._deny(task_id, "steps must be a non-empty list")
        for step in steps:
            if not isinstance(step, dict) or set(step) != _STEP_FIELDS or not isinstance(step.get("operation"), str) or not isinstance(step.get("arguments"), dict): self._deny(task_id, "Each step must contain only operation and arguments")
            if step["operation"] not in capability["operations"]: self._deny(task_id, "Operation is not registered for this capability")
            try:
                self._validate_step_arguments(step["operation"], step["arguments"], set(files))
            except LocalNativeTaskError as exc:
                self._deny(task_id, str(exc))
        if is_repository_task:
            if steps[0]["operation"] != "create_fixture": self._deny(task_id, "Repository task must create its private fixture before applying changes")
            if steps[0]["arguments"] != {"fixture_id": spec["fixture_id"], "initial_hash": spec["fixture_initial_hash"]}:
                self._deny(task_id, "Repository fixture step must exactly match the authorized fixture")
            patches = [step["arguments"] for step in steps if step["operation"] == "apply_patch"]
            if patches != spec["changes"]: self._deny(task_id, "Repository patch steps must exactly match the authorized changes")
        return spec, capability, _json_hash(spec)

    @staticmethod
    def _validate_step_arguments(operation: str, args: dict[str, Any], allowed: set[str]) -> None:
        """Validate arguments before a workspace is created or a runner is invoked."""
        if operation == "write_file":
            valid = set(args) == {"path", "content"} and args.get("path") in allowed and isinstance(args.get("content"), str)
        elif operation == "read_file":
            valid = set(args) == {"path"} and args.get("path") in allowed
        elif operation in {"inspect_structure", "sha256"}:
            paths = args.get("paths")
            valid = set(args) == {"paths"} and isinstance(paths, list) and bool(paths) and all(isinstance(path, str) and path in allowed for path in paths)
        elif operation == "run_tests":
            valid = set(args) == {"command"} and args.get("command") == "python-unittest-q"
        elif operation == "create_fixture":
            valid = set(args) == {"fixture_id", "initial_hash"} and isinstance(args.get("fixture_id"), str) and isinstance(args.get("initial_hash"), str)
        elif operation == "apply_patch":
            valid = set(args) == {"path", "expected_sha256", "content"} and args.get("path") in allowed and isinstance(args.get("expected_sha256"), str) and isinstance(args.get("content"), str)
        else:
            valid = False
        if not valid:
            raise LocalNativeTaskError(f"{operation} arguments are outside the authorized contract")

    def _result_path(self, task_id: str) -> Path:
        return self.root / f"{task_id}.json"

    def _index(self) -> dict[str, str]:
        path = self.root / "task-id-index.json"
        if not path.exists(): return {}
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc: raise LocalNativeTaskError("Durable task index is corrupt") from exc
        return value if isinstance(value, dict) and all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()) else {}

    def _save_index(self, index: dict[str, str]) -> None:
        path = self.root / "task-id-index.json"
        path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(path, 0o600)

    def _write_file(self, workspace: Path, allowed: set[str], args: dict[str, Any]) -> dict[str, Any]:
        if set(args) != {"path", "content"} or args.get("path") not in allowed or not isinstance(args.get("content"), str): raise LocalNativeTaskError("write_file arguments are outside the authorized contract")
        target = self._safe_path(workspace, args["path"])
        if target.exists() and target.is_symlink(): raise LocalNativeTaskError("Writing through a symlink is denied")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args["content"], encoding="utf-8")
        return {"operation": "write_file", "path": args["path"], "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    def _create_fixture(self, workspace: Path, allowed: set[str], args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        """Copy an allowlisted static fixture into a fresh, private workspace."""
        from runtime.execution.local_repository_fixtures import get_fixture, fixture_hash
        fixture = get_fixture(args.get("fixture_id"))
        if not fixture or args.get("initial_hash") != fixture["initial_hash"]:
            raise LocalNativeTaskError("Fixture identity or initial hash is invalid")
        files = fixture["files"]
        if not set(files).issubset(allowed):
            raise LocalNativeTaskError("Fixture contains files outside the authorized repository file list")
        if fixture_hash(files) != fixture["initial_hash"]:
            raise LocalNativeTaskError("Fixture initial state cannot be verified")
        for path, content in files.items():
            target = self._safe_path(workspace, path)
            if target.exists() or target.is_symlink():
                raise LocalNativeTaskError("Fixture workspace is not empty or contains a symlink")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return ({"operation": "create_fixture", "fixture_id": fixture["id"], "initial_hash": fixture["initial_hash"], "files": sorted(files), "status": "PASS"}, files)

    def _apply_patch(self, workspace: Path, allowed: set[str], args: dict[str, Any]) -> dict[str, Any]:
        """Apply a content replacement only when its expected preimage matches."""
        if set(args) != {"path", "expected_sha256", "content"} or args.get("path") not in allowed:
            raise LocalNativeTaskError("apply_patch arguments are outside the authorized contract")
        target = self._safe_path(workspace, args["path"])
        if not target.is_file() or target.is_symlink():
            raise LocalNativeTaskError("Patch target is absent or is a symlink")
        before = target.read_bytes()
        before_hash = hashlib.sha256(before).hexdigest()
        if before_hash != args["expected_sha256"]:
            raise LocalNativeTaskError("Patch target initial hash does not match the authorized preimage")
        flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags)
        except OSError as exc:
            raise LocalNativeTaskError("Patch target could not be opened without following links") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(args["content"])
        finally:
            # fdopen closes the descriptor; this branch exists only if its construction failed.
            try: os.close(descriptor)
            except OSError: pass
        after = target.read_bytes()
        return {"operation": "apply_patch", "path": args["path"], "before_sha256": before_hash, "sha256": hashlib.sha256(after).hexdigest(), "status": "PASS"}

    def _read_file(self, workspace: Path, allowed: set[str], args: dict[str, Any]) -> dict[str, Any]:
        if set(args) != {"path"} or args.get("path") not in allowed: raise LocalNativeTaskError("read_file arguments are outside the authorized contract")
        target = self._safe_path(workspace, args["path"])
        if not target.is_file() or target.is_symlink(): raise LocalNativeTaskError("Authorized file is absent or a symlink")
        return {"operation": "read_file", "path": args["path"], "size_bytes": target.stat().st_size}

    def _inspect_structure(self, workspace: Path, allowed: set[str], args: dict[str, Any]) -> dict[str, Any]:
        paths = args.get("paths")
        if set(args) != {"paths"} or not isinstance(paths, list) or not paths or not all(isinstance(path, str) and path in allowed for path in paths): raise LocalNativeTaskError("inspect_structure arguments are outside the authorized contract")
        if any(not self._safe_path(workspace, path).is_file() or self._safe_path(workspace, path).is_symlink() for path in paths): raise LocalNativeTaskError("Expected generated file is absent or a symlink")
        return {"operation": "inspect_structure", "paths": sorted(paths), "status": "PASS"}

    def _sha256(self, workspace: Path, allowed: set[str], args: dict[str, Any]) -> dict[str, Any]:
        paths = args.get("paths")
        if set(args) != {"paths"} or not isinstance(paths, list) or not paths or not all(isinstance(path, str) and path in allowed for path in paths): raise LocalNativeTaskError("sha256 arguments are outside the authorized contract")
        return {"operation": "sha256", "hashes": {path: hashlib.sha256(self._safe_path(workspace, path).read_bytes()).hexdigest() for path in sorted(paths)}}

    def _run_tests(self, workspace: Path, args: dict[str, Any], task_id: str) -> dict[str, Any]:
        if set(args) != {"command"} or args.get("command") != "python-unittest-q": raise LocalNativeTaskError("Runner command is not allowlisted")
        podman = shutil.which("podman")
        if not podman: return {"status": "BLOCKED", "command": "python-unittest-q", "reason": "PODMAN_UNAVAILABLE", "exit_code": None, "duration_ms": 0, "stdout": "", "stderr": ""}
        original_mode = stat.S_IMODE(workspace.stat().st_mode)
        os.chmod(workspace, 0o777)  # Only while the unprivileged runner has its task-local mount.
        name = "anny-native-" + hashlib.sha256(task_id.encode()).hexdigest()[:20]
        command = [podman, "run", "--rm", "--name", name, "--read-only", "--network", "none", "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "256m", "--cpus", "1", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--volume", f"{workspace.resolve()}:/workspace:rw,rbind,nosuid,nodev,noexec", "--workdir", "/workspace", "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PATH=/usr/local/bin:/usr/bin:/bin", RUNNER_IMAGE, "python", "-m", "unittest", "-q"]
        started = time.monotonic()
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=30, env={"PATH": os.environ.get("PATH", "")})
            return {"status": "PASS" if process.returncode == 0 else "FAIL", "command": "python-unittest-q", "runner_command": ["podman", "run", "<fixed-security-options>", RUNNER_IMAGE, "python", "-m", "unittest", "-q"], "exit_code": process.returncode, "stdout": process.stdout[-4000:], "stderr": process.stderr[-4000:], "duration_ms": round((time.monotonic() - started) * 1000)}
        except subprocess.TimeoutExpired as exc:
            return {"status": "FAIL", "command": "python-unittest-q", "exit_code": None, "stdout": (exc.stdout or "")[-4000:], "stderr": (exc.stderr or "")[-4000:], "duration_ms": round((time.monotonic() - started) * 1000), "reason": "RUNNER_TIMEOUT"}
        finally:
            os.chmod(workspace, original_mode)

    def execute(self, task_spec: dict[str, Any]) -> dict[str, Any]:
        spec, capability, spec_hash = self._validate_spec(task_spec)
        task_id, index = spec["task_id"], self._index()
        if task_id in index:
            if index[task_id] != spec_hash: self._deny(task_id, "task_id has already been used with a different request")
            path = self._result_path(task_id)
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                # Backfill the complete plan for evidence written by the earlier
                # one-task fixture without rerunning code or changing its task id.
                if "task_specification" not in existing:
                    existing["task_specification"] = spec
                    existing["authorization_decision"] = "ALLOW_LOCAL_DEVELOPMENT_ONLY"
                    existing["evidence_migrated_at"] = _utc_now()
                    path.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")
                    os.chmod(path, 0o600)
                return existing
            self._deny(task_id, "task_id index has no durable result")
        started_at = _utc_now()
        self._event(task_id, "RECEIVED", "PASS", request=spec["request"], specification_hash=spec_hash)
        self._event(task_id, "VALIDATED", "PASS", capability_id=capability["id"], specification_hash=spec_hash)
        self._event(task_id, "AUTHORIZED", "PASS", decision="ALLOW_LOCAL_DEVELOPMENT_ONLY", profile=PROFILE, capability_id=capability["id"])
        workspace = self.workspace_root / task_id
        workspace.mkdir(parents=True, exist_ok=False); os.chmod(workspace, 0o700)
        self._event(task_id, "WORKSPACE_CREATED", "PASS", workspace=str(workspace))
        allowed, operations, test, initial_files = set(spec["allowed_files"]), [], None, None
        try:
            for step in spec["steps"]:
                operation, args = step["operation"], step["arguments"]
                if operation == "write_file": item = self._write_file(workspace, allowed, args)
                elif operation == "create_fixture":
                    item, initial_files = self._create_fixture(workspace, allowed, args)
                elif operation == "apply_patch": item = self._apply_patch(workspace, allowed, args)
                elif operation == "read_file": item = self._read_file(workspace, allowed, args)
                elif operation == "inspect_structure": item = self._inspect_structure(workspace, allowed, args)
                elif operation == "sha256": item = self._sha256(workspace, allowed, args)
                elif operation == "run_tests":
                    test = self._run_tests(workspace, args, task_id); item = {"operation": operation, "status": test["status"], "exit_code": test["exit_code"]}
                    self._event(task_id, "TESTED", test["status"], test_result=test)
                else: raise LocalNativeTaskError("Operation is not registered")
                operations.append(item); self._event(task_id, operation.upper(), item.get("status", "PASS"), operation_result=item)
        except LocalNativeTaskError as exc:
            self._event(task_id, "DENIED", "BLOCKED", reason=str(exc)); raise
        if not test: self._deny(task_id, "Task completed without its required test result")
        if capability["id"] == "experimental.local.repository_change.v1" and initial_files is None:
            self._deny(task_id, "Repository task completed without creating its fixture")
        status = test["status"]
        if status == "PASS" and any(not self._safe_path(workspace, path).is_file() for path in allowed): status = "PARTIAL"
        diff = []
        for path in sorted(allowed):
            target = self._safe_path(workspace, path)
            if not target.is_file(): continue
            current = target.read_text(encoding="utf-8")
            before = initial_files.get(path) if initial_files else None
            change = "MODIFIED" if initial_files and path in initial_files else "CREATED"
            item = {"path": path, "change": change, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "size_bytes": target.stat().st_size}
            if initial_files and before != current:
                item["unified_diff"] = "".join(difflib.unified_diff(before.splitlines(keepends=True), current.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}"))
            diff.append(item)
        if initial_files is not None and any(not item.get("unified_diff") for item in diff):
            status = "PARTIAL" if status == "PASS" else status
        repository_evidence = ({"fixture_id": spec["fixture_id"], "fixture_initial_hash": spec["fixture_initial_hash"], "fixture_provenance": "LOCAL_STATIC_TEST_FIXTURE"} if initial_files is not None else {})
        result = {"task_id": task_id, "request": spec["request"], "objective": spec["objective"], "task_specification": spec, "status": status, "execution_kind": "ANNY_RUNTIME_NATIVE", "capability_id": capability["id"], "capability_status": capability["implementation_status"], "profile": PROFILE, "authorization": "ALLOW_LOCAL_DEVELOPMENT_ONLY", "authorization_decision": "ALLOW_LOCAL_DEVELOPMENT_ONLY", "planner": spec["planner"], "model_provenance": "LOCAL_MODEL_INFERENCE" if spec["planner"] == "LOCAL_MODEL_INFERENCE" else "NO_MODEL_AVAILABLE_OR_USED", "planning_evidence": spec.get("planning_evidence"), "executor_process": "ANNY_RUNTIME_NATIVE", "runner_identity": RUNNER_IDENTITY, "runner_isolation": {"container": "PODMAN_ROOTLESS_DEDICATED", "root_filesystem": "READ_ONLY", "network": "DISABLED", "user": "65534:65534", "capabilities": "ALL_DROPPED", "docker_or_podman_socket": "NOT_MOUNTED", "data_directory": "NOT_MOUNTED", "resource_limits": {"memory": "256m", "cpus": 1, "pids": 64, "timeout_seconds": 30}}, "workspace": str(workspace), "allowed_files": sorted(allowed), "operations": operations, "test": test, "diff": diff, "file_hashes": {item["path"]: item["sha256"] for item in diff}, "specification_hash": spec_hash, "result_hash": _json_hash({"status": status, "operations": operations, "diff": diff, "test": test}), "evidence_ref": f"local://native-executions/{task_id}.json", "evidence_references": spec["evidence_references"], "started_at": started_at, "completed_at": _utc_now(), **repository_evidence}
        path = self._result_path(task_id); path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"); os.chmod(path, 0o600)
        index[task_id] = spec_hash; self._save_index(index)
        self._event(task_id, "VERIFIED", status, result_hash=result["result_hash"], evidence_ref=result["evidence_ref"])
        return result

    def list_results(self) -> list[dict[str, Any]]:
        values = []
        for path in self.root.glob("*.json"):
            if path.name == "task-id-index.json": continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and "task_id" in value: values.append(value)
            except json.JSONDecodeError: continue
        return sorted(values, key=lambda value: str(value.get("completed_at", "")))

    def latest(self) -> dict[str, Any] | None:
        values = self.list_results()
        return values[-1] if values else None

    def execute_safe_slug_demo(self, request: str) -> dict[str, Any]:
        """Compatibility fixture; it uses the generic dispatcher."""
        from runtime.execution.local_task_specs import safe_slug_task_spec
        return self.execute(safe_slug_task_spec(request=request))
