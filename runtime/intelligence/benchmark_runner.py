"""BenchmarkRunner for ANNY Capability Benchmark System (MISSION-032).

Executes benchmark cases against a pluggable InferenceBackend.
Never receives or exposes physical model names.
"""
import time
import math
import logging
import platform
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from runtime.intelligence.models import (
    BenchmarkCase, BenchmarkScorecard, CertificationStatus,
    FailureRecord, HardwareProfile, RepeatabilityStats,
)
from runtime.intelligence.grading import GradingEngine, GradingResult

logger = logging.getLogger(__name__)

# Failure types (Phase 26)
FAILURE_BENCHMARK = "benchmark_failure"
FAILURE_IMPLEMENTATION = "implementation_failure"
FAILURE_RESOURCE = "resource_failure"
FAILURE_TIMEOUT = "timeout"
FAILURE_ENVIRONMENTAL = "environmental"
FAILURE_POLICY_DENIED = "policy_denied"
FAILURE_INVALID_CASE = "invalid_case"
FAILURE_GRADING = "grading_failure"


class InferenceBackend(ABC):
    """Abstract backend: ANNY never sees the implementation behind this."""

    @abstractmethod
    def run(self, capability_id: str, input_data: Any) -> Any:
        ...

    @property
    @abstractmethod
    def implementation_id(self) -> str:
        ...

    @property
    @abstractmethod
    def implementation_revision(self) -> str:
        ...

    @property
    def adapter_revision(self) -> Optional[str]:
        return None


def _percentile(sorted_vals: List[float], pct: float) -> float:
    """Compute percentile from pre-sorted list (Phase 13)."""
    if not sorted_vals:
        return 0.0
    idx = (pct / 100.0) * (len(sorted_vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] * (1 - (idx - lo)) + sorted_vals[hi] * (idx - lo)


def _repeatability_stats(scores: List[float]) -> RepeatabilityStats:
    """Phase 25: Compute mean, variance, stddev, best, worst."""
    n = len(scores)
    if n == 0:
        return RepeatabilityStats(run_count=0, mean=0.0, variance=0.0, stddev=0.0,
                                  best=0.0, worst=0.0, scores=[])
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    return RepeatabilityStats(
        run_count=n, mean=round(mean, 4), variance=round(variance, 6),
        stddev=round(math.sqrt(variance), 4), best=round(max(scores), 4),
        worst=round(min(scores), 4), scores=[round(s, 4) for s in scores]
    )


def capture_hardware_profile() -> HardwareProfile:
    """Phase 12: Capture current hardware environment."""
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
        cpu_cores = psutil.cpu_count(logical=False) or os.cpu_count() or 1
    except ImportError:
        ram_gb = 0.0
        cpu_cores = os.cpu_count() or 1

    cpu_model = platform.processor() or platform.machine() or "unknown"
    gpu_model, vram_gb = "none", 0.0
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split(",")
            gpu_model = parts[0].strip()
            vram_gb = round(int(parts[1].strip()) / 1024, 2) if len(parts) > 1 else 0.0
    except Exception:
        pass

    return HardwareProfile(
        cpu_model=cpu_model, cpu_cores=cpu_cores, ram_gb=ram_gb,
        gpu_model=gpu_model, vram_gb=vram_gb,
        runtime_env=f"Python {platform.python_version()}",
        os_info=f"{platform.system()} {platform.release()}",
    )


@dataclass
class RunResult:
    case: BenchmarkCase
    grading: GradingResult
    latency_s: float
    failure: Optional[FailureRecord] = None


class BenchmarkRunner:
    """Executes benchmark cases against an InferenceBackend (Phases 9, 13, 22-26)."""

    BENCHMARK_VERSION = "v1.0.0"
    DEFAULT_RUNS = 3
    CERTIFICATION_THRESHOLD = 0.80

    def __init__(self, backend: InferenceBackend,
                 telemetry_callback: Optional[Callable[[str, Dict], None]] = None,
                 timeout_s: float = 30.0):
        self.backend = backend
        self.telemetry_cb = telemetry_callback or (lambda e, d: None)
        self.timeout_s = timeout_s
        self.grader = GradingEngine()
        self.hardware = capture_hardware_profile()

    def run_cases(self, cases: List[BenchmarkCase], runs_per_case: int = 1
                  ) -> Tuple[List[RunResult], List[FailureRecord]]:
        results: List[RunResult] = []
        failures: List[FailureRecord] = []
        self.telemetry_cb("capability.benchmark_started", {
            "implementation_id": self.backend.implementation_id,
            "case_count": len(cases), "runs_per_case": runs_per_case,
            "benchmark_version": self.BENCHMARK_VERSION,
        })
        for case in cases:
            for _ in range(runs_per_case):
                rr, failure = self._run_single(case)
                if failure:
                    failures.append(failure)
                if rr:
                    results.append(rr)
        event = "capability.benchmark_completed" if not failures else "capability.benchmark_failed"
        self.telemetry_cb(event, {
            "implementation_id": self.backend.implementation_id,
            "results": len(results), "failures": len(failures),
        })
        return results, failures

    def build_scorecard(self, capability_id: str, results: List[RunResult],
                        dataset_version: str = "v1.0.0") -> BenchmarkScorecard:
        """Phase 11: Build scorecard from execution results."""
        cap_results = [r for r in results if r.case.capability_id == capability_id]
        scores = [r.grading.score for r in cap_results]
        confs = [r.grading.confidence for r in cap_results]
        latencies = sorted(r.latency_s for r in cap_results)
        stats = _repeatability_stats(scores)
        mean_score = stats.mean if scores else 0.0
        mean_conf = (sum(confs) / len(confs)) if confs else 0.0
        cert = (CertificationStatus.CERTIFIED if mean_score >= self.CERTIFICATION_THRESHOLD
                else CertificationStatus.VALID)
        sc = BenchmarkScorecard(
            scorecard_id=f"{capability_id}_{self.backend.implementation_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
            capability_id=capability_id,
            implementation_id=self.backend.implementation_id,
            implementation_revision=self.backend.implementation_revision,
            benchmark_version=self.BENCHMARK_VERSION,
            dataset_version=dataset_version,
            score=round(mean_score, 4), confidence=round(mean_conf, 4),
            latency_p50=round(_percentile(latencies, 50), 4),
            latency_p95=round(_percentile(latencies, 95), 4),
            latency_p99=round(_percentile(latencies, 99), 4),
            resource_usage={"ram_gb": self.hardware.ram_gb},
            certification_status=cert,
            hardware_profile=self.hardware.to_dict(),
            adapter_revision=self.backend.adapter_revision,
            created_at=datetime.now(timezone.utc),
        )
        if cert == CertificationStatus.CERTIFIED:
            self.telemetry_cb("capability.certified", {
                "capability_id": capability_id,
                "implementation_id": self.backend.implementation_id,
                "score": mean_score, "confidence": mean_conf,
                "benchmark_version": self.BENCHMARK_VERSION,
            })
        return sc

    def run_repeatability(self, cases: List[BenchmarkCase], capability_id: str,
                          runs: int = DEFAULT_RUNS) -> RepeatabilityStats:
        """Phase 25: Run N times and compute statistics."""
        all_scores: List[float] = []
        cap_cases = [c for c in cases if c.capability_id == capability_id]
        for _ in range(runs):
            rr_list, _ = self.run_cases(cap_cases, runs_per_case=1)
            all_scores.extend(r.grading.score for r in rr_list)
        return _repeatability_stats(all_scores)

    def _run_single(self, case: BenchmarkCase) -> Tuple[Optional[RunResult], Optional[FailureRecord]]:
        start = time.perf_counter()
        try:
            output = self.backend.run(case.capability_id, case.input)
            latency = time.perf_counter() - start
            if latency > self.timeout_s:
                return None, FailureRecord(case_id=case.benchmark_id, capability_id=case.capability_id,
                                           failure_type=FAILURE_TIMEOUT,
                                           details=f"Latency {latency:.2f}s > timeout {self.timeout_s}s",
                                           timestamp=datetime.now(timezone.utc))
            grading = self.grader.grade(case.grading_method, output, case.expected_output)
            return RunResult(case=case, grading=grading, latency_s=round(latency, 4)), None
        except MemoryError as e:
            return None, FailureRecord(case_id=case.benchmark_id, capability_id=case.capability_id,
                                       failure_type=FAILURE_RESOURCE, details=str(e),
                                       timestamp=datetime.now(timezone.utc))
        except NotImplementedError as e:
            return None, FailureRecord(case_id=case.benchmark_id, capability_id=case.capability_id,
                                       failure_type=FAILURE_IMPLEMENTATION, details=str(e),
                                       timestamp=datetime.now(timezone.utc))
        except Exception as e:
            return None, FailureRecord(case_id=case.benchmark_id, capability_id=case.capability_id,
                                       failure_type=self._classify_failure(e), details=str(e),
                                       timestamp=datetime.now(timezone.utc))

    def _classify_failure(self, exc: Exception) -> str:
        msg = str(exc).lower()
        if "timeout" in msg or "timed out" in msg:
            return FAILURE_TIMEOUT
        if "permission" in msg or "denied" in msg:
            return FAILURE_POLICY_DENIED
        if "invalid" in type(exc).__name__.lower() or "invalid" in msg:
            return FAILURE_INVALID_CASE
        if "grading" in msg:
            return FAILURE_GRADING
        return FAILURE_BENCHMARK
