"""
ANNY-CHATGPT-LUNA-BRIDGE-005 Tests

Integration tests proving the governed HTTP bridge for ChatGPT/Luna.
"""
import json
import pytest
import tempfile
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from dataclasses import asdict

from runtime.api.bridge import BridgeRouter, BridgeAuthError, ALLOWED_CAPABILITIES
from runtime.execution.models import Task, ExecutionStatus, TaskExecutionContext
from runtime.execution.capability import CapabilityRegistry
from runtime.execution.manager import ExecutionManager
from runtime.journal.journal import OperationJournal, JournalEntry
from http.server import BaseHTTPRequestHandler

class MockHandler:
    def __init__(self, command="POST", headers=None):
        self.command = command
        self.headers = headers or {}
        self.status = None
        self.body = b""
        self.wfile = MagicMock()
        self.wfile.write.side_effect = self._write
        
    def send_response(self, status):
        self.status = status
        
    def send_header(self, *args): pass
    def end_headers(self): pass
    
    def _write(self, data):
        self.body += data

@pytest.fixture
def mock_exec_mgr():
    mgr = MagicMock(spec=ExecutionManager)
    mgr.registry = CapabilityRegistry()
    # Mock submit_task
    def mock_submit(task):
        ctx = TaskExecutionContext(
            execution_id="exec-123",
            task_id=task.task_id,
            capability_id=task.capability_id,
            workspace_path="/tmp",
            environment={},
            allowed_tools=[],
            deadline=task.deadline,
            resource_limits={},
            network_policy=task.constraints.get("network", "restricted"),
            write_policy="deny",
            status=ExecutionStatus.SUCCEEDED
        )
        return ctx
    mgr.submit_task.side_effect = mock_submit
    
    def mock_execute(exec_id):
        return TaskExecutionContext(
            execution_id=exec_id,
            task_id="tsk-123",
            capability_id="repository.read",
            workspace_path="/tmp",
            environment={},
            allowed_tools=[],
            deadline=datetime.now(timezone.utc),
            resource_limits={},
            network_policy="restricted",
            write_policy="deny",
            status=ExecutionStatus.SUCCEEDED
        )
    mgr.execute_sync.side_effect = mock_execute
    
    return mgr

@pytest.fixture
def bridge(mock_exec_mgr):
    class MockSecretBackend:
        def retrieve(self, key):
            return b"secret-token" if key == "bridge_token" else None
    
    return BridgeRouter({
        "secret_backend": MockSecretBackend(),
        "execution_manager": mock_exec_mgr
    })


# ============================================================
# Phase 3: Bridge Authentication
# ============================================================
def test_bridge_auth_missing(bridge):
    handler = MockHandler(headers={})
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler)
    assert handler.status == 401
    resp = json.loads(handler.body)
    assert resp["error"] == "BRIDGE_AUTH_ERROR"

def test_bridge_auth_invalid(bridge):
    handler = MockHandler(headers={"X-Bridge-Token": "bad-token"})
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler)
    assert handler.status == 401


# ============================================================
# Phase 2: Bridge Contract (Schema)
# ============================================================
def test_bridge_contract_rejects_worker_id(bridge):
    handler = MockHandler(command="POST", headers={"X-Bridge-Token": "secret-token"})
    payload = json.dumps({"intent": "read file", "requested_capability": "repository.read", "worker_id": "w-123"}).encode()
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler, request_body=payload)
    
    assert handler.status == 400
    resp = json.loads(handler.body)
    assert resp["error"] == "BRIDGE_INVALID_REQUEST"
    assert "Prohibited fields" in resp["message"]

def test_bridge_contract_missing_required(bridge):
    handler = MockHandler(command="POST", headers={"X-Bridge-Token": "secret-token"})
    payload = json.dumps({"intent": "read file"}).encode() # missing capability
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler, request_body=payload)
    assert handler.status == 400
    resp = json.loads(handler.body)
    assert "Missing intent or" in resp["message"]


# ============================================================
# Phase 5: Capability Resolution
# ============================================================
def test_capability_not_found(bridge):
    handler = MockHandler(command="POST", headers={"X-Bridge-Token": "secret-token"})
    payload = json.dumps({
        "intent": "hack the mainframe", 
        "requested_capability": "system.hack"
    }).encode()
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler, request_body=payload)
    
    assert handler.status == 404
    resp = json.loads(handler.body)
    assert resp["error"] == "CAPABILITY_NOT_FOUND"


# ============================================================
# Phase 6: Policy Enforcement
# ============================================================
def test_policy_rejects_network_override(bridge):
    handler = MockHandler(command="POST", headers={"X-Bridge-Token": "secret-token"})
    payload = json.dumps({
        "intent": "get weather", 
        "requested_capability": "repository.read",
        "constraints": {"network": "allow_all"}
    }).encode()
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler, request_body=payload)
    
    assert handler.status == 403
    resp = json.loads(handler.body)
    assert resp["error"] == "POLICY_DENIED"


# ============================================================
# Phase 4 & 7: Task Creation & Pipeline
# ============================================================
def test_task_creation_success(bridge, mock_exec_mgr):
    handler = MockHandler(command="POST", headers={"X-Bridge-Token": "secret-token"})
    payload = json.dumps({
        "intent": "read config", 
        "requested_capability": "repository.read",
        "input": {"target": "config.yaml"}
    }).encode()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("runtime.api.bridge.get_data_dir", return_value=tmpdir):
            bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler, request_body=payload)
    
    assert handler.status == 201
    resp = json.loads(handler.body)
    assert "task_id" in resp
    assert "execution_id" in resp
    
    # Verify submit_task was called with correct requested_by
    mock_exec_mgr.submit_task.assert_called_once()
    task = mock_exec_mgr.submit_task.call_args[0][0]
    assert task.requested_by == "chatgpt_luna"


# ============================================================
# Phase 10: Status API (via Journal)
# ============================================================
def test_get_task_status(bridge):
    """Verify bridge retrieves task status from the OperationJournal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a journal entry so the bridge can find it
        journal = OperationJournal(tmpdir)
        journal.record(JournalEntry(
            entry_id="ev-1",
            operation_id="tsk-123",
            execution_id="exec-456",
            session_id="bridge_session",
            actor_id="chatgpt_luna",
            workspace_id="/tmp",
            tool="repository.read",
            state="SUCCEEDED",
            started_at=datetime.now(timezone.utc).isoformat(),
            runtime_generation=1,
            metadata={"intent": "read config", "source": "chatgpt_luna"},
        ))

        with patch("runtime.api.bridge.get_data_dir", return_value=tmpdir):
            handler = MockHandler(command="GET", headers={"X-Bridge-Token": "secret-token"})
            bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks/tsk-123"), handler)
        
        assert handler.status == 200
        resp = json.loads(handler.body)
        assert resp["source"] == "chatgpt_luna"


# ============================================================
# Phase 7C-Negative: Bridge MUST reject filesystem.inspect
# ============================================================
def test_bridge_rejects_filesystem_inspect(bridge):
    """filesystem.inspect is NOT in the bridge allowlist."""
    assert "filesystem.inspect" not in ALLOWED_CAPABILITIES

    handler = MockHandler(command="POST", headers={"X-Bridge-Token": "secret-token"})
    payload = json.dumps({
        "intent": "inspect file",
        "requested_capability": "filesystem.inspect",
    }).encode()
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler, request_body=payload)

    assert handler.status == 404
    resp = json.loads(handler.body)
    assert resp["error"] == "CAPABILITY_NOT_FOUND"


# ============================================================
# Phase 7C-Negative: Bridge MUST reject shell/subprocess/overrides
# ============================================================
@pytest.mark.parametrize("bad_cap", [
    "shell.execute", "subprocess.run", "filesystem.arbitrary",
    "network.arbitrary", "secret.access", "policy.override",
    "worker.override", "executor.override",
])
def test_bridge_rejects_dangerous_capabilities(bridge, bad_cap):
    handler = MockHandler(command="POST", headers={"X-Bridge-Token": "secret-token"})
    payload = json.dumps({
        "intent": "dangerous",
        "requested_capability": bad_cap,
    }).encode()
    bridge.dispatch(MagicMock(path="/api/v1/bridge/tasks"), handler, request_body=payload)

    assert handler.status == 404
    resp = json.loads(handler.body)
    assert resp["error"] == "CAPABILITY_NOT_FOUND"


# ============================================================
# Phase 7C: Bridge allowlist contains exactly the canonical set
# ============================================================
def test_bridge_allowlist_exact():
    assert ALLOWED_CAPABILITIES == frozenset({
        "fabric.read",
        "fabric.register",
        "repository.read",
        "repository.search",
    })
