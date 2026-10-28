"""Strict GitHub-Issues inbox for the local ANNY Runtime.

This is the only writing client in the Runtime.  Its URLs are constructed from
the fixed CANARY inbox allowlist and integer issue numbers; it cannot write to
arbitrary repositories, branches, workflows, or issue-like URLs.
"""
from __future__ import annotations

import json
import os
import re
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from runtime.core.version import __commit__, __version__
from runtime.execution.models import ExecutionStatus, Task
from runtime.github.client import GITHUB_API_BASE, GITHUB_TOKEN_REF, GitHubAuthError


INBOX_OWNER = "GRECOITALICO"
INBOX_REPOSITORY = "ANNY-RUNTIME-CANARY-INBOX"
TITLE_PREFIX = "[ANNY TASK v1]"
REQUEST_SCHEMA = "anny.github-task.v1"
ACK_SCHEMA = "anny.task-ack.v1"
RESULT_SCHEMA = "anny.task-result.v1"
REQUIRED_SCOPES = frozenset({"repo", "read:org"})
MAX_REQUEST_BYTES = 32 * 1024
MAX_PAGES = 20
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")


class InboxError(RuntimeError):
    code = "INBOX_ERROR"

    def __init__(self, code: str | None = None):
        super().__init__(code or self.code)
        if code:
            self.code = code


class InboxTransportError(InboxError):
    pass


class InboxContractError(InboxError):
    code = "INVALID_REQUEST"


@dataclass(frozen=True)
class InboxSettings:
    enabled: bool = False
    authorized_actor: str = ""
    downloads_root: str = ""
    poll_interval_seconds: int = 25

    @classmethod
    def from_config(cls, config: Any) -> "InboxSettings":
        return cls(
            enabled=bool(getattr(config, "github_inbox_enabled", False)),
            authorized_actor=str(getattr(config, "github_inbox_authorized_actor", "") or "").strip(),
            downloads_root=str(getattr(config, "github_inbox_downloads_root", "") or "").strip(),
            poll_interval_seconds=max(20, min(30, int(getattr(config, "github_inbox_poll_interval_seconds", 25)))),
        )


@dataclass(frozen=True)
class InboxRequest:
    request_id: str
    capability: str
    input: Dict[str, Any]
    constraints: Dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_error(exc: Exception) -> str:
    if isinstance(exc, InboxError):
        return exc.code
    name = type(exc).__name__.upper()
    return name if name.isidentifier() else "INBOX_INTERNAL_ERROR"


def parse_inbox_request(issue: Dict[str, Any], authorized_actor: str) -> InboxRequest:
    """Validate one issue without granting it any authority."""
    if not isinstance(issue, dict) or "pull_request" in issue:
        raise InboxContractError("NOT_ISSUE")
    if not isinstance(issue.get("title"), str) or not issue["title"].startswith(TITLE_PREFIX):
        raise InboxContractError("TITLE_NOT_ACCEPTED")
    actor = issue.get("user", {}).get("login") if isinstance(issue.get("user"), dict) else None
    if not authorized_actor or actor != authorized_actor:
        raise InboxContractError("ACTOR_NOT_AUTHORIZED")
    body = issue.get("body")
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise InboxContractError("REQUEST_BODY_INVALID")
    try:
        payload = json.loads(body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise InboxContractError("REQUEST_JSON_INVALID") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "request_id", "capability", "input", "constraints"}:
        raise InboxContractError("REQUEST_FIELDS_INVALID")
    if payload.get("schema_version") != REQUEST_SCHEMA:
        raise InboxContractError("REQUEST_SCHEMA_UNSUPPORTED")
    request_id = payload.get("request_id")
    capability = payload.get("capability")
    input_data = payload.get("input")
    constraints = payload.get("constraints")
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise InboxContractError("REQUEST_ID_INVALID")
    if not isinstance(capability, str) or not isinstance(input_data, dict) or not isinstance(constraints, dict):
        raise InboxContractError("REQUEST_TYPES_INVALID")
    if capability == "runtime.ping":
        if input_data or constraints:
            raise InboxContractError("PING_CONTRACT_INVALID")
    elif capability == "filesystem.list_text_files":
        if input_data or constraints:
            raise InboxContractError("LIST_CONTRACT_INVALID")
    elif capability == "filesystem.read_text":
        if set(input_data) != {"relative_path"} or set(constraints) != {"max_bytes"}:
            raise InboxContractError("READ_CONTRACT_INVALID")
        relative_path = input_data.get("relative_path")
        max_bytes = constraints.get("max_bytes")
        if not isinstance(relative_path, str) or not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= 16384:
            raise InboxContractError("READ_CONTRACT_INVALID")
        from runtime.execution.inbox_capabilities import InboxCapabilityError, validate_relative_text_name
        try:
            validate_relative_text_name(relative_path)
        except InboxCapabilityError as exc:
            raise InboxContractError("READ_CONTRACT_INVALID") from exc
    else:
        raise InboxContractError("CAPABILITY_NOT_AUTHORIZED")
    return InboxRequest(request_id=request_id, capability=capability, input=input_data, constraints=constraints)


class InboxStateStore:
    """Atomically persisted per-issue recovery state; never stores credentials."""
    def __init__(self, data_dir: Path):
        self.path = data_dir / "github-inbox" / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _read(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, issue_number: int) -> Dict[str, Any]:
        with self._lock:
            return dict(self._read().get(str(issue_number), {}))

    def put(self, issue_number: int, state: Dict[str, Any]) -> None:
        with self._lock:
            all_state = self._read()
            all_state[str(issue_number)] = state
            descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", text=True)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(all_state, handle, sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.path)
                os.chmod(self.path, 0o600)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)


class GitHubInboxClient:
    """Narrow client: only the designated private inbox may be written."""
    def __init__(self, secret_backend: Any, timeout_seconds: int = 10, opener: Callable[..., Any] = urllib.request.urlopen):
        self.secret_backend = secret_backend
        self.timeout_seconds = timeout_seconds
        self._opener = opener

    def _token(self) -> str:
        value = self.secret_backend.retrieve(GITHUB_TOKEN_REF) if self.secret_backend else None
        if not value:
            raise GitHubAuthError("GitHub access token is unavailable")
        return value.decode("utf-8").strip()

    def _request(self, method: str, suffix: str, body: Optional[Dict[str, Any]] = None) -> tuple[Any, Dict[str, str]]:
        if not suffix.startswith("/") or ".." in suffix:
            raise InboxTransportError("INBOX_PATH_REJECTED")
        data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{GITHUB_API_BASE}{suffix}", data=data, method=method,
            headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/vnd.github+json", "User-Agent": "ANNY-Runtime-Inbox/1"},
        )
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return (json.loads(raw) if raw else {}), {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise GitHubAuthError("GITHUB_AUTH_FAILED") from exc
            if exc.code == 403:
                raise InboxTransportError("GITHUB_RATE_LIMIT_OR_FORBIDDEN") from exc
            raise InboxTransportError(f"GITHUB_HTTP_{exc.code}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise InboxTransportError("GITHUB_CONNECTION_FAILED") from exc
        except json.JSONDecodeError as exc:
            raise InboxTransportError("GITHUB_RESPONSE_INVALID") from exc

    @property
    def _repository_path(self) -> str:
        return f"/repos/{INBOX_OWNER}/{INBOX_REPOSITORY}"

    def verify_activation(self) -> Dict[str, Any]:
        principal, headers = self._request("GET", "/user")
        scopes = {scope.strip() for scope in headers.get("x-oauth-scopes", "").split(",") if scope.strip()}
        missing = sorted(REQUIRED_SCOPES - scopes)
        excess = sorted(scopes - REQUIRED_SCOPES)
        repository, _ = self._request("GET", self._repository_path)
        if not isinstance(repository, dict) or repository.get("private") is not True:
            raise InboxTransportError("INBOX_NOT_PRIVATE")
        return {"principal": principal.get("login") if isinstance(principal, dict) else None, "scopes": sorted(scopes), "missing_scopes": missing, "excess_scopes": excess, "private": True}

    def list_open_issues(self) -> Iterable[Dict[str, Any]]:
        page = 1
        while page <= MAX_PAGES:
            issues, headers = self._request("GET", f"{self._repository_path}/issues?state=open&per_page=100&page={page}")
            if not isinstance(issues, list):
                raise InboxTransportError("ISSUE_LIST_INVALID")
            for issue in issues:
                if isinstance(issue, dict) and "pull_request" not in issue:
                    yield issue
            if len(issues) < 100 or 'rel="next"' not in headers.get("link", ""):
                return
            page += 1
        raise InboxTransportError("ISSUE_PAGINATION_LIMIT")

    @staticmethod
    def _issue_number(number: Any) -> int:
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise InboxTransportError("ISSUE_NUMBER_INVALID")
        return number

    def comments(self, number: Any) -> list[Dict[str, Any]]:
        issue = self._issue_number(number)
        response, _ = self._request("GET", f"{self._repository_path}/issues/{issue}/comments?per_page=100")
        return response if isinstance(response, list) else []

    def post_comment(self, number: Any, body: str) -> Dict[str, Any]:
        issue = self._issue_number(number)
        response, _ = self._request("POST", f"{self._repository_path}/issues/{issue}/comments", {"body": body})
        return response if isinstance(response, dict) else {}

    def close_issue(self, number: Any) -> None:
        issue = self._issue_number(number)
        self._request("PATCH", f"{self._repository_path}/issues/{issue}", {"state": "closed"})


class GitHubInboxWorker:
    """Single-threaded, fail-closed inbox poller owned by the Runtime process."""
    def __init__(self, settings: InboxSettings, inbox: GitHubInboxClient, execution_manager: Any, data_dir: Path, runtime_id: str, status_provider: Optional[Callable[[], Dict[str, Any]]] = None):
        self.settings, self.inbox, self.execution_manager = settings, inbox, execution_manager
        self.runtime_id, self.status_provider = runtime_id, status_provider
        self._authorized_actor = settings.authorized_actor
        self.state_store = InboxStateStore(data_dir)
        self._lock, self._stop = threading.Lock(), threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status: Dict[str, Any] = {"active": False, "last_poll": None, "last_successful_poll": None, "last_error_code": None, "consecutive_failures": 0, "authenticated_principal": None, "last_result": None, "activation": "DISABLED" if not settings.enabled else "PENDING"}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def _set(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if not self.settings.enabled:
            self._set(active=False, activation="DISABLED")
            return False
        try:
            check = self.inbox.verify_activation()
        except Exception as exc:
            self._set(active=False, activation="TOKEN_AUTH_FAILED", last_error_code=_normalized_error(exc))
            return False
        if check["missing_scopes"]:
            self._set(active=False, activation="TOKEN_SCOPE_INSUFFICIENT", authenticated_principal=check["principal"])
            return False
        if check["excess_scopes"]:
            self._set(active=False, activation="TOKEN_SCOPE_EXCESS", authenticated_principal=check["principal"])
            return False
        if not self.settings.authorized_actor:
            self._set(active=False, activation="AUTHORIZED_ACTOR_MISSING", authenticated_principal=check["principal"])
            return False
        if self.settings.authorized_actor == "self":
            self._authorized_actor = check["principal"] or ""
        if not self._authorized_actor or check["principal"] != self._authorized_actor:
            self._set(active=False, activation="AUTHENTICATED_PRINCIPAL_NOT_AUTHORIZED", authenticated_principal=check["principal"])
            return False
        self._stop.clear()
        self._set(active=True, activation="ACTIVE", authenticated_principal=check["principal"], last_error_code=None)
        self._thread = threading.Thread(target=self._run, name="github-inbox-worker", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._set(active=False)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            failures = int(self.status().get("consecutive_failures", 0))
            delay = min(300, self.settings.poll_interval_seconds * (2 ** min(failures, 4)))
            self._stop.wait(delay)

    @staticmethod
    def _find_comment(comments: Iterable[Dict[str, Any]], schema: str, request_id: str) -> bool:
        for comment in comments:
            try:
                payload = json.loads(comment.get("body", ""))
            except (AttributeError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("schema_version") == schema and payload.get("request_id") == request_id:
                return True
        return False

    def _comment_json(self, number: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.inbox.post_comment(number, body)
        if not self._find_comment(self.inbox.comments(number), payload["schema_version"], payload.get("request_id", "")):
            raise InboxTransportError("REMOTE_PUBLICATION_UNVERIFIED")

    def _result(self, request: InboxRequest, number: int, status: str, result: Dict[str, Any], evidence: Dict[str, Any], error_code: Optional[str] = None) -> Dict[str, Any]:
        payload = {"schema_version": RESULT_SCHEMA, "request_id": request.request_id, "github_issue_number": number, "status": status, "capability": request.capability, "result": result, "evidence": evidence, "runtime": {"runtime_id": self.runtime_id, "build_revision": __commit__, "version": __version__}}
        if error_code:
            payload["error"] = {"code": error_code}
        return payload

    def _execute(self, request: InboxRequest) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        task = Task(task_id=f"github-{request.request_id}", capability_id=request.capability, account_id="github-inbox", project_id="github-inbox", input=request.input, constraints=request.constraints, deadline=now + timedelta(seconds=60), workspace_policy="retain", evidence_policy="required", requested_by=self._authorized_actor, created_at=now)
        context = self.execution_manager.submit_task(task)
        self.execution_manager.execute_sync(context.execution_id)
        status = context.status.value
        terminal = status if status in {"SUCCEEDED", "FAILED", "TIMED_OUT"} else "BLOCKED"
        result = context.result if isinstance(context.result, dict) else {}
        evidence = {"execution_id": context.execution_id, "result_sha256": context.result_hash, "started_at": context.started_at.isoformat() if context.started_at else None, "finished_at": context.completed_at.isoformat() if context.completed_at else None}
        return self._result(request, 0, terminal, result, evidence, context.failure_reason.value if context.failure_reason else None)

    def _process(self, issue: Dict[str, Any]) -> None:
        number = issue.get("number")
        if not isinstance(number, int):
            return
        try:
            request = parse_inbox_request(issue, self._authorized_actor)
        except InboxContractError as exc:
            # Other actors and unrelated issues are deliberately ignored.
            if exc.code in {"ACTOR_NOT_AUTHORIZED", "TITLE_NOT_ACCEPTED", "NOT_ISSUE"}:
                return
            request_id = "INVALID"
            existing = self.inbox.comments(number)
            if not self._find_comment(existing, "anny.task-rejection.v1", request_id):
                self._comment_json(number, {"schema_version": "anny.task-rejection.v1", "request_id": request_id, "github_issue_number": number, "status": "BLOCKED", "error": {"code": exc.code}})
            return
        comments = self.inbox.comments(number)
        state = self.state_store.get(number)
        if state.get("stage") == "COMPLETED":
            return
        if self._find_comment(comments, RESULT_SCHEMA, request.request_id):
            self.inbox.close_issue(number)
            state.update({"request_id": request.request_id, "stage": "COMPLETED", "updated_at": _utc_now()})
            self.state_store.put(number, state)
            return
        if state and state.get("request_id") != request.request_id:
            self._comment_json(number, self._result(request, number, "BLOCKED", {}, {}, "ISSUE_REQUEST_ID_CONFLICT"))
            return
        if not state:
            state = {"request_id": request.request_id, "stage": "ACKNOWLEDGED", "updated_at": _utc_now()}
            self.state_store.put(number, state)
        if not self._find_comment(comments, ACK_SCHEMA, request.request_id):
            self._comment_json(number, {"schema_version": ACK_SCHEMA, "request_id": request.request_id, "github_issue_number": number, "status": "ACKNOWLEDGED", "capability": request.capability})
        payload = state.get("result")
        if not isinstance(payload, dict):
            payload = self._execute(request)
            payload["github_issue_number"] = number
            state.update({"stage": "EXECUTED", "result": payload, "updated_at": _utc_now()})
            self.state_store.put(number, state)
        self._comment_json(number, payload)
        self.inbox.close_issue(number)
        state.update({"stage": "COMPLETED", "updated_at": _utc_now()})
        self.state_store.put(number, state)
        self._set(last_result={"issue_number": number, "request_id": request.request_id, "status": payload.get("status")})

    def poll_once(self) -> None:
        self._set(last_poll=_utc_now())
        try:
            for issue in self.inbox.list_open_issues():
                self._process(issue)
            self._set(last_successful_poll=_utc_now(), last_error_code=None, consecutive_failures=0)
        except Exception as exc:
            current = int(self.status().get("consecutive_failures", 0))
            self._set(last_error_code=_normalized_error(exc), consecutive_failures=current + 1)
