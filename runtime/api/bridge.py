"""ChatGPT/Luna Bridge API for ANNY Runtime.

Production-adapted bridge. Uses the canonical ExecutionManager architecture.

Flow:
  Bridge → Task → CapabilityRegistry → ExecutionManager → WorkerManager
  → MCPGateway → Tool/Model → Result → Evidence

Routes:
  POST /api/v1/bridge/tasks            — create and execute a task
  GET  /api/v1/bridge/tasks/{task_id}   — query task
  GET  /api/v1/bridge/executions/{eid}  — query execution
"""
import json
import uuid
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional

from runtime.execution.models import Task, ExecutionStatus
from runtime.core.config import get_data_dir
from runtime.journal.journal import OperationJournal, JournalEntry


class BridgeAuthError(Exception):
    pass

class BridgeError(Exception):
    pass


# ── Allowed bridge capabilities ──────────────────────────────────
ALLOWED_CAPABILITIES = frozenset({
    "fabric.read",
    "repository.read",
    "repository.search",
    "filesystem.inspect",
    "fabric.register",
})

# ── Allowed top-level request fields ─────────────────────────────
ALLOWED_FIELDS = frozenset({
    "intent",
    "requested_capability",
    "input",
    "constraints",
})

# ── Forbidden constraint keys ───────────────────────────────────
FORBIDDEN_CONSTRAINTS = frozenset({
    "network",
    "admin",
})

# ── Error codes (never expose internals) ─────────────────────────
ERROR_BRIDGE_AUTH       = "BRIDGE_AUTH_ERROR"
ERROR_INVALID_REQUEST   = "BRIDGE_INVALID_REQUEST"
ERROR_CAPABILITY_404    = "CAPABILITY_NOT_FOUND"
ERROR_POLICY_DENIED     = "POLICY_DENIED"
ERROR_EXECUTION_FAILED  = "EXECUTION_FAILED"
ERROR_RESULT_UNAVAIL    = "RESULT_UNAVAILABLE"


class BridgeRouter:
    """API Bridge for ChatGPT/Luna external interaction."""

    def __init__(self, admin_context: Dict[str, Any]):
        self.context = admin_context

    # ── Authentication ───────────────────────────────────────────
    def _authenticate(self, handler: BaseHTTPRequestHandler):
        token = handler.headers.get("X-Bridge-Token")
        if not token:
            raise BridgeAuthError()

        secret_backend = self.context.get("secret_backend")
        if not secret_backend:
            raise BridgeAuthError()

        expected_bytes = secret_backend.retrieve("bridge_token")
        expected = expected_bytes.decode("utf-8") if expected_bytes else None
        if not expected or token != expected:
            raise BridgeAuthError()

    # ── JSON helpers ─────────────────────────────────────────────
    def _send_json(self, handler: BaseHTTPRequestHandler, data: Any,
                   status: int = 200):
        handler.send_response(status)
        handler.send_header("Content-type", "application/json; charset=utf-8")
        handler.end_headers()
        body = json.dumps(data) if not isinstance(data, str) else data
        handler.wfile.write(body.encode("utf-8"))

    def _send_error(self, handler: BaseHTTPRequestHandler, error_type: str,
                    message: str, status: int):
        """Send a sanitized error response. Never includes internal details."""
        self._send_json(handler, {"error": error_type, "message": message},
                        status=status)

    # ── Dispatch ─────────────────────────────────────────────────
    def dispatch(self, parsed: urllib.parse.ParseResult,
                 handler: BaseHTTPRequestHandler,
                 request_body: bytes = b""):
        """Main dispatcher for bridge endpoints."""
        method = handler.command

        try:
            self._authenticate(handler)
        except BridgeAuthError:
            self._send_error(handler, ERROR_BRIDGE_AUTH,
                             "Invalid or missing credentials", 401)
            return

        path = parsed.path
        try:
            if method == "POST" and path == "/api/v1/bridge/tasks":
                self.handle_create_task(handler, request_body)
            elif method == "GET" and path.startswith("/api/v1/bridge/tasks/"):
                task_id = path.split("/")[-1]
                self.handle_get_task(handler, task_id)
            elif method == "GET" and path.startswith(
                    "/api/v1/bridge/executions/"):
                exec_id = path.split("/")[-1]
                self.handle_get_execution(handler, exec_id)
            else:
                self._send_error(handler, "NOT_FOUND",
                                 "Unknown bridge endpoint", 404)
        except Exception:
            self._send_error(handler, ERROR_EXECUTION_FAILED,
                             "An internal error occurred", 500)

    # ── POST /api/v1/bridge/tasks ────────────────────────────────
    def handle_create_task(self, handler: BaseHTTPRequestHandler,
                           request_body: bytes):
        # Read body if not already provided
        if not request_body:
            length = int(handler.headers.get("content-length", 0))
            if length > 0:
                request_body = handler.rfile.read(length)

        if not request_body:
            self._send_error(handler, ERROR_INVALID_REQUEST,
                             "Empty request body", 400)
            return

        try:
            data = json.loads(request_body)
        except json.JSONDecodeError:
            self._send_error(handler, ERROR_INVALID_REQUEST,
                             "Invalid JSON", 400)
            return

        # Reject unknown top-level fields
        extra = set(data.keys()) - ALLOWED_FIELDS
        if extra:
            self._send_error(handler, ERROR_INVALID_REQUEST,
                             "Prohibited fields in request", 400)
            return

        intent = data.get("intent")
        capability = data.get("requested_capability")
        input_data = data.get("input", {})
        constraints = data.get("constraints", {})

        if not intent or not capability:
            self._send_error(handler, ERROR_INVALID_REQUEST,
                             "Missing intent or requested_capability", 400)
            return

        # Reject forbidden constraints
        forbidden = set(constraints.keys()) & FORBIDDEN_CONSTRAINTS
        if forbidden:
            self._send_error(handler, ERROR_POLICY_DENIED,
                             "Constraint override not permitted", 403)
            return

        # Check capability exists in bridge allowlist
        if capability not in ALLOWED_CAPABILITIES:
            self._send_error(handler, ERROR_CAPABILITY_404,
                             "Capability not available via bridge", 404)
            return

        # ── Execution via Canonical Architecture ───────────────────
        execution_manager = self.context.get("execution_manager")
        if not execution_manager:
            self._send_error(handler, ERROR_EXECUTION_FAILED,
                             "Execution subsystem unavailable", 503)
            return

        try:
            now = datetime.now(timezone.utc)
            task_id = f"tsk-{uuid.uuid4().hex[:12]}"

            task = Task(
                task_id=task_id,
                capability_id=capability,
                input=input_data,
                constraints=constraints,
                deadline=now + timedelta(seconds=60),
                workspace_policy="keep",
                evidence_policy="journal",
                requested_by="chatgpt_luna",
                created_at=now,
            )

            # ── PHASE: QUEUED ──────────────────────────────────────
            journal = OperationJournal(str(get_data_dir()))
            exec_ctx = execution_manager.submit_task(task)

            journal.record(JournalEntry(
                entry_id=f"ev-q-{exec_ctx.execution_id}",
                operation_id=task_id,
                execution_id=exec_ctx.execution_id,
                session_id="bridge_session",
                actor_id="chatgpt_luna",
                workspace_id=exec_ctx.workspace_path or "",
                tool=capability,
                state="QUEUED",
                started_at=now.isoformat(),
                runtime_generation=1,
                metadata={"intent": intent, "source": "chatgpt_luna"},
            ))

            # ── PHASE: RUNNING → terminal ──────────────────────────
            journal.record(JournalEntry(
                entry_id=f"ev-r-{exec_ctx.execution_id}",
                operation_id=task_id,
                execution_id=exec_ctx.execution_id,
                session_id="bridge_session",
                actor_id="chatgpt_luna",
                workspace_id=exec_ctx.workspace_path or "",
                tool=capability,
                state="RUNNING",
                started_at=now.isoformat(),
                runtime_generation=1,
                metadata={"intent": intent, "source": "chatgpt_luna"},
            ))

            exec_ctx = execution_manager.execute_sync(exec_ctx.execution_id)
            finished = datetime.now(timezone.utc)
            terminal_state = exec_ctx.status.name  # SUCCEEDED / FAILED / TIMED_OUT

            journal.record(JournalEntry(
                entry_id=f"ev-t-{exec_ctx.execution_id}",
                operation_id=task_id,
                execution_id=exec_ctx.execution_id,
                session_id="bridge_session",
                actor_id="chatgpt_luna",
                workspace_id=exec_ctx.workspace_path or "",
                tool=capability,
                state=terminal_state,
                started_at=now.isoformat(),
                runtime_generation=1,
                finished_at=finished.isoformat(),
                metadata={"intent": intent, "source": "chatgpt_luna"},
            ))

            self._send_json(handler, {
                "task_id": task_id,
                "execution_id": exec_ctx.execution_id,
                "status": terminal_state,
                "source": "chatgpt_luna",
            }, status=201)

        except Exception:
            self._send_error(handler, ERROR_EXECUTION_FAILED,
                             "Task execution failed", 500)

    # ── GET /api/v1/bridge/tasks/{task_id} ───────────────────────
    def handle_get_task(self, handler: BaseHTTPRequestHandler, task_id: str):
        try:
            journal = OperationJournal(str(get_data_dir()))
            entries = journal.get_operation(task_id)
            if not entries:
                self._send_error(handler, ERROR_RESULT_UNAVAIL,
                                 "Task not found", 404)
                return

            latest = entries[-1]
            self._send_json(handler, {
                "task_id": latest.operation_id,
                "execution_id": latest.execution_id,
                "capability": latest.tool,
                "state": latest.state,
                "intent": latest.metadata.get("intent", ""),
                "source": latest.metadata.get("source", "chatgpt_luna"),
            })
        except Exception:
            self._send_error(handler, ERROR_RESULT_UNAVAIL,
                             "Could not retrieve task", 500)

    # ── GET /api/v1/bridge/executions/{execution_id} ─────────────
    def handle_get_execution(self, handler: BaseHTTPRequestHandler,
                             exec_id: str):
        try:
            journal = OperationJournal(str(get_data_dir()))
            # Search all entries for this execution_id, return latest state
            matched = []
            with journal._lock:
                for e in journal._entries:
                    if e.execution_id == exec_id:
                        matched.append(e)

            if not matched:
                self._send_error(handler, ERROR_RESULT_UNAVAIL,
                                 "Execution not found", 404)
                return

            latest = matched[-1]
            self._send_json(handler, {
                "execution_id": latest.execution_id,
                "task_id": latest.operation_id,
                "capability": latest.tool,
                "state": latest.state,
                "source": latest.metadata.get("source", "chatgpt_luna"),
                "evidence_durability": "DURABLE",
            })
        except Exception:
            self._send_error(handler, ERROR_RESULT_UNAVAIL,
                             "Could not retrieve execution", 500)
