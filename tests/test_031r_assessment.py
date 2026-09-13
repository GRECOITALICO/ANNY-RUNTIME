import pytest
from runtime.intelligence.models import (
    ImplementationProfile, 
    BenchmarkResult, 
    CapabilityAssessmentRequest, 
    DelegationDecision, 
    CertificationStatus, 
    ResourceFit
)
from runtime.intelligence.layer import LocalIntelligenceLayer

def test_case_a_delegate():
    layer = LocalIntelligenceLayer()
    layer.register_implementation(ImplementationProfile(
        implementation_id="impl_a",
        capability_ids=["test.cap"],
        quality_profile="high",
        resource_profile={},
        latency_profile={},
        cost_profile={},
        availability=True,
        certification=CertificationStatus.CERTIFIED,
        artifact_references=[],
        adapter_references=[]
    ))
    layer.add_benchmark_result(BenchmarkResult(
        benchmark_id="b1",
        implementation_id="impl_a",
        capability_id="test.cap",
        dataset_version="v1",
        score=0.94,
        confidence=0.9,
        latency=1.0,
        resource_usage={},
        timestamp=None,
        certification_status=CertificationStatus.CERTIFIED
    ))
    
    req = CapabilityAssessmentRequest(
        capability_id="test.cap",
        quality_required=0.90
    )
    
    res = layer.assess_capability(req, available_implementations=["impl_a"])
    assert res.decision == DelegationDecision.DELEGATE
    assert res.selected_implementation is not None
    assert res.selected_implementation.implementation_id == "impl_a"

def test_case_b_no_local_delegation():
    layer = LocalIntelligenceLayer()
    layer.register_implementation(ImplementationProfile(
        implementation_id="impl_a",
        capability_ids=["test.cap"],
        quality_profile="high",
        resource_profile={},
        latency_profile={},
        cost_profile={},
        availability=True,
        certification=CertificationStatus.CERTIFIED,
        artifact_references=[],
        adapter_references=[]
    ))
    layer.add_benchmark_result(BenchmarkResult(
        benchmark_id="b1",
        implementation_id="impl_a",
        capability_id="test.cap",
        dataset_version="v1",
        score=0.94,
        confidence=0.9,
        latency=1.0,
        resource_usage={},
        timestamp=None,
        certification_status=CertificationStatus.CERTIFIED
    ))
    
    req = CapabilityAssessmentRequest(
        capability_id="test.cap",
        quality_required=0.95
    )
    
    res = layer.assess_capability(req, available_implementations=["impl_a"])
    assert res.decision == DelegationDecision.ESCALATE
    assert res.selected_implementation is None

def test_case_c_unavailable():
    layer = LocalIntelligenceLayer()
    layer.register_implementation(ImplementationProfile(
        implementation_id="impl_a",
        capability_ids=["test.cap"],
        quality_profile="high",
        resource_profile={},
        latency_profile={},
        cost_profile={},
        availability=False,
        certification=CertificationStatus.CERTIFIED,
        artifact_references=[],
        adapter_references=[]
    ))
    req = CapabilityAssessmentRequest(
        capability_id="test.cap",
        quality_required=0.90
    )
    res = layer.assess_capability(req, available_implementations=["impl_a"])
    assert res.decision == DelegationDecision.FAIL_CAPABILITY_INSUFFICIENT

