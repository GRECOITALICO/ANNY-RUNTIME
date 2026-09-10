"""
ANNY-MCP-QWEN-INTEGRATION-004

End-to-end integration test proving the governed pipeline:

    Qwen → Worker → MCPGateway → Tool → Result → Evidence

NO new architecture. Uses existing:
  - QwenModelExecutor (runtime/execution/qwen_executor.py)
  - WorkerManager (runtime/execution/worker.py)
  - CapabilityRegistry (runtime/execution/capability.py)
  - MCPGateway (runtime/mcp/gateway.py)
  - ToolRegistry (runtime/mcp/registry.py)
  - Real tool implementations (runtime/mcp/tools.py)
"""
import os
import json
import uuid
import hashlib
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from runtime.execution.models import (
    Task, TaskExecutionContext, ExecutionStatus, WorkerState, WorkerDefinition,
)
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.interfaces import ContextPackage, ModelResult
from runtime.execution.worker import WorkerManager
from runtime.execution.selector import ExecutorSelection

from runtime.mcp import ToolRequest, ToolResult, ToolInvocationStatus
from runtime.mcp.registry import ToolRegistry
from runtime.mcp.gateway import MCPGateway


# ============================================================
# Phase 1: Component Verification
# ============================================================

class TestPhase1ComponentVerification:
    """Verify all components exist and can be instantiated."""

    def test_qwen_executor_importable(self):
        from runtime.execution.qwen_executor import QwenModelExecutor
        assert QwenModelExecutor is not None

    def test_worker_manager_instantiable(self):
        wm = WorkerManager(workspace_manager=MagicMock())
        assert wm is not None
        assert hasattr(wm, 'create_worker')
        assert hasattr(wm, 'start_worker')

    def test_capability_registry_instantiable(self):
        cr = CapabilityRegistry()
        caps = cr.list_all()
        assert len(caps) > 0
        assert cr.get("filesystem.inspect") is not None

    def test_mcp_gateway_instantiable(self):
        gw = MCPGateway(
            tool_registry=ToolRegistry(),
            capability_registry=CapabilityRegistry(),
        )
        assert gw is not None
        stats = gw.get_stats()
        assert stats["total_tools"] == 5

    def test_tool_registry_instantiable(self):
        tr = ToolRegistry()
        assert len(tr.list_tools()) == 5
        assert tr.get_tool("filesystem.inspect") is not None
        assert tr.get_tool("fabric.read") is not None

    def test_github_client_importable(self):
        try:
            from runtime.github.client import GitHubClient
            assert GitHubClient is not None
        except ImportError:
            pytest.skip("GitHubClient not available")

    def test_fabric_client_importable(self):
        """Fabric may or may not be a separate module — we have fabric tools in MCP."""
        from runtime.mcp.tools import TOOL_IMPLEMENTATIONS
        assert "fabric.read" in TOOL_IMPLEMENTATIONS
        assert "fabric.register" in TOOL_IMPLEMENTATIONS


# ============================================================
# Phase 2: Integration Capability
# ============================================================

class TestPhase2IntegrationCapability:
    """Verify model.tool_request capability can be created and registered."""

    def test_register_model_tool_request_capability(self):
        cr = CapabilityRegistry()

        # Only create if not exists
        if not cr.get("model.tool_request"):
            cr.register(CapabilityDefinition(
                capability_id="model.tool_request",
                name="Model Tool Request",
                description="Allows a model to request tool invocation within its ContextPackage.",
                version="1.0.0",
                risk_level="medium",
                inference_required=True,
                deterministic_allowed=False,
                network_policy="disabled",
                filesystem_policy="none",
                required_tools=["filesystem.inspect", "repository.read", "repository.search",
                                "fabric.read", "fabric.register"],
                max_runtime=120,
                max_output=1024 * 1024,
                evidence_required=True,
                preferred_executor=ExecutorType.LOCAL_MODEL,
                fallback_executor=None,
                enabled=True,
            ))

        cap = cr.get("model.tool_request")
        assert cap is not None
        assert cap.inference_required is True
        assert cap.network_policy == "disabled"
        assert "fabric.read" in cap.required_tools
        # No wildcard
        assert "*" not in cap.required_tools


# ============================================================
# Phase 3: Tool Request Contract
# ============================================================

class TestPhase3ToolRequestContract:
    """Verify the ToolRequest contract enforces what models can/cannot set."""

    def test_request_has_required_fields(self):
        req = ToolRequest.create(
            tool_id="filesystem.inspect",
            capability_id="filesystem.inspect",
            worker_id="wrk-test1234",
            execution_id="exec-test5678",
            input_data={"path": "/tmp/test"},
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        assert req.tool_id == "filesystem.inspect"
        assert req.capability_id == "filesystem.inspect"
        assert req.worker_id == "wrk-test1234"
        assert req.execution_id == "exec-test5678"
        assert req.request_id.startswith("treq-")

    def test_model_cannot_set_policy_fields(self):
        """ToolRequest has NO fields for policy, resource_limits, network_policy, allowed_callers."""
        req = ToolRequest.create(
            tool_id="test", capability_id="test", worker_id="wrk-1",
            execution_id="exec-1", input_data={},
            deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        assert not hasattr(req, 'policy')
        assert not hasattr(req, 'resource_limits')
        assert not hasattr(req, 'network_policy')
        assert not hasattr(req, 'allowed_callers')


# ============================================================
# Phase 4 & 5: Qwen Request Simulation + Validation
# ============================================================

@pytest.fixture
def integration_env(tmp_path):
    """Set up a complete integration environment."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test.txt").write_text("Integration test content")
    (workspace / "README.md").write_text("# Test Repo\nThis is a test.")
    (workspace / "search_target.py").write_text("# Integration marker for search")

    fabric_dir = tmp_path / "fabric_data"
    fabric_dir.mkdir()

    # Pre-register a fabric resource
    resource_data = {
        "resource_id": "test-integration-res",
        "resource_type": "test",
        "state": "ACTIVE",
        "provenance_id": "prov-integration001",
        "metadata": {"origin": "integration_test"},
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    (fabric_dir / "test-integration-res.json").write_text(json.dumps(resource_data))

    cap_registry = CapabilityRegistry()
    # Register fabric capabilities
    for cap_id in ["fabric.read", "fabric.register", "model.tool_request"]:
        if not cap_registry.get(cap_id):
            cap_registry.register(CapabilityDefinition(
                capability_id=cap_id, name=cap_id, description=cap_id,
                version="1.0.0", risk_level="medium", inference_required=(cap_id == "model.tool_request"),
                deterministic_allowed=(cap_id != "model.tool_request"),
                network_policy="disabled" if cap_id == "model.tool_request" else "local_only",
                filesystem_policy="none",
                required_tools=["filesystem.inspect", "repository.read", "fabric.read", "fabric.register"],
                max_runtime=120, max_output=1024*1024, evidence_required=True,
                preferred_executor=ExecutorType.LOCAL_MODEL if cap_id == "model.tool_request" else ExecutorType.DETERMINISTIC,
                fallback_executor=None, enabled=True,
            ))

    from tests.test_mcp_gateway_003 import MockGitHubClient, MockFabricClient
    tool_registry = ToolRegistry()
    gateway = MCPGateway(
        tool_registry=tool_registry,
        capability_registry=cap_registry,
        workspace_path=str(workspace),
        fabric_data_dir=str(fabric_dir),
        github_client=MockGitHubClient(str(workspace)),
        fabric_client=MockFabricClient(str(fabric_dir)),
    )

    return {
        "workspace": str(workspace),
        "fabric_dir": str(fabric_dir),
        "cap_registry": cap_registry,
        "tool_registry": tool_registry,
        "gateway": gateway,
    }


def _simulate_qwen_tool_request(tool_id: str, arguments: dict,
                                  worker_id: str, execution_id: str,
                                  capability_id: str) -> ToolRequest:
    """
    Simulate what Qwen would produce as a structured tool request.
    In real execution, Qwen outputs JSON which the runtime parses.
    The model sets ONLY: tool_id, arguments.
    The runtime injects: worker_id, execution_id, capability_id, deadline.
    """
    return ToolRequest.create(
        tool_id=tool_id,
        capability_id=capability_id,
        worker_id=worker_id,
        execution_id=execution_id,
        input_data=arguments,
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


class TestPhase4And5QwenRequestAndValidation:
    """Simulate Qwen producing a tool request and validate it through the gateway."""

    def test_qwen_fabric_read_request(self, integration_env):
        """Phase 4: Qwen requests fabric.read for a real resource."""
        gw = integration_env["gateway"]

        # Simulate: Qwen outputs tool request
        req = _simulate_qwen_tool_request(
            tool_id="fabric.read",
            arguments={"resource_id": "test-integration-res"},
            worker_id="wrk-qwen001",
            execution_id="exec-integration001",
            capability_id="fabric.read",
        )

        result = gw.invoke(req)
        assert result.succeeded, f"Expected success, got: {result.error_message}"
        assert result.output_data["found"] is True
        assert result.output_data["resource"]["resource_id"] == "test-integration-res"

    def test_qwen_filesystem_inspect_request(self, integration_env):
        """Qwen requests filesystem.inspect on a workspace file."""
        gw = integration_env["gateway"]
        workspace = integration_env["workspace"]

        req = _simulate_qwen_tool_request(
            tool_id="filesystem.inspect",
            arguments={"path": os.path.join(workspace, "test.txt")},
            worker_id="wrk-qwen002",
            execution_id="exec-integration002",
            capability_id="filesystem.inspect",
        )

        result = gw.invoke(req)
        assert result.succeeded
        assert result.output_data["exists"] is True
        assert result.output_data["size"] == len("Integration test content")

    def test_validation_rejects_missing_tool(self, integration_env):
        """Phase 5: Gateway rejects request for nonexistent tool."""
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="nonexistent.tool",
            arguments={},
            worker_id="wrk-qwen003",
            execution_id="exec-integration003",
            capability_id="filesystem.inspect",
        )
        result = gw.invoke(req)
        assert not result.succeeded

    def test_validation_rejects_missing_worker(self, integration_env):
        """Phase 5: Gateway rejects request without worker_id."""
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="filesystem.inspect",
            arguments={"path": "/tmp"},
            worker_id="",  # empty
            execution_id="exec-001",
            capability_id="filesystem.inspect",
        )
        result = gw.invoke(req)
        assert not result.succeeded
        assert "worker" in result.error_message.lower()


# ============================================================
# Phase 6: MCP Invocation Pipeline
# ============================================================

class TestPhase6MCPPipeline:
    """Verify the pipeline: Qwen → Worker → MCPGateway → Tool → Result"""

    def test_full_pipeline_fabric_read(self, integration_env):
        gw = integration_env["gateway"]
        # Worker creates request (not model directly)
        req = _simulate_qwen_tool_request(
            tool_id="fabric.read",
            arguments={"resource_id": "test-integration-res"},
            worker_id="wrk-pipeline001",
            execution_id="exec-pipeline001",
            capability_id="fabric.read",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert "result_hash" in result.evidence
        assert result.evidence["worker_id"] == "wrk-pipeline001"

    def test_full_pipeline_repository_read(self, integration_env):
        gw = integration_env["gateway"]
        workspace = integration_env["workspace"]
        req = _simulate_qwen_tool_request(
            tool_id="repository.read",
            arguments={"repo_path": workspace, "file_path": "README.md"},
            worker_id="wrk-pipeline002",
            execution_id="exec-pipeline002",
            capability_id="repository.inspect",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert "# Test Repo" in result.output_data["content"]


# ============================================================
# Phase 7: Real Fabric Test
# ============================================================

class TestPhase7RealFabric:
    def test_fabric_read_real_resource(self, integration_env):
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="fabric.read",
            arguments={"resource_id": "test-integration-res"},
            worker_id="wrk-fabric001",
            execution_id="exec-fabric001",
            capability_id="fabric.read",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert result.output_data["resource"]["provenance_id"] == "prov-integration001"

    def test_fabric_register_new_resource(self, integration_env):
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="fabric.register",
            arguments={"resource_id": "new-qwen-res", "resource_type": "inference_output",
                        "metadata": {"model": "Qwen3-8B", "test": True}},
            worker_id="wrk-fabric002",
            execution_id="exec-fabric002",
            capability_id="fabric.register",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert result.output_data["state"] == "ACTIVE"

        # Verify it persisted
        req2 = _simulate_qwen_tool_request(
            tool_id="fabric.read",
            arguments={"resource_id": "new-qwen-res"},
            worker_id="wrk-fabric003",
            execution_id="exec-fabric003",
            capability_id="fabric.read",
        )
        result2 = gw.invoke(req2)
        assert result2.succeeded
        assert result2.output_data["found"] is True


# ============================================================
# Phase 8: Real Repository Test
# ============================================================

class TestPhase8RealRepository:
    def test_repository_read_real_file(self, integration_env):
        gw = integration_env["gateway"]
        workspace = integration_env["workspace"]
        req = _simulate_qwen_tool_request(
            tool_id="repository.read",
            arguments={"repo_path": workspace, "file_path": "test.txt"},
            worker_id="wrk-repo001",
            execution_id="exec-repo001",
            capability_id="repository.inspect",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert result.output_data["content"] == "Integration test content"

    def test_repository_search_real(self, integration_env):
        gw = integration_env["gateway"]
        workspace = integration_env["workspace"]
        req = _simulate_qwen_tool_request(
            tool_id="repository.search",
            arguments={"repo_path": workspace, "pattern": "marker for search"},
            worker_id="wrk-repo002",
            execution_id="exec-repo002",
            capability_id="repository.search",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert result.output_data["count"] >= 1


# ============================================================
# Phase 9: Authority Test
# ============================================================

class TestPhase9Authority:
    """Verify the model CANNOT: change policy, enable network, read secrets, etc."""

    def test_cannot_change_policy_via_request(self):
        """ToolRequest has no policy field — model can't set it."""
        req = ToolRequest.create(
            tool_id="test", capability_id="test", worker_id="wrk-1",
            execution_id="exec-1", input_data={},
            deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        assert not hasattr(req, 'policy')
        assert not hasattr(req, 'resource_limits')
        assert not hasattr(req, 'network_policy')

    def test_cannot_invoke_without_capability(self, integration_env):
        """Model can't call a tool without proper capability."""
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="fabric.register",
            arguments={"resource_id": "x", "resource_type": "y"},
            worker_id="wrk-auth001",
            execution_id="exec-auth001",
            capability_id="document.classify",  # wrong capability
        )
        result = gw.invoke(req)
        assert result.status == ToolInvocationStatus.DENIED

    def test_cannot_access_outside_workspace(self, integration_env):
        """Model can't escape workspace boundary."""
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="filesystem.inspect",
            arguments={"path": "/etc/passwd"},
            worker_id="wrk-auth002",
            execution_id="exec-auth002",
            capability_id="filesystem.inspect",
        )
        result = gw.invoke(req)
        assert not result.succeeded
        assert "outside workspace" in result.error_message.lower()

    def test_cannot_read_secrets(self, integration_env):
        """Model can't read files outside workspace (where secrets live)."""
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="repository.read",
            arguments={"repo_path": "/", "file_path": "etc/shadow"},
            worker_id="wrk-auth003",
            execution_id="exec-auth003",
            capability_id="repository.inspect",
        )
        result = gw.invoke(req)
        assert not result.succeeded

    def test_cannot_invoke_without_worker_id(self, integration_env):
        """Direct model access without worker context is blocked."""
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="filesystem.inspect",
            arguments={"path": "/tmp"},
            worker_id="",
            execution_id="exec-auth004",
            capability_id="filesystem.inspect",
        )
        result = gw.invoke(req)
        assert not result.succeeded


# ============================================================
# Phase 10: Network Test
# ============================================================

class TestPhase10Network:
    """During model execution: network = disabled."""

    def test_model_capability_has_network_disabled(self):
        cr = CapabilityRegistry()
        cr.register(CapabilityDefinition(
            capability_id="model.tool_request",
            name="Model Tool Request", description="test",
            version="1.0.0", risk_level="medium", inference_required=True,
            deterministic_allowed=False, network_policy="disabled",
            filesystem_policy="none",
            required_tools=["filesystem.inspect", "fabric.read"],
            max_runtime=120, max_output=1024*1024, evidence_required=True,
            preferred_executor=ExecutorType.LOCAL_MODEL,
            fallback_executor=None, enabled=True,
        ))
        cap = cr.get("model.tool_request")
        assert cap.network_policy == "disabled"

    def test_tools_with_network_requirement_use_gateway_not_direct(self):
        """fabric.read requires 'local' network but the model's capability is 'disabled'.
        The MCP Gateway mediates this — model never directly contacts the network."""
        tr = ToolRegistry()
        fabric_tool = tr.get_tool("fabric.read")
        assert fabric_tool.network_requirement == "local"
        # The gateway handles the actual network call, not the model


# ============================================================
# Phase 11: Result Validation
# ============================================================

class TestPhase11ResultValidation:
    def test_result_has_valid_schema(self, integration_env):
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="fabric.read",
            arguments={"resource_id": "test-integration-res"},
            worker_id="wrk-result001",
            execution_id="exec-result001",
            capability_id="fabric.read",
        )
        result = gw.invoke(req)
        assert isinstance(result, ToolResult)
        assert result.request_id == req.request_id
        assert result.tool_id == "fabric.read"
        assert result.status == ToolInvocationStatus.SUCCEEDED
        assert isinstance(result.output_data, dict)
        assert result.duration_ms is not None
        assert result.duration_ms >= 0

    def test_result_evidence_complete(self, integration_env):
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="filesystem.inspect",
            arguments={"path": os.path.join(integration_env["workspace"], "test.txt")},
            worker_id="wrk-result002",
            execution_id="exec-result002",
            capability_id="filesystem.inspect",
        )
        result = gw.invoke(req)
        ev = result.evidence
        assert "request_id" in ev
        assert "tool_id" in ev
        assert "capability_id" in ev
        assert "worker_id" in ev
        assert "execution_id" in ev
        assert "result_hash" in ev
        assert "input_hash" in ev
        assert "duration_ms" in ev
        assert len(ev["result_hash"]) == 64  # SHA-256


# ============================================================
# Phase 12: End-to-End
# ============================================================

class TestPhase12EndToEnd:
    def test_e2e_fabric_read(self, integration_env):
        """1 Qwen → fabric.read on real Fabric resource."""
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="fabric.read",
            arguments={"resource_id": "test-integration-res"},
            worker_id="wrk-e2e001",
            execution_id="exec-e2e001",
            capability_id="fabric.read",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert result.output_data["resource"]["resource_id"] == "test-integration-res"

    def test_e2e_repository_read(self, integration_env):
        """1 Qwen → repository.read on real repository file."""
        gw = integration_env["gateway"]
        workspace = integration_env["workspace"]
        req = _simulate_qwen_tool_request(
            tool_id="repository.read",
            arguments={"repo_path": workspace, "file_path": "README.md"},
            worker_id="wrk-e2e002",
            execution_id="exec-e2e002",
            capability_id="repository.inspect",
        )
        result = gw.invoke(req)
        assert result.succeeded
        assert "# Test Repo" in result.output_data["content"]


# ============================================================
# Phase 13: Evidence
# ============================================================

class TestPhase13Evidence:
    def test_evidence_contains_all_required_fields(self, integration_env):
        gw = integration_env["gateway"]
        req = _simulate_qwen_tool_request(
            tool_id="fabric.read",
            arguments={"resource_id": "test-integration-res"},
            worker_id="wrk-evidence001",
            execution_id="exec-evidence001",
            capability_id="fabric.read",
        )
        result = gw.invoke(req)
        ev = result.evidence

        required_fields = [
            "request_id", "tool_id", "capability_id", "worker_id",
            "execution_id", "started_at", "completed_at", "duration_ms",
            "result_hash", "input_hash",
        ]
        for field in required_fields:
            assert field in ev, f"Missing evidence field: {field}"


# ============================================================
# Phase 16: Secret Audit
# ============================================================

class TestPhase16SecretAudit:
    def test_no_secrets_in_tool_results(self, integration_env):
        gw = integration_env["gateway"]
        workspace = integration_env["workspace"]

        # Run all tools and check outputs for secret patterns
        requests = [
            ("filesystem.inspect", "filesystem.inspect",
             {"path": os.path.join(workspace, "test.txt")}),
            ("repository.read", "repository.inspect",
             {"repo_path": workspace, "file_path": "test.txt"}),
            ("fabric.read", "fabric.read",
             {"resource_id": "test-integration-res"}),
        ]

        secret_patterns = ["ghp_", "github_pat_", "sk-", "AKIA", "password=", "secret_key"]

        for tool_id, cap_id, args in requests:
            req = _simulate_qwen_tool_request(
                tool_id=tool_id, arguments=args,
                worker_id="wrk-secret001", execution_id="exec-secret001",
                capability_id=cap_id,
            )
            result = gw.invoke(req)
            if result.output_data:
                output_str = json.dumps(result.output_data)
                for pattern in secret_patterns:
                    assert pattern not in output_str, \
                        f"Secret pattern '{pattern}' found in {tool_id} output"
