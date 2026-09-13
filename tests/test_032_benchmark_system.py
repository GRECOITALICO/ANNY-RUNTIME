"""Tests for ANNY Capability Benchmark System (MISSION-032)."""
import pytest
from datetime import datetime, timezone

from runtime.intelligence.taxonomy import is_deterministic, requires_benchmark
from runtime.intelligence.models import BenchmarkCase, BenchmarkScorecard, CertificationStatus
from runtime.intelligence.grading import GradingEngine
from runtime.intelligence.benchmark_runner import BenchmarkRunner, InferenceBackend
from runtime.intelligence.benchmark_dataset import get_partition

class MockBackend(InferenceBackend):
    @property
    def implementation_id(self) -> str: return "mock_model_v1"
    
    @property
    def implementation_revision(self) -> str: return "rev123"
    
    def run(self, capability_id: str, input_data: dict) -> str:
        # Pass summarization, fail others
        if capability_id == "text.summarization":
            return "This is a good summary."
        return "I don't know."

def test_taxonomy():
    assert is_deterministic("filesystem.read")
    assert not requires_benchmark("filesystem.read")
    assert requires_benchmark("text.summarization")
    assert not is_deterministic("text.summarization")

def test_grading_engine():
    engine = GradingEngine()
    
    # Exact match
    res = engine.grade("exact_match", "Hello World", "hello world")
    assert res.passed
    assert res.score == 1.0
    
    # Structured match
    res = engine.grade("structured_match", '{"a": 1, "b": 2}', '{"a": 1}')
    assert res.passed
    
    # Semantic match
    res = engine.grade("semantic_grading", "The quick brown fox", "quick brown fox jumps")
    assert res.score > 0.4
    
    # Task success
    res = engine.grade("task_success", '{"tool": "x", "args": {}}', '{"tool": "x"}')
    assert res.passed

def test_benchmark_runner():
    backend = MockBackend()
    runner = BenchmarkRunner(backend=backend)
    
    cases = [
        BenchmarkCase(benchmark_id="sum1", capability_id="text.summarization", input={"text": "Long text..."}, expected_output="This is a good summary.", grading_method="semantic_grading", difficulty="easy", dataset_partition="TRAIN", version="v1")
    ]
    
    results, failures = runner.run_cases(cases, runs_per_case=1)
    assert len(failures) == 0
    assert len(results) == 1
    assert results[0].grading.score > 0.5
    
    scorecard = runner.build_scorecard("text.summarization", results)
    assert scorecard.certification_status == CertificationStatus.CERTIFIED
    assert scorecard.score > 0.5
