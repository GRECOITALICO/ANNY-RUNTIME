import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runtime.execution.inbox_capabilities import InboxCapabilityError, list_text_files, read_text_file
from runtime.execution.deterministic_executor import DeterministicExecutor
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


def test_read_contract_limits_and_simple_relative_name():
    valid = parse_inbox_request(_issue(_payload("filesystem.read_text", {"relative_path": "one.txt"}, {"max_bytes": 16384})), "anny-l0")
    assert valid.capability == "filesystem.read_text"
    for path in ("../one.txt", "/tmp/one.txt", "nested/one.txt", "one.md"):
        with pytest.raises(InboxContractError):
            parse_inbox_request(_issue(_payload("filesystem.read_text", {"relative_path": path}, {"max_bytes": 16})), "anny-l0")


def test_downloads_text_capabilities_reject_symlink_invalid_utf8_and_large_file(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    (root / "three.txt").write_text("3\n", encoding="utf-8")
    (root / "other.md").write_text("not listed", encoding="utf-8")
    os.symlink(root / "three.txt", root / "link.txt")
    (root / "broken.txt").write_bytes(b"\xff")
    (root / "large.txt").write_text("x" * 17, encoding="utf-8")

    assert list_text_files(str(root))["files"] == [
        {"name": "broken.txt", "size_bytes": 1},
        {"name": "large.txt", "size_bytes": 17},
        {"name": "three.txt", "size_bytes": 2},
    ]
    assert read_text_file(str(root), "three.txt", 16) == {
        "relative_path": "three.txt", "content": "3\n", "encoding": "utf-8", "bytes": 2,
        "sha256": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    }
    for name, limit, code in (("link.txt", 16, "TEXT_FILE_OPEN_DENIED"), ("broken.txt", 16, "TEXT_FILE_NOT_UTF8"), ("large.txt", 16, "TEXT_FILE_TOO_LARGE"), ("missing.txt", 16, "TEXT_FILE_NOT_FOUND"), ("../three.txt", 16, "INVALID_RELATIVE_TEXT_NAME")):
        with pytest.raises(InboxCapabilityError, match=code):
            read_text_file(str(root), name, limit)


def test_deterministic_executor_uses_the_registered_bounded_text_capability(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    (root / "value.txt").write_text("3\n", encoding="utf-8")
    manager = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    workspace = manager.create_workspace("inbox-exec", "inbox")
    task = Task(
        task_id="inbox-read", capability_id="filesystem.read_text", account_id="inbox", project_id="inbox",
        input={"relative_path": "value.txt"}, constraints={"max_bytes": 16},
        deadline=datetime.now(timezone.utc) + timedelta(seconds=20), workspace_policy="retain",
        evidence_policy="required", requested_by="anny-l0", created_at=datetime.now(timezone.utc),
    )
    context = TaskExecutionContext(
        execution_id="inbox-exec", task_id=task.task_id, account_id="inbox", project_id="inbox",
        capability_id=task.capability_id, workspace_path=workspace, environment={}, allowed_tools=[task.capability_id],
        deadline=task.deadline, resource_limits={"max_output_size": 1024 * 1024, "max_workspace_size": 1024 * 1024},
        network_policy="disabled", write_policy="read_only",
    )
    DeterministicExecutor(manager, inbox_downloads_root=str(root)).execute(task, context)
    assert context.status == ExecutionStatus.SUCCEEDED
    assert context.result["content"] == "3\n"
    assert context.result_hash


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
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0"), inbox, manager, tmp_path, "rt-test")

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
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0"), inbox, manager, tmp_path, "rt-test")
    assert worker.start() is False
    assert worker.status()["activation"] == "TOKEN_SCOPE_EXCESS"
    assert not manager.calls


def test_worker_fails_closed_when_token_or_authorized_identity_is_unavailable(tmp_path):
    class MissingTokenInbox:
        def verify_activation(self):
            raise RuntimeError("credential unavailable")
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0"), MissingTokenInbox(), _FakeExecutionManager(), tmp_path, "rt-test")
    assert worker.start() is False
    assert worker.status()["activation"] == "TOKEN_AUTH_FAILED"

    wrong = _FakeInbox([], scopes=["repo", "read:org"])
    wrong.verify_activation = lambda: {"principal": "different-user", "missing_scopes": [], "excess_scopes": [], "private": True}
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="anny-l0"), wrong, _FakeExecutionManager(), tmp_path, "rt-test")
    assert worker.start() is False
    assert worker.status()["activation"] == "AUTHENTICATED_PRINCIPAL_NOT_AUTHORIZED"


def test_worker_allows_explicit_self_actor_only_after_token_identity_verification(tmp_path):
    inbox = _FakeInbox([])
    worker = GitHubInboxWorker(InboxSettings(enabled=True, authorized_actor="self"), inbox, _FakeExecutionManager(), tmp_path, "rt-test")
    assert worker.start() is True
    worker.stop()
