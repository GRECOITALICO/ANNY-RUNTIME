import json
import pytest
from typing import Dict, Any, Optional

from runtime.execution.models import Task, ModelDefinition, ModelState
from runtime.execution.capability import (
    CapabilityRegistry,
    CapabilityDefinition,
    ExecutorType,
)
from runtime.execution.policy import RuntimePolicy
from runtime.execution.registry import ModelRegistry
from runtime.intelligence.layer import LocalIntelligenceLayer
from runtime.intelligence.models import (
    ImplementationProfile,
    CertificationStatus,
)
from runtime.orchestration.plan import ExecutionPlan, RoutingClass
from runtime.orchestration.frontier import DefaultFrontierExecutor
from runtime.orchestration.kernel import Orchestrator

class MockTask(Task):
    def __init__(self, task_id: str, type: str, allow_frontier: bool = False, constraints: dict = None):
        super().__init__(
            task_id=task_id,
            capability_id=type,
            account_id="acc",
            project_id="proj",
            input={},
            constraints=constraints or {},
            deadline=None,
            workspace_policy="",
            evidence_policy="",
            requested_by="test",
            created_at=None,
        )
        self.type = type
        self.allow_frontier = allow_frontier

def _make_model_def(model_id: str, name: str, capabilities: list, status=ModelState.AVAILABLE) -> ModelDefinition:
    return ModelDefinition(
        model_id=model_id,
        display_name=name,
        provider="local",
        executor_type="LOCAL_MODEL",
        version="1.0",
        status=status,
        capabilities_supported=capabilities,
        capabilities_forbidden=[],
        hardware_requirements={},
        memory_requirements={},
        context_window=32000,
        quantization="int8",
        artifact_uri=f"local://models/{model_id}",
        artifact_sha256="a" * 64,
        runtime_interface="llama.cpp",
        max_concurrency=1,
        max_runtime=300,
        max_input_size=20000,
        max_output_size=4000,
        network_policy="none",
        evidence_policy="required",
    )

def _make_impl_profile(impl_id: str, cert_status=CertificationStatus.CERTIFIED, gpu_present=True) -> ImplementationProfile:
    return ImplementationProfile(
        implementation_id=impl_id,
        capability_ids=["document.classify"],
        quality_profile="high",
        resource_profile={"gpu_present": gpu_present},
        latency_profile={"p50": 100},
        cost_profile={"token_cost": 0.0},
        availability=True,
        certification=cert_status,
        artifact_references=[],
        adapter_references=[],
    )


@pytest.fixture
def base_orchestrator():
    cap_reg = CapabilityRegistry()
    model_reg = ModelRegistry()
    intel_layer = LocalIntelligenceLayer()
    frontier_exec = DefaultFrontierExecutor(enabled=True)
    return Orchestrator(
        capability_registry=cap_reg,
        model_registry=model_reg,
        intelligence_layer=intel_layer,
        frontier_executor=frontier_exec,
    )


# 1. Deterministic Selection
def test_deterministic_selection(base_orchestrator):
    task = MockTask(task_id="t-001", type="filesystem.inspect")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.DETERMINISTIC
    assert plan.executor_type == ExecutorType.DETERMINISTIC.value
    assert plan.model_id is None


# 2. Local Model Selection
def test_local_model_selection(base_orchestrator):
    base_orchestrator.model_registry.register(
        _make_model_def("qwen-2.5-7b", "Qwen 2.5 7B", ["document.classify"])
    )
    from datetime import datetime
    from runtime.intelligence.models import BenchmarkResult
    base_orchestrator.intelligence_layer.add_benchmark_result(
        BenchmarkResult(
            benchmark_id="b-1",
            implementation_id="qwen-2.5-7b",
            capability_id="document.classify",
            dataset_version="1.0",
            score=0.95,
            confidence=0.90,
            latency=100.0,
            resource_usage={},
            timestamp=datetime.now(),
            certification_status=CertificationStatus.CERTIFIED,
        )
    )
    task = MockTask(task_id="t-002", type="document.classify")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    print(f"REASON: {plan.decision_reason}")
    assert plan.routing_class == RoutingClass.LOCAL_MODEL
    assert plan.model_id == "qwen-2.5-7b"


# 3. Frontier fallback is blocked without an injected physical executor
def test_frontier_fallback_is_blocked_without_physical_executor(base_orchestrator):
    for m in base_orchestrator.model_registry.list_models():
        base_orchestrator.model_registry.unregister(m.model_id)

    task = MockTask(task_id="t-003", type="document.classify", allow_frontier=True)
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "No valid executor" in plan.decision_reason


# 4. Blocked When No Executor Exists
def test_blocked_when_no_executor_exists(base_orchestrator):
    for m in base_orchestrator.model_registry.list_models():
        base_orchestrator.model_registry.unregister(m.model_id)
    base_orchestrator.frontier_executor = DefaultFrontierExecutor(enabled=False)

    task = MockTask(task_id="t-004", type="document.classify", allow_frontier=False)
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "No valid executor" in plan.decision_reason


# 5. No Silent Deterministic Downgrade Guarantee
def test_no_silent_deterministic_downgrade(base_orchestrator):
    for m in base_orchestrator.model_registry.list_models():
        base_orchestrator.model_registry.unregister(m.model_id)
    base_orchestrator.frontier_executor = DefaultFrontierExecutor(enabled=False)

    task = MockTask(task_id="t-005", type="document.classify")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class != RoutingClass.DETERMINISTIC
    assert plan.routing_class == RoutingClass.BLOCKED
    assert plan.provenance.get("downgrade_prevented") is True


# 6. Disabled Capability
def test_disabled_capability(base_orchestrator):
    cap = base_orchestrator.capability_registry.get("filesystem.inspect")
    cap.enabled = False
    task = MockTask(task_id="t-006", type="filesystem.inspect")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "disabled" in plan.decision_reason


# 7. Unknown Capability
def test_unknown_capability(base_orchestrator):
    task = MockTask(task_id="t-007", type="nonexistent.capability")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "Unknown capability" in plan.decision_reason


# 8. Policy Denial
def test_policy_denial(base_orchestrator):
    policy = RuntimePolicy(allow_llm=False)
    task = MockTask(task_id="t-008", type="document.classify")
    plan = base_orchestrator.plan_task(task, policy=policy)
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "Policy denial" in plan.decision_reason


# 9. Stale Certification
def test_stale_certification(base_orchestrator):
    profile = _make_impl_profile("stale-model-v1", cert_status=CertificationStatus.STALE)
    base_orchestrator.intelligence_layer.register_implementation(profile)
    base_orchestrator.model_registry.register(
        _make_model_def("stale-model-v1", "Stale Model", ["document.classify"])
    )
    base_orchestrator.frontier_executor = DefaultFrontierExecutor(enabled=False)

    task = MockTask(task_id="t-009", type="document.classify")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "Certification status invalid" in str(plan.provenance.get("rejection_reasons"))


# 10. Revoked Certification
def test_revoked_certification(base_orchestrator):
    profile = _make_impl_profile("revoked-model-v1", cert_status=CertificationStatus.REVOKED)
    base_orchestrator.intelligence_layer.register_implementation(profile)
    base_orchestrator.model_registry.register(
        _make_model_def("revoked-model-v1", "Revoked Model", ["document.classify"])
    )
    base_orchestrator.frontier_executor = DefaultFrontierExecutor(enabled=False)

    task = MockTask(task_id="t-010", type="document.classify")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "Certification status invalid" in str(plan.provenance.get("rejection_reasons"))


# 11. Resource Incompatibility
def test_resource_incompatibility(base_orchestrator):
    profile = _make_impl_profile("cpu-only-model", gpu_present=False)
    base_orchestrator.intelligence_layer.register_implementation(profile)
    from runtime.intelligence.models import BenchmarkResult
    from datetime import datetime, timezone
    base_orchestrator.intelligence_layer.add_benchmark_result(BenchmarkResult(
        benchmark_id="b1", implementation_id="cpu-only-model", capability_id="document.classify",
        dataset_version="1", score=0.9, confidence=0.9, latency=10, resource_usage={},
        timestamp=datetime.now(timezone.utc), certification_status=CertificationStatus.CERTIFIED
    ))
    base_orchestrator.model_registry.register(
        _make_model_def("cpu-only-model", "CPU Model", ["document.classify"])
    )
    base_orchestrator.frontier_executor = DefaultFrontierExecutor(enabled=False)

    task = MockTask(task_id="t-011", type="document.classify", constraints={"requires_gpu": True})
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "missing GPU" in str(plan.provenance.get("rejection_reasons"))


# 12. Capability / Version Provenance
def test_capability_version_provenance(base_orchestrator):
    task = MockTask(task_id="t-012", type="filesystem.inspect")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert plan.provenance["capability_version"] == "1.1.0"
    assert plan.provenance["requested_capability"] == "filesystem.inspect"
    assert plan.provenance["policy_applied"] == "1.0.0"


# 13. ExecutionPlan Serialization
def test_execution_plan_serialization(base_orchestrator):
    task = MockTask(task_id="t-013", type="filesystem.inspect")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    d = plan.to_dict()
    assert isinstance(d, dict)
    assert d["routing_class"] == "DETERMINISTIC"
    json_str = json.dumps(d)
    assert "filesystem.inspect" in json_str


# 14. Secret-Free ExecutionPlan
def test_secret_free_execution_plan(base_orchestrator):
    task = MockTask(task_id="t-014", type="filesystem.inspect")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    plan.provenance["secrets"] = "sk-123456789"
    plan.provenance["api_key"] = "super-secret"
    d = plan.to_dict()
    assert "secrets" not in d["provenance"]
    assert "api_key" not in d["provenance"]


# 15. Telemetry of Routing Decision
def test_telemetry_of_routing_decision(base_orchestrator):
    task = MockTask(task_id="t-015", type="filesystem.inspect")
    plan = base_orchestrator.plan_task(task, policy=RuntimePolicy(allow_llm=True))
    assert "decision_reason" in plan.to_dict()
    assert len(plan.decision_reason) > 0


# 16. Registry Reconciliation
def test_registry_reconciliation(base_orchestrator):
    base_orchestrator.model_registry.register(
        _make_model_def("reconciled-model-v1", "Reconciled Model", ["document.classify"])
    )
    base_orchestrator._reconcile_registries()
    assert "reconciled-model-v1" in base_orchestrator.intelligence_layer._implementations


# 17. Model Availability Reconciliation
def test_model_availability_reconciliation(base_orchestrator):
    base_orchestrator.model_registry.register(
        _make_model_def("avail-model-v1", "Avail Model", ["document.classify"])
    )
    base_orchestrator.model_registry.set_availability("avail-model-v1", False)
    base_orchestrator.frontier_executor = DefaultFrontierExecutor(enabled=False)

    task = MockTask(task_id="t-017", type="document.classify")
    plan = base_orchestrator.plan_task(task)
    assert plan.routing_class == RoutingClass.BLOCKED


# 18. Frontier Executor Boundary
def test_frontier_executor_boundary(base_orchestrator):
    frontier = DefaultFrontierExecutor(enabled=True)
    assert frontier.is_available("frontier-gpt4") is False
    plan = ExecutionPlan(
        task_id="t-018",
        capability_id="document.classify",
        capability_version="1.1.0",
        routing_class=RoutingClass.FRONTIER_MODEL,
        executor_type=ExecutorType.REMOTE_MODEL.value,
        executor_id="frontier-executor",
        model_id="frontier-gpt4",
    )
    task = MockTask(task_id="t-018", type="document.classify")
    with pytest.raises(RuntimeError, match="not a physical executor"):
        frontier.execute_plan(task, plan)
