import pytest
import os
from datetime import datetime, timezone, timedelta

from runtime.execution.models import (
    ModelDefinition, ModelState, Task, ExecutionStatus, ModelCapabilityBinding
)
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.registry import ModelRegistry
from runtime.intelligence.layer import LocalIntelligenceLayer
from runtime.intelligence.models import ImplementationProfile, BenchmarkResult, CertificationStatus
from runtime.orchestration.kernel import Orchestrator
from runtime.orchestration.plan import RoutingClass
from runtime.orchestration.frontier import DefaultFrontierExecutor
from runtime.execution.worker import WorkerManager
from runtime.execution.selector import ExecutorSelection


def create_test_model_registry(tmp_path):
    reg_path = tmp_path / "models.json"
    registry = ModelRegistry(storage_path=str(reg_path))
    return registry


def make_test_task(task_id: str, capability_id: str):
    return Task(
        task_id=task_id,
        capability_id=capability_id,
        account_id="acc-1",
        project_id="proj-1",
        input={"test": True},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        workspace_policy="workspace_only",
        evidence_policy="required",
        requested_by="test-user",
        created_at=datetime.now(timezone.utc)
    )


def test_dynamic_model_availability_reconciliation(tmp_path):
    registry = create_test_model_registry(tmp_path)
    frontier = DefaultFrontierExecutor(enabled=True)
    layer = LocalIntelligenceLayer()
    orchestrator = Orchestrator(
        model_registry=registry,
        intelligence_layer=layer,
        frontier_executor=frontier
    )

    # Initial state: qwen3-8b is INSTALL_REQUIRED -> unavailable
    assert registry.is_available("qwen3-8b") is False
    profile = layer._implementations.get("qwen3-8b")
    assert profile is not None
    assert profile.availability is False

    # Mark available in ModelRegistry
    registry.set_availability("qwen3-8b", True)
    assert registry.is_available("qwen3-8b") is True

    # Reconcile again
    orchestrator._reconcile_registries()
    profile = layer._implementations.get("qwen3-8b")
    assert profile.availability is True


def test_unregistered_model_removed_from_intelligence_layer(tmp_path):
    registry = create_test_model_registry(tmp_path)
    layer = LocalIntelligenceLayer()
    orchestrator = Orchestrator(model_registry=registry, intelligence_layer=layer)

    # Register temporary model
    temp_model = ModelDefinition(
        model_id="temp-model-v1",
        display_name="Temp Model",
        provider="local",
        executor_type="LOCAL_MODEL",
        version="1.0",
        status=ModelState.AVAILABLE,
        capabilities_supported=["document.classify"],
        capabilities_forbidden=[],
        hardware_requirements={},
        memory_requirements={},
        context_window=32000,
        quantization="int8",
        artifact_uri="local://temp",
        artifact_sha256="b" * 64,
        runtime_interface="llama.cpp",
        max_concurrency=1,
        max_runtime=300,
        max_input_size=20000,
        max_output_size=4000,
        network_policy="none",
        evidence_policy="required"
    )
    registry.register_model(temp_model)
    orchestrator._reconcile_registries()
    assert "temp-model-v1" in layer._implementations

    # Unregister model
    registry.unregister("temp-model-v1")
    orchestrator._reconcile_registries()
    assert "temp-model-v1" not in layer._implementations


def test_executor_type_and_execution_class_sync(tmp_path):
    registry = create_test_model_registry(tmp_path)
    layer = LocalIntelligenceLayer()
    orchestrator = Orchestrator(model_registry=registry, intelligence_layer=layer)

    luna_profile = layer._implementations.get("luna")
    assert luna_profile is not None
    assert luna_profile.execution_class == "REMOTE_MODEL"

    qwen_profile = layer._implementations.get("qwen3-8b")
    assert qwen_profile is not None
    assert qwen_profile.execution_class == "LOCAL_MODEL"


def test_frontier_executor_availability_interlock(tmp_path):
    registry = create_test_model_registry(tmp_path)
    layer = LocalIntelligenceLayer()
    
    # Frontier disabled
    disabled_frontier = DefaultFrontierExecutor(enabled=False)
    orchestrator = Orchestrator(
        model_registry=registry,
        intelligence_layer=layer,
        frontier_executor=disabled_frontier
    )
    orchestrator._reconcile_registries()
    luna_profile = layer._implementations.get("luna")
    assert luna_profile.availability is False

    # An enabled DefaultFrontierExecutor remains a local sentinel and cannot
    # make a remote model available.
    enabled_frontier = DefaultFrontierExecutor(enabled=True, available_models=["luna"])
    orchestrator.frontier_executor = enabled_frontier
    orchestrator._reconcile_registries()
    luna_profile = layer._implementations.get("luna")
    assert luna_profile.availability is False


def test_bijective_routing_class_mapping():
    assert WorkerManager._routing_class("DETERMINISTIC") == "DETERMINISTIC"
    assert WorkerManager._routing_class("LOCAL_MODEL") == "LOCAL_MODEL"
    assert WorkerManager._routing_class("REMOTE_MODEL") == "FRONTIER_MODEL"
    assert WorkerManager._routing_class("UNKNOWN") == "UNKNOWN"


def test_remote_model_worker_rejects_default_frontier_sentinel(tmp_path):
    frontier = DefaultFrontierExecutor(enabled=True, available_models=["luna"])
    worker_mgr = WorkerManager(workspace_manager=None, frontier_executor=frontier)
    
    selection = ExecutorSelection(
        executor_type=ExecutorType.REMOTE_MODEL,
        executor_id="frontier-executor",
        executor_version="1.0.0",
        model_id="luna",
        model_version="1.0.0",
        reason="Remote frontier selection",
        policy_version="v1.0",
        risk_class="high"
    )
    
    task = make_test_task("task-remote-001", "architecture.analysis")
    
    from runtime.execution.models import TaskExecutionContext
    context = TaskExecutionContext(
        execution_id="exec-remote-001",
        task_id=task.task_id,
        account_id=task.account_id,
        project_id=task.project_id,
        capability_id=task.capability_id,
        workspace_path="",
        environment={},
        allowed_tools=[],
        deadline=task.deadline,
        resource_limits={},
        network_policy="egress_only",
        write_policy="workspace_only",
        status=ExecutionStatus.QUEUED
    )
    
    worker = worker_mgr.create_worker(context, selection, task)
    assert worker.routing_class == "FRONTIER_MODEL"
    
    cap_def = CapabilityDefinition(
        capability_id="architecture.analysis",
        name="Arch Analysis",
        description="Analysis",
        version="1.0.0",
        risk_level="high",
        inference_required=True,
        deterministic_allowed=False,
        network_policy="egress_only",
        filesystem_policy="workspace_only",
        required_tools=[],
        max_runtime=600,
        max_output=10000,
        evidence_required=True,
        preferred_executor=ExecutorType.REMOTE_MODEL,
        fallback_executor=None,
        enabled=True
    )
    # Isolated WorkerManager test: inject an explicit test-only admission so
    # the assertion reaches the Frontier sentinel rather than a direct-route
    # denial. Runtime production wiring performs this in ExecutionManager.
    test_registry = CapabilityRegistry()
    test_registry.register(cap_def)
    worker_mgr.capability_registry = test_registry
    worker_mgr._admit_execution(context, task, cap_def, selection)

    worker_mgr.start_worker(worker.worker_id, context, task, cap_def)
    assert context.status == ExecutionStatus.FAILED
    assert context.failure_reason.name == "AUTHORIZATION_DENIED"
    assert "Authorized FrontierExecutor" in context.error_message


def test_capability_support_reconciliation(tmp_path):
    registry = create_test_model_registry(tmp_path)
    layer = LocalIntelligenceLayer()
    orchestrator = Orchestrator(model_registry=registry, intelligence_layer=layer)

    qwen = registry.get_model("qwen3-8b")
    qwen.capabilities_supported.append("new.capability")
    orchestrator._reconcile_registries()

    profile = layer._implementations.get("qwen3-8b")
    assert "new.capability" in profile.capability_ids


def test_certification_status_reconciliation(tmp_path):
    registry = create_test_model_registry(tmp_path)
    layer = LocalIntelligenceLayer()
    orchestrator = Orchestrator(model_registry=registry, intelligence_layer=layer)

    qwen = registry.get_model("qwen3-8b")
    setattr(qwen, "certification_status", CertificationStatus.REVOKED)
    orchestrator._reconcile_registries()

    profile = layer._implementations.get("qwen3-8b")
    assert profile.certification == CertificationStatus.REVOKED


def test_no_silent_fallback_during_drift(tmp_path):
    registry = create_test_model_registry(tmp_path)
    # Set all models unavailable
    for m in registry.list_models():
        registry.set_availability(m.model_id, False)

    frontier = DefaultFrontierExecutor(enabled=False)
    orchestrator = Orchestrator(
        model_registry=registry,
        frontier_executor=frontier
    )
    
    task = make_test_task("task-drift-001", "document.classify")
    
    plan = orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert plan.provenance.get("downgrade_prevented") is True
