import pytest
import os
import json
import tempfile
from datetime import datetime, timezone
from runtime.execution.models import ModelState, Task, ModelDefinition
from runtime.execution.registry import ModelRegistry, ModelCapabilityBinding, HardwareProfile, ModelPerformanceProfile, EvaluationRecord
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.selector import ExecutorSelector
from runtime.execution.manager import ExecutionManager
from runtime.workspace.ephemeral import EphemeralWorkspaceManager

@pytest.fixture
def clean_registry():
    return ModelRegistry()

def test_01_registration(clean_registry):
    models = clean_registry.list_models()
    assert len(models) == 2
    assert any(m.model_id == "qwen3-8b" for m in models)
    assert any(m.model_id == "luna" for m in models)

def test_02_duplicate_rejection(clean_registry):
    with pytest.raises(ValueError, match="already registered"):
        clean_registry.register_model(ModelDefinition(
            model_id="qwen3-8b", display_name="", provider="", executor_type="", version="",
            status=ModelState.AVAILABLE, capabilities_supported=[], capabilities_forbidden=[],
            hardware_requirements={}, memory_requirements={}, context_window=0, quantization="",
            artifact_uri="", runtime_interface="", max_concurrency=0, max_runtime=0,
            max_input_size=0, max_output_size=0, network_policy="", evidence_policy=""
        ))

def test_03_state_transitions(clean_registry):
    model = clean_registry.get_model("qwen3-8b")
    assert model.status == ModelState.INSTALL_REQUIRED
    model.status = ModelState.AVAILABLE
    assert clean_registry.is_available("qwen3-8b") is True

def test_04_capability_binding(clean_registry):
    bindings = clean_registry.get_bindings_for_capability("document.classify")
    assert any(b.model_id == "qwen3-8b" for b in bindings)

def test_05_forbidden_binding(clean_registry):
    bindings = clean_registry.get_bindings_for_capability("architecture.analysis")
    qwen_bind = next(b for b in bindings if b.model_id == "qwen3-8b")
    assert qwen_bind.authorization == "forbidden"
    
    selector = ExecutorSelector(clean_registry)
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    cap = CapabilityDefinition("architecture.analysis", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t2", "architecture.analysis", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    # ensure luna isn't available to force it to look at qwen3
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    with pytest.raises(ValueError, match="No available models found"):
        selector.select(task, cap, policy)

def test_06_preferred_binding(clean_registry):
    selector = ExecutorSelector(clean_registry)
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    
    cap = CapabilityDefinition("architecture.analysis", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t3", "architecture.analysis", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    selection = selector.select(task, cap, policy)
    assert selection.model_id == "luna"

def test_07_fallback(clean_registry):
    selector = ExecutorSelector(clean_registry)
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    
    # For architecture.analysis, qwen is forbidden. We need a capability where qwen is fallback
    cap = CapabilityDefinition("document.classify", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t4", "document.classify", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    selection = selector.select(task, cap, policy)
    assert selection.model_id == "qwen3-8b"

def test_08_unknown_hardware(clean_registry):
    hw = clean_registry.get_hardware_profile()
    assert hw.cpu == "UNKNOWN"

def test_09_availability(clean_registry):
    assert clean_registry.is_available("luna") is True

def test_10_unavailable_model(clean_registry):
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    assert clean_registry.is_available("luna") is False

def test_11_disabled_model(clean_registry):
    clean_registry.get_model("luna").status = ModelState.DISABLED
    assert clean_registry.is_available("luna") is False

def test_12_deterministic_selection(clean_registry):
    selector = ExecutorSelector(clean_registry)
    policy = RuntimePolicy()
    cap = CapabilityDefinition("non_llm.task", "test", "test", "1.0", "low", False, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t5", "non_llm.task", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    selection = selector.select(task, cap, policy)
    assert selection.executor_type == ExecutorType.DETERMINISTIC

def test_13_llm_capability_without_model(clean_registry):
    selector = ExecutorSelector(clean_registry)
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    cap = CapabilityDefinition("nonexistent.task", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t6", "nonexistent.task", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    with pytest.raises(ValueError, match="No models bound to capability"):
        selector.select(task, cap, policy)

def test_14_authority_boundary():
    from runtime.execution.selector import ExecutorSelection
    selection = ExecutorSelection(ExecutorType.LOCAL_MODEL, "worker", "1.0", "luna", "1.0", "test", "1.0", "low")
    assert selection.model_id == "luna"

def test_15_performance_profile(clean_registry):
    perf = clean_registry.get_performance_profile("luna")
    assert perf.executions == 0

def test_16_evaluation_record(clean_registry):
    clean_registry._evaluations.append(EvaluationRecord("ev1", "luna", "test", "exe1", 1.0, "auto", "sys", datetime.now(timezone.utc), "ref1"))
    assert len(clean_registry._evaluations) == 1

def test_17_control_plane_list():
    from runtime.admin.routes import AdminRouter
    router = AdminRouter({})
    assert '/models' in router._get_routes

def test_18_control_plane_detail():
    from runtime.admin.routes import AdminRouter
    router = AdminRouter({})
    # Detail is handled dynamically, let's verify handle_model_detail exists
    assert hasattr(router, 'handle_model_detail')

def test_19_reproducibility_metadata():
    ws_mgr = EphemeralWorkspaceManager("/tmp/anny-workspaces-registry-test-2")
    manager = ExecutionManager(ws_mgr)
    manager.policy.allow_llm = True
    manager.model_registry.add_binding(ModelCapabilityBinding("luna", "schema.validate", "granted", "standard", "low", True, False, "test"))
    
    cap = manager.registry.get("schema.validate")
    cap.inference_required = True
    task = Task("task-123", "schema.validate", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    context = manager.submit_task(task)
    assert context.model_version == "1.0"
    assert context.executor_version == "1.0.0"

def test_20_schema_validation():
    # Tested by ensuring loading an invalid version raises an error via internal method
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b'{"version": "2.0"}')
        path = f.name
    
    try:
        reg = ModelRegistry()
        reg.storage_path = path
        with pytest.raises(ValueError, match="Unsupported registry schema version"):
            reg._load_from_disk()
    finally:
        os.unlink(path)

def test_21_persistence_reload():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        path = f.name
        
    try:
        reg1 = ModelRegistry(storage_path=path)
        reg1.get_model("qwen3-8b").status = ModelState.AVAILABLE
        reg1._save_to_disk()
        
        reg2 = ModelRegistry(storage_path=path)
        assert reg2.is_available("qwen3-8b") is True
    finally:
        os.unlink(path)

def test_22_crash_recovery():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b'{"corrupted": json')
        path = f.name
        
    try:
        # Should recover by falling back to initial state
        reg = ModelRegistry(storage_path=path)
        assert len(reg.list_models()) == 2
        assert reg.is_available("luna") is True
    finally:
        os.unlink(path)

def test_23_model_replacement_without_task_mutation(clean_registry):
    # A task requests capability 'doc.class'. Model A handles it, then Model B handles it. The task doesn't change.
    cap = CapabilityDefinition("doc.class", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t7", "doc.class", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    clean_registry.add_binding(ModelCapabilityBinding("qwen3-8b", "doc.class", "granted", "standard", "low", True, False, "test"))
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    
    selector = ExecutorSelector(clean_registry)
    policy = RuntimePolicy()
    policy.allow_llm = True
    
    sel1 = selector.select(task, cap, policy)
    assert sel1.model_id == "qwen3-8b"
    
    clean_registry.get_model("qwen3-8b").status = ModelState.UNAVAILABLE
    clean_registry.add_binding(ModelCapabilityBinding("luna", "doc.class", "granted", "standard", "low", True, False, "test"))
    
    sel2 = selector.select(task, cap, policy)
    assert sel2.model_id == "luna"
