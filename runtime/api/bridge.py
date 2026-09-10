"""ChatGPT/Luna Bridge API for ANNY Runtime.

Production-adapted bridge. Uses the canonical ExecutionManager architecture.

Routes:
  POST /api/v1/bridge/tasks            — create and execute a task
  GET  /api/v1/bridge/tasks/{task_id}   — query task
  GET  /api/v1/bridge/executions/{eid}  — query execution
"""
import json
import uuid
import hashlib
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional

from runtime.execution.models import Task, ExecutionStatus
from runtime.core.config import get_data_dir
from runtime.journal.journal import OperationJournal, JournalEntry

class BridgeAuthError(Exception): pass
class CapabilityNotFoundError(Exception): pass
class PolicyDeniedError(Exception): pass
class TaskCreationFailedError(Exception): pass


# ── Allowed bridge capabilities ──────────────────────────────────
ALLOWED_CAPABILITIES = frozenset({
    "fabric.read",
    "repository.read",
    "repository.search",
    "filesystem.inspect",
    "fabric.register",
})

# ── Forbidden top-level fields ───────────────────────────────────
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

class BridgeRouter:
    """API Bridge for ChatGPT/Luna external interaction."""

    def __init__(self, admin_context: Dict[str, Any]):
        self.context = admin_context

    def _authenticate(self, handler: BaseHTTPRequestHandler):
        token = handler.headers.get("X-Bridge-Token")
        if not token:
            raise BridgeAuthError("Invalid or missing X-Bridge-Token")
            
        secret_backend = self.context.get("secret_backend")
        if not secret_backend:
            raise BridgeAuthError("System misconfigured: missing secret_backend")
            
        expected_bytes = secret_backend.retrieve("bridge_token")
        expected = expected_bytes.decode('utf-8') if expected_bytes else None
        if not expected or token != expected:
            raise BridgeAuthError("Invalid or missing X-Bridge-Token")

    def _send_json(self, handler: BaseHTTPRequestHandler, data: Any,
                   status: int = 200):
        handler.send_response(status)
        handler.send_header('Content-type', 'application/json; charset=utf-8')
        handler.end_headers()
        body = json.dumps(data) if not isinstance(data, str) else data
        handler.wfile.write(body.encode('utf-8'))

    def _send_error(self, handler: BaseHTTPRequestHandler, error_type: str,
                    message: str, status: int):
        self._send_json(handler, {"error": error_type, "message": message},
                        status=status)

    def dispatch(self, parsed: urllib.parse.ParseResult,
                 handler: BaseHTTPRequestHandler,
                 request_body: bytes = b""):
        """Main dispatcher for bridge endpoints."""
        method = handler.command

        try:
            self._authenticate(handler)
        except BridgeAuthError as e:
            self._send_error(handler, "BRIDGE_AUTH_ERROR", str(e), 401)
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
        except Exception as e:
            self._send_error(handler, "INTERNAL_ERROR", str(e), 500)

    # ── POST /api/v1/bridge/tasks ────────────────────────────────

    def handle_create_task(self, handler: BaseHTTPRequestHandler,
                           request_body: bytes):
        if not request_body:
            length = int(handler.headers.get('content-length', 0))
            if length > 0:
                request_body = handler.rfile.read(length)

        if not request_body:
            self._send_error(handler, "BRIDGE_INVALID_REQUEST",
                             "Empty request body", 400)
            return

        try:
            data = json.loads(request_body)
        except json.JSONDecodeError:
            self._send_error(handler, "BRIDGE_INVALID_REQUEST",
                             "Invalid JSON", 400)
            return

        # 1. Reject unknown top-level fields
        extra = set(data.keys()) - ALLOWED_FIELDS
        if extra:
            self._send_error(handler, "BRIDGE_INVALID_REQUEST",
                             f"Prohibited fields: {sorted(extra)}", 400)
            return

        intent = data.get("intent")
        capability = data.get("requested_capability")
        input_data = data.get("input", {})
        constraints = data.get("constraints", {})

        if not intent or not capability:
            self._send_error(handler, "BRIDGE_INVALID_REQUEST",
                             "Missing intent or requested_capability", 400)
            return

        # 2. Reject forbidden constraints
        forbidden = set(constraints.keys()) & FORBIDDEN_CONSTRAINTS
        if forbidden:
            self._send_error(handler, "POLICY_DENIED",
                             f"Constraint override not permitted: {sorted(forbidden)}", 403)
            return

        # 3. Check capability exists
        if capability not in ALLOWED_CAPABILITIES:
            self._send_error(handler, "CAPABILITY_NOT_FOUND",
                             f"Capability '{capability}' not available via bridge", 404)
            return

        # ── Execution via Canonical Architecture ───────────────────
        try:
            execution_manager = self.context.get("execution_manager")
            if not execution_manager:
                raise RuntimeError("System misconfigured: execution_manager missing")

            task_id = f"tsk-{uuid.uuid4().hex[:12]}"
            task = Task(
                task_id=task_id,
                capability_id=capability,
                input_data=input_data,
                constraints=constraints,
                deadline=None,
                workspace_policy="keep"
            )

            # Submit and execute synchronously
            exec_ctx = execution_manager.submit_task(task)
            exec_ctx = execution_manager.execute_sync(exec_ctx.execution_id)

            # Record durability
            journal = OperationJournal(str(get_data_dir()))
            now = datetime.now(timezone.utc).isoformat()
            
            entry = JournalEntry(
                entry_id=f"ev-{exec_ctx.execution_id}",
                operation_id=task_id,
                execution_id=exec_ctx.execution_id,
                session_id="bridge_session",
                actor_id="chatgpt_luna",
                workspace_id=exec_ctx.workspace_path,
                tool=capability,
                state=exec_ctx.status.name,
                started_at=now,
                runtime_generation=1,
                finished_at=now,
                metadata={"intent": intent, "source": "chatgpt_luna"}
            )
            journal.record(entry)

            self._send_json(handler, {
                "task_id": task_id,
                "execution_id": exec_ctx.execution_id,
                "status": exec_ctx.status.name,
                "source": "chatgpt_luna",
            }, status=201)
            
        except Exception as e:
            self._send_error(handler, "EXECUTION_FAILED", f"Execution failed: {e}", 500)

    # ── GET /api/v1/bridge/tasks/{task_id} ───────────────────────

    def handle_get_task(self, handler: BaseHTTPRequestHandler, task_id: str):
        journal = OperationJournal(str(get_data_dir()))
        entries = journal.get_operation(task_id)
        if not entries:
            self._send_error(handler, "RESULT_UNAVAILABLE", f"Task {task_id} not found", 404)
            return
            
        entry = entries[0]
        self._send_json(handler, {
            "task_id": entry.operation_id,
            "execution_id": entry.execution_id,
            "capability": entry.tool,
            "intent": entry.metadata.get("intent", "unknown"),
            "source": entry.metadata.get("source", "chatgpt_luna")
        })

    # ── GET /api/v1/bridge/executions/{execution_id} ─────────────

    def handle_get_execution(self, handler: BaseHTTPRequestHandler, exec_id: str):
        journal = OperationJournal(str(get_data_dir()))
        # We need to search entries by execution_id
        # JournalEntry has entry_id = ev-{execution_id}
        entry = journal.get_entry(f"ev-{exec_id}")
        if not entry:
            self._send_error(handler, "RESULT_UNAVAILABLE", f"Execution {exec_id} not found", 404)
            return
            
        self._send_json(handler, {
            "execution_id": entry.execution_id,
            "task_id": entry.operation_id,
            "capability": entry.tool,
            "status": entry.state,
            "source": entry.metadata.get("source", "chatgpt_luna"),
            "durability": "DURABLE"
        })
