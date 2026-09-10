"""Tests for ANNY-MCP-GATEWAY-003."""
import os
import json
import pytest
import tempfile
from datetime import datetime, timezone, timedelta

from runtime.mcp import (
    ToolDefinition, ToolRequest, ToolResult, ToolPolicy,
    ToolState, ToolInvocationStatus,
)
from runtime.mcp.registry import ToolRegistry
from runtime.mcp.gateway import (
    MCPGateway, AuthorizationDeniedError, PolicyViolationError,
)
from runtime.execution.capability import CapabilityRegistry


@pytest.fixture
def tool_registry():
    return ToolRegistry()


@pytest.fixture
def cap_registry():
    return CapabilityRegistry()


@pytest.fixture
def workspace(tmp_path):
    # Create a test file in workspace
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "code.py").write_text("print('hi')")
    return str(tmp_path)


@pytest.fixture
def fabric_dir(tmp_path):
    d = tmp_path / "fabric_data"
    d.mkdir()
    return str(d)


@pytest.fixture
def gateway(tool_registry, cap_registry, workspace, fabric_dir):
    # Register extra capabilities needed by tools
    from runtime.execution.capability import CapabilityDefinition, ExecutorType
    for cap_id in ["fabric.read", "fabric.register"]:
        cap_registry.register(CapabilityDefinition(
            capability_id=cap_id, name=cap_id, description=cap_id,
            version="1.0.0", risk_level="low", inference_required=False,
            deterministic_allowed=True, network_policy="local_only",
            filesystem_policy="none", required_tools=[cap_id],
            max_runtime=60, max_output=1024*1024, evidence_required=True,
            preferred_executor=ExecutorType.DETERMINISTIC,
            fallback_executor=None, enabled=True,
        ))
    return MCPGateway(
        tool_registry=tool_registry,
        capability_registry=cap_registry,
        audit_manager=None,
        workspace_path=workspace,
        fabric_data_dir=fabric_dir,
    )


def _make_request(tool_id, cap_id, input_data=None):
    return ToolRequest.create(
        tool_id=tool_id,
        capability_id=cap_id,
        worker_id="wrk-test1234",
        execution_id="exec-test5678",
        input_data=input_data or {},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


# ============ Phase 2: Domain Model Tests ============

class TestDomainModels:
    def test_tool_definition_creation(self):
        td = ToolDefinition(
            tool_id="test.tool", name="Test", description="A test",
            input_schema={}, output_schema={}, required_capability="test.cap",
            network_requirement="none", timeout=30, version="1.0.0",
        )
        assert td.tool_id == "test.tool"
        assert td.state == ToolState.REGISTERED

    def test_tool_request_create(self):
        req = _make_request("test.tool", "test.cap", {"key": "val"})
        assert req.request_id.startswith("treq-")
        assert req.tool_id == "test.tool"
        assert req.input_data == {"key": "val"}

    def test_tool_result_evidence_hash(self):
        r = ToolResult(
            request_id="r1", tool_id="t1", status=ToolInvocationStatus.SUCCEEDED,
            output_data={"a": 1}, error_message=None,
            started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
            duration_ms=10,
        )
        h = r.compute_evidence_hash()
        assert len(h) == 64  # SHA-256 hex


# ============ Phase 3: Registry Tests ============

class TestToolRegistry:
    def test_initial_tools_registered(self, tool_registry):
        tools = tool_registry.list_tools()
        assert len(tools) == 5
        ids = {t.tool_id for t in tools}
        assert "filesystem.inspect" in ids
        assert "repository.read" in ids
        assert "repository.search" in ids
        assert "fabric.read" in ids
        assert "fabric.register" in ids

    def test_all_initial_tools_available(self, tool_registry):
        available = tool_registry.list_available()
        assert len(available) == 5

    def test_policies_registered(self, tool_registry):
        for tool_id in ["filesystem.inspect", "repository.read", "repository.search", "fabric.read", "fabric.register"]:
            assert tool_registry.get_policy(tool_id) is not None

    def test_disable_enable(self, tool_registry):
        tool_registry.disable_tool("filesystem.inspect")
        assert tool_registry.get_tool("filesystem.inspect").state == ToolState.DISABLED
        assert len(tool_registry.list_available()) == 4
        tool_registry.enable_tool("filesystem.inspect")
        assert tool_registry.get_tool("filesystem.inspect").state == ToolState.AVAILABLE


# ============ Phase 4: Gateway Pipeline Tests ============

class TestGatewayPipeline:
    def test_filesystem_inspect_success(self, gateway, workspace):
        req = _make_request("filesystem.inspect", "filesystem.inspect",
                            {"path": os.path.join(workspace, "test.txt")})
        result = gateway.invoke(req)
        assert result.succeeded
        assert result.output_data["exists"] is True
        assert result.output_data["size"] == 11
        assert result.evidence["result_hash"]

    def test_repository_read_success(self, gateway, workspace):
        req = _make_request("repository.read", "repository.inspect",
                            {"repo_path": workspace, "file_path": "test.txt"})
        result = gateway.invoke(req)
        assert result.succeeded
        assert result.output_data["content"] == "hello world"

    def test_repository_search_success(self, gateway, workspace):
        req = _make_request("repository.search", "repository.search",
                            {"repo_path": workspace, "pattern": "print"})
        result = gateway.invoke(req)
        assert result.succeeded
        assert result.output_data["count"] >= 1

    def test_fabric_register_then_read(self, gateway):
        # Register
        req = _make_request("fabric.register", "fabric.register",
                            {"resource_id": "test-res-001", "resource_type": "test", "metadata": {"k": "v"}})
        result = gateway.invoke(req)
        assert result.succeeded
        assert result.output_data["provenance_id"].startswith("prov-")

        # Read back
        req2 = _make_request("fabric.read", "fabric.read",
                             {"resource_id": "test-res-001"})
        result2 = gateway.invoke(req2)
        assert result2.succeeded
        assert result2.output_data["found"] is True

    def test_nonexistent_tool(self, gateway):
        req = _make_request("nonexistent.tool", "filesystem.inspect")
        result = gateway.invoke(req)
        assert not result.succeeded

    def test_evidence_always_present(self, gateway, workspace):
        req = _make_request("filesystem.inspect", "filesystem.inspect",
                            {"path": os.path.join(workspace, "test.txt")})
        result = gateway.invoke(req)
        assert "result_hash" in result.evidence
        assert "input_hash" in result.evidence
        assert "duration_ms" in result.evidence


# ============ Phase 5: Capability Boundary Tests ============

class TestCapabilityBoundary:
    def test_unauthorized_capability_denied(self, gateway):
        # document.classify is NOT in the allowed_callers for filesystem.inspect
        req = _make_request("filesystem.inspect", "document.classify",
                            {"path": "/tmp/test"})
        result = gateway.invoke(req)
        assert result.status == ToolInvocationStatus.DENIED
        assert "not authorized" in result.error_message

    def test_nonexistent_capability_denied(self, gateway):
        req = _make_request("filesystem.inspect", "nonexistent.cap",
                            {"path": "/tmp/test"})
        result = gateway.invoke(req)
        assert result.status == ToolInvocationStatus.DENIED

    def test_correct_capability_allowed(self, gateway, workspace):
        req = _make_request("filesystem.inspect", "filesystem.inspect",
                            {"path": os.path.join(workspace, "test.txt")})
        result = gateway.invoke(req)
        assert result.succeeded


# ============ Phase 6: Worker Boundary Tests ============

class TestWorkerBoundary:
    def test_missing_worker_id_rejected(self, gateway):
        req = _make_request("filesystem.inspect", "filesystem.inspect", {"path": "/tmp"})
        req.worker_id = ""  # Remove worker_id
        result = gateway.invoke(req)
        assert not result.succeeded
        assert "worker" in result.error_message.lower()

    def test_missing_execution_id_rejected(self, gateway):
        req = _make_request("filesystem.inspect", "filesystem.inspect", {"path": "/tmp"})
        req.execution_id = ""
        result = gateway.invoke(req)
        assert not result.succeeded


# ============ Policy Enforcement Tests ============

class TestPolicyEnforcement:
    def test_invocation_limit_enforced(self, gateway, workspace):
        # filesystem.inspect has max_invocations_per_execution=100
        # We'll test with a smaller custom policy
        gateway.tool_registry.register_policy(ToolPolicy(
            policy_id="pol-test-limit", tool_id="filesystem.inspect",
            max_invocations_per_execution=2, max_input_size=4096,
            max_output_size=1024*1024, require_evidence=True,
            allowed_callers=["filesystem.inspect", "filesystem.list", "filesystem.hash"],
            network_policy="disabled", filesystem_policy="read_only", audit_level="summary",
        ))

        path = os.path.join(workspace, "test.txt")
        for i in range(2):
            result = gateway.invoke(_make_request("filesystem.inspect", "filesystem.inspect", {"path": path}))
            assert result.succeeded

        # Third invocation should be denied
        result = gateway.invoke(_make_request("filesystem.inspect", "filesystem.inspect", {"path": path}))
        assert result.status == ToolInvocationStatus.DENIED
        assert "limit exceeded" in result.error_message.lower()

    def test_workspace_boundary_enforced(self, gateway):
        req = _make_request("filesystem.inspect", "filesystem.inspect",
                            {"path": "/etc/passwd"})
        result = gateway.invoke(req)
        assert not result.succeeded
        assert "outside workspace" in result.error_message.lower()


class TestGatewayStats:
    def test_stats_after_invocations(self, gateway, workspace):
        path = os.path.join(workspace, "test.txt")
        gateway.invoke(_make_request("filesystem.inspect", "filesystem.inspect", {"path": path}))
        stats = gateway.get_stats()
        assert stats["total_tools"] == 5
        assert stats["available_tools"] == 5
        assert stats["total_invocations"] >= 1
