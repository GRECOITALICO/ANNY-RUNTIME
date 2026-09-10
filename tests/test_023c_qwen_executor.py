import os
import time
import json
import psutil
import hashlib
import pytest
from datetime import datetime, timezone
from runtime.execution.interfaces import ContextPackage
from runtime.execution.capability import CapabilityRegistry
from runtime.execution.qwen_executor import QwenModelExecutor
from runtime.execution.deterministic_executor import ExecutorLimitsExceeded, ExecutorSecurityError

ARTIFACT_PATH = os.environ.get("QWEN_MODEL_PATH", "/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/models/Qwen3-8B-Q4_K_M.gguf")

@pytest.fixture(scope="module")
def executor():
    return QwenModelExecutor(artifact_path=ARTIFACT_PATH)

def create_context(text: str, network_policy="disabled", constraints=None):
    capability = CapabilityRegistry().get("document.classify")
    capability.network_policy = network_policy
    return ContextPackage(
        task=None,
        capability=capability,
        authorized_input={"text": text},
        allowed_tools=[],
        constraints=constraints or {"max_context": 32000, "max_output": 4000, "temperature": 0.0, "seed": 42},
        evidence_policy="required"
    )

def test_phase_15_ten_real_tasks(executor):
    documents = [
        "This is a public press release about our new product.",
        "Confidential financial projections for Q4.",
        "Internal cafeteria menu for next week.",
        "Restricted access logs for the production database.",
        "The weather today is sunny, public knowledge.",
        "Secret recipe for the new sauce.",
        "Employee directory for internal use only.",
        "Highly restricted cryptographic keys.",
        "Public announcement of a new CEO.",
        "Internal guidelines for requesting PTO."
    ]
    
    results = []
    for doc in documents:
        ctx = create_context(doc)
        res = executor.execute(ctx)
        assert res.status == "SUCCEEDED"
        assert "class" in res.result_data
        assert res.result_data["class"] in ["confidential", "public", "internal", "restricted"]
        results.append(res)
        
    assert len(results) == 10

def test_phase_17_reproducibility(executor):
    doc = "This document contains highly confidential merger plans."
    ctx = create_context(doc)
    
    res1 = executor.execute(ctx)
    res2 = executor.execute(ctx)
    res3 = executor.execute(ctx)
    
    c1 = res1.result_data["class"]
    c2 = res2.result_data["class"]
    c3 = res3.result_data["class"]
    
    assert c1 == c2 == c3

def test_phase_18_failure_network_denied(executor):
    ctx = create_context("Test doc", network_policy="allowed")
    with pytest.raises(ExecutorSecurityError, match="disabled network policy"):
        executor.execute(ctx)

def test_phase_18_failure_missing_artifact():
    bad_executor = QwenModelExecutor(artifact_path="/tmp/does_not_exist.gguf")
    ctx = create_context("Test doc")
    with pytest.raises(ExecutorSecurityError, match="ARTIFACT_MISSING"):
        bad_executor.execute(ctx)

def test_phase_18_failure_context_limit(executor):
    ctx = create_context("A" * 40000, constraints={"max_context": 100})
    with pytest.raises(ExecutorLimitsExceeded, match="Input exceeds max_context"):
        executor.execute(ctx)
