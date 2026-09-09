import pytest
from datetime import datetime, timezone
from runtime.execution.models import ModelState, Task, ModelDefinition
from runtime.execution.registry import ModelRegistry, ModelCapabilityBinding, HardwareProfile, ModelPerformanceProfile, EvaluationRecord
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.selector import ExecutorSelector
from runtime.execution.manager import ExecutionManager
from runtime.workspace.ephemeral import EphemeralWorkspaceManager

def test_model_registry_initialization():
    registry = ModelRegistry()
    models = registry.list_models()
    assert len(models) == 2
    assert any(m.model_id == "qwen3-8b" for m in models)
    assert any(m.model_id == "luna" for m in models)

def test_model_state_availability():
    registry = ModelRegistry()
    # Default is INSTALL_REQUIRED for qwen3-8b
    assert registry.is_available("qwen3-8b") is False
    
    # Update to AVAILABLE
    registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    assert registry.is_available("qwen3-8b") is True
    
    # Check available model luna
    assert registry.is_available("luna") is True

def test_capability_binding_retrieval():
    registry = ModelRegistry()
    
    registry.add_binding(ModelCapabilityBinding(
        model_id="qwen3-8b", 
        capability_id="filesystem.inspect", 
        authorization="granted", 
        quality_profile="standard",
        risk_limit="low",
        preferred=True, 
        fallback=False,
        reason="test"
    ))
    
    bindings = registry.get_bindings_for_capability("filesystem.inspect")
    assert len(bindings) == 1
    assert bindings[0].model_id == "qwen3-8b"
    assert bindings[0].preferred is True

def test_hardware_and_performance_profiles():
    registry = ModelRegistry()
    
    # Test HardwareProfile (singleton for the local runner)
    hw = registry.get_hardware_profile()
    assert hw is not None
    assert hw.cpu == "UNKNOWN"
    
    # Test Performance Profile
    perf = registry.get_performance_profile("qwen3-8b")
    assert perf is not None
    assert perf.executions == 0
    
    perf_luna = registry.get_performance_profile("luna")
    assert perf_luna is not None
    assert perf_luna.executions == 0

def test_selector_fallback_and_availability():
    registry = ModelRegistry()
    selector = ExecutorSelector(registry)
    policy = RuntimePolicy()
    policy.allow_llm = True
    
    registry.add_binding(ModelCapabilityBinding("luna", "test.cap", "granted", "standard", "low", True, False, "test"))
    registry.add_binding(ModelCapabilityBinding("qwen3-8b", "test.cap", "granted", "standard", "low", False, True, "test"))
    
    cap = CapabilityDefinition("test.cap", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t1", "test.cap", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    # luna is available, should take precedence
    selection = selector.select(task, cap, policy)
    assert selection.model_id == "luna"
    
    # make luna unavailable, make qwen available
    registry.get_model("luna").status = ModelState.UNAVAILABLE
    registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    selection = selector.select(task, cap, policy)
    assert selection.model_id == "qwen3-8b"

def test_selector_forbidden_binding():
    registry = ModelRegistry()
    selector = ExecutorSelector(registry)
    policy = RuntimePolicy()
    policy.allow_llm = True
    
    registry.add_binding(ModelCapabilityBinding("qwen3-8b", "test.cap2", "forbidden", "none", "none", True, False, "test"))
    registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    
    cap = CapabilityDefinition("test.cap2", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t2", "test.cap2", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    with pytest.raises(ValueError, match="No available models found"):
        selector.select(task, cap, policy)

def test_execution_manager_reproducibility_fields():
    ws_mgr = EphemeralWorkspaceManager("/tmp/anny-workspaces-registry-test")
    manager = ExecutionManager(ws_mgr)
    
    manager.policy.allow_llm = True
    manager.model_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    manager.model_registry.add_binding(ModelCapabilityBinding("qwen3-8b", "schema.validate", "granted", "standard", "low", True, False, "test"))
    
    cap = manager.registry.get("schema.validate")
    cap.inference_required = True
    
    task = Task("task-123", "schema.validate", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    context = manager.submit_task(task)
    
    assert context.model_id == "qwen3-8b"
    assert context.executor_type == "LOCAL_MODEL"
    assert context.executor_id == "worker-compatible-local_model"
    assert context.executor_version == "1.0.0"
    assert context.model_version == "3.0"
    assert context.policy_version == "1.0.0"
