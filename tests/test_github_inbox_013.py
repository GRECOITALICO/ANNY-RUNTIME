import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runtime.execution.inbox_capabilities import build_local_access_policy, hash_local_file, inspect_local_file, list_local_directory, read_local_text
from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.execution.capability import CapabilityRegistry
from runtime.execution.models import ExecutionStatus, Task, TaskExecutionContext
from runtime.github.inbox import GitHubInboxClient, GitHubInboxWorker, InboxContractError, InboxSettings, parse_inbox_request
from runtime.workspace.ephemeral import EphemeralWorkspaceManager


def _issue(body, actor="anny-l0", number=7, title="[ANNY TASK v1] bounded read"):
    return {"number": number, "title": title, "body": json.dumps(body), "user": {"login": actor}}


def _payload(capability="runtime.ping", input_data=None, constraints=None):
    return {
        "schema_version": "anny.github-task.v1",
        "request_id": "ANNY-READ-013",
        "capability": capability,
        "input": {} if input_data is None else input_data,
        "constraints": {} if constraints is None else constraints,
    }


@pytest.mark.parametrize("mutate", [
    lambda value: value.update({"extra": True}),
    lambda value: value.update({"request_id": "x"}),
    lambda value: value.update({"capability": "shell.execute"}),
])
def test_request_contract_rejects_unknown_invalid_or_unauthorized(mutate):
    payload = _payload()
    mutate(payload)
    with pytest.raises(InboxContractError):
        parse_inbox_request(_issue(payload), "anny-l0")


def test_request_contract_rejects_wrong_actor_and_pr():
    with pytest.raises(InboxContractError, match="ACTOR_NOT_AUTHORIZED"):
        parse_inbox_request(_issue(_payload(), actor="other"), "anny-l0")
    issue = _issue(_payload())
    issue["pull_request"] = {"url": "not-used"}
    with pytest.raises(InboxContractError, match="NOT_ISSUE"):
        parse_inbox_request(issue, "anny-l0")


def test_local_contract_accepts_only_registered_operations_and_relative_paths():
    valid = parse_inbox_request(_issue(_payload("filesystem.local.read_text", {"root_id": "workspace", "relative_path": "nested/one.txt"}, {"max_bytes": 16384})), "anny-l0")
    assert valid.capability == "filesystem.local.read_text"
    for capability, input_data, constraints in (
        ("shell.execute", {}, {}),
        ("filesystem.local.read_text", {"root_id": "workspace", "relative_path": "../one.txt"}, {"max_bytes": 16}),
        ("filesystem.local.list", {"root_id": "workspace", "relative_path": "/tmp"}, {"max_entries": 1}),
        ("filesystem.local.hash", {"root_id": "workspace", "relative_path": "one.txt"}, {"max_bytes": 4 * 1024 * 1024 + 1}),
    ):
        with pytest.raises(InboxContractError):
            parse_inbox_request(_issue(_payload(capability, input_data, constraints)), "anny-l0")


def _policy(root, operations=("read", "list", "inspect", "hash")):
    return build_local_access_policy({"fixture": {"path": str(root), "operations": list(operations)}})


def test_local_policy_separates_operations_and_rejects_escape_sensitive_and_symlink_paths(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested" / "three.txt").write_text("3\n", encoding="utf-8")
    (root / ".ssh").mkdir()
    (root / ".ssh" / "id_rsa").write_text("never publish", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    os.symlink(outside, root / "link.txt")
    policy = _policy(root)

    assert list_local_directory(policy, "fixture", ".", 10)["entries"] == [{"name": "nested", "kind": "directory", "size_bytes": pytest.approx((root / "nested").stat().st_size)}]
    assert read_local_text(policy, "fixture", "nested/three.txt", 16)["content"] == "3\n"
    assert inspect_local_file(policy, "fixture", "nested/three.txt")["kind"] == "file"
    assert hash_local_file(policy, "fixture", "nested/three.txt", 16)["bytes"] == 2
    for path in ("../outside.txt", ".ssh/id_rsa", "link.txt"):
        with pytest.raises(Exception):
            read_local_text(policy, "fixture", path, 16)
    with pytest.raises(Exception, match="LOCAL_OPERATION_NOT_AUTHORIZED"):
        read_local_text(_policy(root, ("list",)), "fixture", "nested/three.txt", 16)


def test_local_policy_mutations_require_separate_explicit_grants_and_stay_inside_fixture(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    policy = _policy(root, ("create", "write", "move", "delete"))

    assert policy.create_text("fixture", "created.txt", "first")["bytes"] == 5
    assert policy.write_text("fixture", "created.txt", "edited")["bytes"] == 6
    assert policy.move_file("fixture", "created.txt", "moved.txt")["moved"] is True
    assert policy.delete_file("fixture", "moved.txt")["deleted"] is True
    assert not (root / "moved.txt").exists()
    with pytest.raises(Exception, match="LOCAL_OPERATION_NOT_AUTHORIZED"):
        _policy(root, ("read",)).create_text("fixture", "not-allowed.txt", "no")


def test_deterministic_executor_uses_registered_local_policy_and_blocks_ungranted_root(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "value.txt").write_text("3\n", encoding="utf-8")
    manager = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    workspace = manager.create_workspace("inbox-exec", "inbox")
    task = Task(
        task_id="inbox-read", capability_id="filesystem.local.read_text", account_id="inbox", project_id="inbox",
        input={"root_id": "fixture", "relative_path": "value.txt"}, constraints={"max_bytes": 16},
        deadline=datetime.now(timezone.utc) + timedelta(seconds=20), workspace_policy="retain",
        evidence_policy="required", requested_by="anny-l0", created_at=datetime.now(timezone.utc),
    )
    context = TaskExecutionContext(
        execution_id="inbox-exec", task_id=task.task_id, account_id="inbox", project_id="inbox",
        capability_id=task.capability_id, workspace_path=workspace, environment={}, allowed_tools=[task.capability_id],
        deadline=task.deadline, resource_limits={"max_output_size": 1024 * 1024, "max_workspace_size": 1024 * 1024},
        network_policy="disabled", write_policy="read_only",
    )
    DeterministicExecutor(manager, inbox_local_roots={"fixture": {"path": str(root), "operations": ["read"]}}).execute(task, context)
    assert context.status == ExecutionStatus.SUCCEEDED
    assert context.result["content"] == "3\n"
    assert context.result_hash


def test_registry_exposes_only_read_only_local_inbox_capabilities():
    registry = CapabilityRegistry()
    for capability_id in ("filesystem.local.list", "filesystem.local.read_text", "filesystem.local.inspect", "filesystem.local.hash"):
        capability = registry.get(capability_id)
        assert capability is not None
        assert capability.side_effect == "read"
        assert capability.deterministic_allowed is True
    assert registry.get("filesystem.local.delete") is None
    assert registry.get("shell.execute") is None


class _Response:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_inbox_client_scopes_privacy_pagination_and_fixed_write_target():
    seen = []
    def opener(request, timeout):
        seen.append((request.get_method(), request.full_url, request.data))
        if request.full_url.endswith("/user"):
            return _Response({"login": "anny-l0"}, {"X-OAuth-Scopes": "repo, read:org"})
        if request.full_url.endswith("/ANNY-RUNTIME-CANARY-INBOX"):
            return _Response({"private": True})
        if "issues?state=open" in request.full_url and "page=1" in request.full_url:
            return _Response([{"number": 1}], {"Link": '<next>; rel="next"'})
        if "issues?state=open" in request.full_url and "page=2" in request.full_url:
            return _Response([])
        if request.get_method() == "POST":
            return _Response({"id": 1})
        if request.get_method() == "PATCH":
            return _Response({"state": "closed"})
        return _Response([])

    class Secrets:
        def retrieve(self, reference):
            assert reference == "github-access-token"
            return b"not-printed"

    client = GitHubInboxClient(Secrets(), opener=opener)
    activation = client.verify_activation()
    assert activation["missing_scopes"] == [] and activation["excess_scopes"] == []
    assert list(client.list_open_issues()) == [{"number": 1}]
    client.post_comment(8, "{}")
    client.close_issue(8)
    assert all("GRECOITALICO/ANNY-RUNTIME-CANARY-INBOX" in url for _, url, _ in seen if "/repos/" in url)
    assert any(method == "POST" and url.endswith("/issues/8/comments") for method, url, _ in seen)
    assert any(method == "PATCH" and url.endswith("/issues/8") for method, url, _ in seen)


class _FakeInbox:
    def __init__(self, issues, scopes=None):
        self.issues, self.comments_by_issue, self.closed = list(issues), {}, []
        self.scopes = scopes if scopes is not None else ["repo", "read:org"]

    def verify_activation(self):
        return {"principal": "anny-l0", "scopes": self.scopes, "missing_scopes": sorted({"repo", "read:org"} - set(self.scopes)), "excess_scopes": sorted(set(self.scopes) - {"repo", "read:org"}), "private": True}

    def list_open_issues(self):
        return list(self.issues)

    def comments(self, number):
        return list(self.comments_by_issue.get(number, []))

    def post_comment(self, number, body):
        self.comments_by_issue.setdefault(number, []).append({"body": body})
        return {"id": len(self.comments_by_issue[number])}

    def close_issue(self, number):
        self.closed.append(number)


class _FakeExecutionManager:
    def __init__(self):
        self.calls, self.contexts = [], {}

    def submit_task(self, task):
        self.calls.append(task)
        context = TaskExecutionContext(
            execution_id="exec-013", task_id=task.task_id, account_id=task.account_id, project_id=task.project_id,
            capability_id=task.capability_id, workspace_path="", environment={}, allowed_tools=[],
            deadline=task.deadline, resource_limits={}, network_policy="disabled", write_policy="read_only",
        )
        self.contexts[context.execution_id] = context
        return context

    def execute_sync(self, execution_id):
        context = self.contexts[execution_id]
        context.status = ExecutionStatus.SUCCEEDED
        context.result = {"pong": True}
        context.result_hash = "a" * 64
        context.started_at = context.completed_at = datetime.now(timezone.utc)


def test_worker_acknowledges_executes_publishes_verifies_and_is_idempotent(tmp_path):
    inbox = _FakeInbox([_issue(_payload())])
    manager = _FakeExecutionManager()
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0", local_roots={"fixture": {"path": str(tmp_path), "operations": ["read"]}}), inbox, manager, tmp_path, "rt-test")

    assert worker.start() is True
    worker.stop()
    worker.poll_once()
    comments = [json.loads(item["body"]) for item in inbox.comments(7)]
    assert [item["schema_version"] for item in comments] == ["anny.task-ack.v1", "anny.task-result.v1"]
    assert comments[-1]["github_issue_number"] == 7
    assert inbox.closed == [7]
    assert len(manager.calls) == 1
    worker.poll_once()
    assert len(manager.calls) == 1


def test_worker_fails_closed_for_excess_token_scope_and_never_executes(tmp_path):
    inbox = _FakeInbox([_issue(_payload())], scopes=["repo", "read:org", "workflow"])
    manager = _FakeExecutionManager()
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0", local_roots={"fixture": {"path": str(tmp_path), "operations": ["read"]}}), inbox, manager, tmp_path, "rt-test")
    assert worker.start() is False
    assert worker.status()["activation"] == "TOKEN_SCOPE_EXCESS"
    assert not manager.calls


def test_worker_fails_closed_when_token_or_authorized_identity_is_unavailable(tmp_path):
    class MissingTokenInbox:
        def verify_activation(self):
            raise RuntimeError("credential unavailable")
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0", local_roots={"fixture": {"path": str(tmp_path), "operations": ["read"]}}), MissingTokenInbox(), _FakeExecutionManager(), tmp_path, "rt-test")
    assert worker.start() is False
    assert worker.status()["activation"] == "TOKEN_AUTH_FAILED"

    wrong = _FakeInbox([], scopes=["repo", "read:org"])
    wrong.verify_activation = lambda: {"principal": "different-user", "missing_scopes": [], "excess_scopes": [], "private": True}
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0", local_roots={"fixture": {"path": str(tmp_path), "operations": ["read"]}}), wrong, _FakeExecutionManager(), tmp_path, "rt-test")
    assert worker.start() is False
    assert worker.status()["activation"] == "AUTHENTICATED_PRINCIPAL_NOT_AUTHORIZED"


def test_worker_allows_explicit_self_actor_only_after_token_identity_verification(tmp_path):
    inbox = _FakeInbox([])
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="self", local_roots={"fixture": {"path": str(tmp_path), "operations": ["read"]}}), inbox, _FakeExecutionManager(), tmp_path, "rt-test")
    assert worker.start() is True
    worker.stop()


def test_worker_requires_explicit_local_root_configuration_before_activation(tmp_path):
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0"), _FakeInbox([]), _FakeExecutionManager(), tmp_path, "rt-test")
    assert worker.start() is False
    assert worker.status()["activation"] == "LOCAL_ROOTS_MISSING"

    invalid = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0", local_roots={"broken": {}}), _FakeInbox([]), _FakeExecutionManager(), tmp_path, "rt-test")
    assert invalid.start() is False
    assert invalid.status()["activation"] == "LOCAL_ROOTS_INVALID"


def test_worker_publishes_blocked_for_a_policy_denial(tmp_path):
    class PolicyDeniedManager(_FakeExecutionManager):
        def execute_sync(self, execution_id):
            context = self.contexts[execution_id]
            context.status = ExecutionStatus.FAILED
            from runtime.execution.models import FailureReason
            context.failure_reason = FailureReason.AUTHORIZATION_DENIED
            context.result_hash = "b" * 64
            context.started_at = context.completed_at = datetime.now(timezone.utc)

    inbox = _FakeInbox([_issue(_payload("filesystem.local.read_text", {"root_id": "fixture", "relative_path": "one.txt"}, {"max_bytes": 16}))])
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0", local_roots={"fixture": {"path": str(tmp_path), "operations": ["read"]}}), inbox, PolicyDeniedManager(), tmp_path, "rt-test")
    assert worker.start() is True
    worker.stop()
    worker.poll_once()
    result = json.loads(inbox.comments(7)[-1]["body"])
    assert result["status"] == "BLOCKED"
    assert result["error"]["code"] == "AUTHORIZATION_DENIED"
