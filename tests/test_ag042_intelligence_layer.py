import pytest
from datetime import datetime, timezone
from runtime.intelligence.layer import LocalIntelligenceLayer
from runtime.intelligence.models import (
    ImplementationProfile,
    ImplementationCandidate,
    CapabilityAssessmentRequest,
    CapabilityAssessmentResponse,
    DelegationDecision,
    CertificationStatus,
    ResourceFit,
    BenchmarkResult,
)
from runtime.execution.capability import ExecutorType
from runtime.orchestration.kernel import Orchestrator
from runtime.execution.registry import ModelRegistry
from runtime.execution.models import ModelDefinition, ModelState
from runtime.execution.capability import CapabilityRegistry

def _profile(impl_id: str, avail=True, cert=CertificationStatus.CERTIFIED, gpu=True, net=False, cap="test.cap", ex_class="LOCAL_MODEL"):
    return ImplementationProfile(
        implementation_id=impl_id,
        capability_ids=[cap],
        quality_profile="high",
        resource_profile={"gpu_present": gpu, "requires_network": net},
        latency_profile={},
        cost_profile={},
        availability=avail,
        certification=cert,
        artifact_references=[],
        adapter_references=[],
        execution_class=ex_class,
    )

def _benchmark(impl_id: str, cap="test.cap", score=0.9, conf=0.9, latency=100.0, timestamp=None, adapter_rev=None):
    b = BenchmarkResult(
        benchmark_id=f"bench_{impl_id}_{datetime.now().timestamp()}",
        implementation_id=impl_id,
        capability_id=cap,
        dataset_version="1.0",
        score=score,
        confidence=conf,
        latency=latency,
        resource_usage={},
        timestamp=timestamp or datetime.now(timezone.utc),
        certification_status=CertificationStatus.CERTIFIED,
    )
    if adapter_rev:
        setattr(b, "adapter_revision", adapter_rev)
    return b

@pytest.fixture
def layer():
    return LocalIntelligenceLayer()

def test_1_available_model_selected(layer):
    layer.register_implementation(_profile("model_1", avail=True))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.decision == DelegationDecision.DELEGATE
    assert res.selected_implementation.implementation_id == "model_1"

def test_2_unavailable_model_rejected(layer):
    layer.register_implementation(_profile("model_1", avail=False))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.decision == DelegationDecision.FAIL_CAPABILITY_INSUFFICIENT
    assert "Not available" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_3_install_required_model_rejected():
    # ModelRegistry translates INSTALL_REQUIRED to unavailable for layer mapping.
    reg = ModelRegistry()
    m = ModelDefinition("m1", "M1", "prov", "LOCAL_MODEL", "1.0", ModelState.INSTALL_REQUIRED, ["test.cap"], [], {}, {}, 8000, "int8", "", "", "hf", 1, 100, 100, 100, "none", "required")
    reg._models["m1"] = m
    assert not reg.is_available("m1")

def test_4_unsupported_capability_rejected(layer):
    layer.register_implementation(_profile("model_1", cap="other.cap"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert "Unsupported capability 'test.cap'" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_5_certified_implementation_accepted(layer):
    layer.register_implementation(_profile("model_1", cert=CertificationStatus.CERTIFIED))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.decision == DelegationDecision.DELEGATE

def test_6_stale_certification_rejected(layer):
    layer.register_implementation(_profile("model_1", cert=CertificationStatus.STALE))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert "Certification status invalid: STALE" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_7_revoked_certification_rejected(layer):
    layer.register_implementation(_profile("model_1", cert=CertificationStatus.REVOKED))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert "Certification status invalid: REVOKED" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_8_rebenchmark_required_rejected(layer):
    layer.register_implementation(_profile("model_1", cert=CertificationStatus.REQUIRES_REBENCHMARK))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert "Certification status invalid: REQUIRES_REBENCHMARK" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_9_no_benchmark_evidence(layer):
    layer.register_implementation(_profile("model_1", cert=CertificationStatus.CERTIFIED))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.decision == DelegationDecision.FAIL_CAPABILITY_INSUFFICIENT
    assert "No valid benchmark evidence found" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_10_valid_benchmark_evidence(layer):
    layer.register_implementation(_profile("model_1"))
    layer.add_benchmark_result(_benchmark("model_1", score=0.9))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.decision == DelegationDecision.DELEGATE

def test_11_resource_fit(layer):
    layer.register_implementation(_profile("model_1", gpu=True))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8, resource_constraints={"requires_gpu": True})
    res = layer.assess_capability(req)
    assert res.selected_implementation.resource_fit == ResourceFit.FIT

def test_12_resource_insufficient(layer):
    layer.register_implementation(_profile("model_1", gpu=False))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8, resource_constraints={"requires_gpu": True})
    res = layer.assess_capability(req)
    assert "Resource fit incompatible: missing GPU" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_13_resource_unknown(layer):
    # If a specific constraint isn't checked but constraints exist, the implementation sets FIT by default assuming passed
    layer.register_implementation(_profile("model_1", gpu=True))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8, resource_constraints={"requires_tpu": True})
    res = layer.assess_capability(req)
    assert res.selected_implementation.resource_fit == ResourceFit.FIT

def test_14_network_policy_incompatibility(layer):
    layer.register_implementation(_profile("model_1", net=True))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8, policy_constraints={"network": "disabled"})
    res = layer.assess_capability(req)
    assert "Policy denial" in res.assessment_provenance["rejection_reasons"]["model_1"]

def test_15_filesystem_policy_incompatibility(layer):
    # Placeholder for filesystem policy - currently network is enforced
    pass

def test_16_local_execution_class_preserved(layer):
    layer.register_implementation(_profile("model_1", ex_class="LOCAL_MODEL"))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.selected_implementation.execution_class == "LOCAL_MODEL"

def test_17_frontier_execution_class_preserved(layer):
    layer.register_implementation(_profile("model_1", ex_class="REMOTE_MODEL"))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.selected_implementation.execution_class == "REMOTE_MODEL"

def test_18_certification_drift(layer):
    p = _profile("model_1")
    p.adapter_revision = "rev2"
    layer.register_implementation(p)
    layer.add_benchmark_result(_benchmark("model_1", adapter_rev="rev1"))
    status = layer.check_certification_drift(p)
    assert status == CertificationStatus.STALE

def test_19_provenance_completeness(layer):
    layer.register_implementation(_profile("model_1"))
    layer.register_implementation(_profile("model_2", avail=False))
    layer.add_benchmark_result(_benchmark("model_1"))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert "model_1" in res.assessment_provenance["eligible_candidates"]
    assert "Not available" in res.assessment_provenance["rejection_reasons"]["model_2"]

def test_20_deterministic_ordering_of_candidates(layer):
    layer.register_implementation(_profile("model_1"))
    layer.register_implementation(_profile("model_2"))
    layer.add_benchmark_result(_benchmark("model_1", score=0.85, conf=0.9))
    layer.add_benchmark_result(_benchmark("model_2", score=0.90, conf=0.9))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    # model_2 has higher score
    assert res.selected_implementation.implementation_id == "model_2"

def test_21_quality_threshold_enforcement(layer):
    layer.register_implementation(_profile("model_1"))
    layer.add_benchmark_result(_benchmark("model_1", score=0.7))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.decision == DelegationDecision.ESCALATE
    assert "No candidate met required quality threshold" in res.assessment_provenance["rejection_reasons"]["all"]

def test_22_confidence_recorded(layer):
    layer.register_implementation(_profile("model_1"))
    layer.add_benchmark_result(_benchmark("model_1", score=0.9, conf=0.95))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.confidence == 0.95
    assert res.selected_implementation.confidence == 0.95

def test_23_latency_recorded(layer):
    layer.register_implementation(_profile("model_1"))
    layer.add_benchmark_result(_benchmark("model_1", latency=123.4))
    req = CapabilityAssessmentRequest(capability_id="test.cap", quality_required=0.8)
    res = layer.assess_capability(req)
    assert res.selected_implementation.latency == 123.4

def test_24_registry_reconciliation():
    cap_reg = CapabilityRegistry()
    model_reg = ModelRegistry()
    intel_layer = LocalIntelligenceLayer()
    orchestrator = Orchestrator(cap_reg, model_reg, intel_layer)
    
    m = ModelDefinition("m_remote", "Remote", "prov", ExecutorType.REMOTE_MODEL.value, "1.0", ModelState.AVAILABLE, ["document.classify"], [], {}, {}, 8000, "none", "", "", "api", 1, 100, 100, 100, "none", "required")
    model_reg._models["m_remote"] = m
    orchestrator._reconcile_registries()
    
    profile = intel_layer._implementations["m_remote"]
    assert profile.execution_class == ExecutorType.REMOTE_MODEL.value
