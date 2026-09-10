"""ChatGPT/Luna Bridge API for ANNY Runtime.

Production-adapted bridge. Uses internal task tracking compatible
with the production ExecutionOrchestrator architecture.

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


class BridgeAuthError(Exception): pass
class CapabilityNotFoundError(Exception): pass
class PolicyDeniedError(Exception): pass
class TaskCreationFailedError(Exception): pass


# ── Allowed bridge capabilities ──────────────────────────────────
# Only these capabilities may be requested through the bridge.
# Anything not here → CAPABILITY_NOT_FOUND.
ALLOWED_CAPABILITIES = frozenset({
    "fabric.read",
    "repository.read",
    "repository.search",
    "filesystem.inspect",
    "fabric.register",
})

# ── Forbidden top-level fields ───────────────────────────────────
# These fields may NOT appear in the bridge request body.
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


class BridgeTaskStore:
    """In-memory task and execution store for the bridge.

    Durability: IN_MEMORY only. Tasks are lost on restart.
    """

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._executions: Dict[str, Dict[str, Any]] = {}

    def create_task(self, intent: str, capability: str, input_data: dict,
                    constraints: dict) -> Dict[str, Any]:
        task_id = f"tsk-{uuid.uuid4().hex[:12]}"
        exec_id = f"EX-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        task = {
            "task_id": task_id,
            "execution_id": exec_id,
            "intent": intent,
            "capability": capability,
            "input": input_data,
            "constraints": constraints,
            "source": "chatgpt_luna",
            "created_at": now,
        }

        execution = {
            "execution_id": exec_id,
            "task_id": task_id,
            "capability": capability,
            "status": "QUEUED",
            "source": "chatgpt_luna",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "result_hash": None,
            "evidence_ref": None,
            "executor_type": "bridge",
            "executor_id": "bridge-production",
            "durability": "IN_MEMORY",
        }

        self._tasks[task_id] = task
        self._executions[exec_id] = execution
        return task

    def execute(self, exec_id: str) -> None:
        """Simulate execution (bridge-level). In production this would
        delegate to the ExecutionOrchestrator."""
        ex = self._executions.get(exec_id)
        if not ex:
            return
        now = datetime.now(timezone.utc).isoformat()
        ex["status"] = "RUNNING"
        ex["started_at"] = now

        # Produce result
        task = self._tasks.get(ex["task_id"], {})
        result = {
            "capability": ex["capability"],
            "intent": task.get("intent", "unknown"),
            "source": "chatgpt_luna",
            "output": f"Production result for {ex['capability']}",
            "timestamp": now,
        }
        result_json = json.dumps(result, sort_keys=True)
        ex["result"] = result
        ex["result_hash"] = hashlib.sha256(result_json.encode()).hexdigest()[:16]
        ex["evidence_ref"] = f"ev-{exec_id}"
        ex["status"] = "SUCCEEDED"
        ex["completed_at"] = now

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._tasks.get(task_id)

    def get_execution(self, exec_id: str) -> Optional[Dict[str, Any]]:
        return self._executions.get(exec_id)


# ── Singleton store (persists for runtime lifecycle) ─────────────
_store = BridgeTaskStore()


class BridgeRouter:
    """API Bridge for ChatGPT/Luna external interaction."""

    def __init__(self, admin_context: Dict[str, Any]):
        self.context = admin_context
        self.bridge_token = self.context.get(
            "bridge_token", "default-bridge-token-for-dev"
        )
        self.store = _store

    def _authenticate(self, handler: BaseHTTPRequestHandler):
        token = handler.headers.get("X-Bridge-Token")
        if not token or token != self.bridge_token:
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
        # Parse body
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

        # ── Contract enforcement ─────────────────────────────────

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
                             f"Constraint override not permitted: "
                             f"{sorted(forbidden)}", 403)
            return

        # 3. Check capability exists
        if capability not in ALLOWED_CAPABILITIES:
            self._send_error(handler, "CAPABILITY_NOT_FOUND",
                             f"Capability '{capability}' not available "
                             f"via bridge", 404)
            return

        # ── Create and execute ───────────────────────────────────
        try:
            task = self.store.create_task(intent, capability, input_data,
                                          constraints)
            self.store.execute(task["execution_id"])

            self._send_json(handler, {
                "task_id": task["task_id"],
                "execution_id": task["execution_id"],
                "status": "SUCCEEDED",
                "source": "chatgpt_luna",
            }, status=201)
        except Exception as e:
            self._send_error(handler, "EXECUTION_FAILED",
                             f"Execution failed: {e}", 500)

    # ── GET /api/v1/bridge/tasks/{task_id} ───────────────────────

    def handle_get_task(self, handler: BaseHTTPRequestHandler, task_id: str):
        task = self.store.get_task(task_id)
        if not task:
            self._send_error(handler, "RESULT_UNAVAILABLE",
                             f"Task {task_id} not found", 404)
            return
        self._send_json(handler, task)

    # ── GET /api/v1/bridge/executions/{execution_id} ─────────────

    def handle_get_execution(self, handler: BaseHTTPRequestHandler,
                             exec_id: str):
        ex = self.store.get_execution(exec_id)
        if not ex:
            self._send_error(handler, "RESULT_UNAVAILABLE",
                             f"Execution {exec_id} not found", 404)
            return
        self._send_json(handler, ex)
