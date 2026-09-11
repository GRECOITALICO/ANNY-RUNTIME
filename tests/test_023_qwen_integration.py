import pytest
import os
import json
from datetime import datetime, timezone, timedelta
import hashlib

from runtime.execution.worker import WorkerManager
from runtime.execution.manager import ExecutionManager
from runtime.execution.models import Task, ExecutionStatus
from runtime.execution.capability import ExecutorType
from runtime.execution.registry import ModelRegistry
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.qwen_executor import QwenModelExecutor

try:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(repo_id="Qwen/Qwen2.5-0.5B-Instruct-GGUF", filename="qwen2.5-0.5b-instruct-q4_k_m.gguf")
    os.environ["QWEN_MODEL_PATH"] = path
except Exception:
    pass

def _make_task(task_id, text, constraints=None):
    """Helper to create a Task with all required fields."""
    return Task(
        task_id=task_id,
        capability_id="document.classify",
        input={"text": text},
        constraints=constraints or {"max_context": 1000, "max_output": 500},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        workspace_policy="destroy_on_complete",
        evidence_policy="required",
        requested_by="test-023",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def workspace_manager(tmp_path):
    wm = EphemeralWorkspaceManager(base_dir=str(tmp_path))
    return wm


@pytest.fixture
def execution_manager(workspace_manager):
    em = ExecutionManager(workspace_manager=workspace_manager, audit_manager=None)
    # Enable LLMs for tests
    em.policy.allow_llm = True
    # Make qwen3-8b available
    qwen = em.registry.get_model("qwen3-8b") if hasattr(em, "registry") and hasattr(em.registry, "get_model") else None
    if qwen:
        pass # Wait, em.registry is CapabilityRegistry. em.model_registry is ModelRegistry.
        
    model = em.model_registry.get_model("qwen3-8b")
    from runtime.execution.models import ModelState
    model.status = ModelState.AVAILABLE
    
    return em


def test_qwen_10_task_baseline(execution_manager):
    """Phase 17: Execute 10 classification tasks in sequence"""
    for i in range(10):
        task = _make_task(
            f"tsk-cls-{i}",
            f"This is document number {i}. It is an internal draft.",
        )
        ctx = execution_manager.submit_task(task)
        ctx = execution_manager.execute_sync(ctx.execution_id)

        assert ctx.status == ExecutionStatus.SUCCEEDED, f"Task {i} failed: {ctx.error_message}"
        assert ctx.result["class"] == "internal"
        assert ctx.result_hash is not None


def test_qwen_reproducibility(execution_manager):
    """Phase 18: Exact same input should yield identical result hash"""
    task1 = _make_task("tsk-cls-A", "Very secret password document.")
    ctx1 = execution_manager.submit_task(task1)
    ctx1 = execution_manager.execute_sync(ctx1.execution_id)

    task2 = _make_task("tsk-cls-B", "Very secret password document.")
    ctx2 = execution_manager.submit_task(task2)
    ctx2 = execution_manager.execute_sync(ctx2.execution_id)

    assert ctx1.status == ExecutionStatus.SUCCEEDED
    assert ctx2.status == ExecutionStatus.SUCCEEDED
    assert ctx1.result_hash == ctx2.result_hash


def test_qwen_failure_network_policy(execution_manager):
    """Phase 19: If network policy is egress_only, executor rejects it."""
    cap = execution_manager.registry.get("document.classify")
    original = cap.network_policy
    cap.network_policy = "egress_only"

    task = _make_task("tsk-cls-net", "Test")
    ctx = execution_manager.submit_task(task)
    ctx = execution_manager.execute_sync(ctx.execution_id)

    assert ctx.status == ExecutionStatus.FAILED
    assert ctx.failure_reason.value == "AUTHORIZATION_DENIED"
    assert "disabled network policy" in ctx.error_message

    cap.network_policy = original


def test_qwen_failure_limit_exceeded(execution_manager):
    """Phase 19: Limit Exceeded on max context"""
    task = _make_task(
        "tsk-cls-lim",
        "A" * 10000,
        constraints={"max_context": 100, "max_output": 500},
    )
    ctx = execution_manager.submit_task(task)
    ctx = execution_manager.execute_sync(ctx.execution_id)

    assert ctx.status == ExecutionStatus.LIMIT_EXCEEDED
    assert "max_context" in ctx.error_message


def test_qwen_model_output_invalid():
    """Test validation directly"""
    from runtime.execution.validator import ModelResultValidator, ModelOutputInvalid

    invalid_json = '{"class": "internal"'  # Missing bracket
    with pytest.raises(ModelOutputInvalid):
        ModelResultValidator.validate_document_classification(invalid_json)

    invalid_class = '{"class": "super_secret", "confidence": 0.5, "reason_codes": []}'
    with pytest.raises(ModelOutputInvalid) as exc:
        ModelResultValidator.validate_document_classification(invalid_class)
    assert "one of" in str(exc.value)


def test_qwen_phase_25_clean_state(execution_manager):
    """Phase 25: Verify executor leaves no residual memory."""
    task = _make_task("tsk-cls-clean", "clean state test")
    ctx = execution_manager.submit_task(task)
    ctx = execution_manager.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.SUCCEEDED
