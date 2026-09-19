import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
from .models import (
    ImplementationProfile,
    BenchmarkResult,
    CapabilityAssessmentRequest,
    CapabilityAssessmentResponse,
    CapabilityTier,
    ResourceFit,
    CertificationStatus,
    ImplementationCandidate,
    DelegationDecision
)

logger = logging.getLogger(__name__)

class LocalIntelligenceLayer:
    """
    The Local Intelligence Layer assesses capabilities and determines
    delegation viability based on required quality thresholds and constraints,
    abstracting away physical model specifics.
    """

    def __init__(self):
        # implementation_id -> ImplementationProfile
        self._implementations: Dict[str, ImplementationProfile] = {}
        # benchmark_id -> BenchmarkResult
        self._benchmarks: Dict[str, BenchmarkResult] = {}
        self._assessment_cache = {}

    def register_implementation(self, profile: ImplementationProfile):
        self._implementations[profile.implementation_id] = profile
        self._assessment_cache.clear()

    def remove_implementation(self, implementation_id: str):
        if implementation_id in self._implementations:
            del self._implementations[implementation_id]
            self._assessment_cache.clear()

    def add_benchmark_result(self, result: BenchmarkResult):
        self._benchmarks[result.benchmark_id] = result
        self._assessment_cache.clear()

    def _get_benchmark_stats(self, impl_id: str, capability_id: str) -> (float, float, float):
        relevant = [
            b for b in self._benchmarks.values()
            if b.implementation_id == impl_id and b.capability_id == capability_id
        ]
        if not relevant:
            return (0.0, 0.0, 0.0)
        
        avg_score = sum(b.score for b in relevant) / len(relevant)
        avg_conf = sum(b.confidence for b in relevant) / len(relevant)
        
        latencies = sorted([b.latency for b in relevant])
        median_latency = latencies[len(latencies) // 2] if latencies else 0.0
        
        return avg_score, avg_conf, median_latency

    def _determine_tier(self, score: float) -> CapabilityTier:
        if score >= 0.95: return CapabilityTier.L4
        if score >= 0.90: return CapabilityTier.L3
        if score >= 0.85: return CapabilityTier.L2
        if score >= 0.75: return CapabilityTier.L1
        return CapabilityTier.L0

    def assess_capability(self, request: CapabilityAssessmentRequest, available_implementations: List[str] = None) -> CapabilityAssessmentResponse:
        """
        Assess whether a capability can be fulfilled matching the required quality.
        """
        candidates: List[ImplementationCandidate] = []
        provenance = {
            "eligible_candidates": [],
            "rejection_reasons": {}
        }
        
        impls_to_check = self._implementations.values()
        if available_implementations is not None:
            impls_to_check = [impl for impl in impls_to_check if impl.implementation_id in available_implementations]
        
        for impl in impls_to_check:
            impl_id = impl.implementation_id
            # 1. Availability check
            if not impl.availability:
                provenance["rejection_reasons"][impl_id] = "Not available"
                continue
                
            # 2. Capability support check
            if request.capability_id not in impl.capability_ids:
                provenance["rejection_reasons"][impl_id] = f"Unsupported capability '{request.capability_id}'"
                continue
                
            # 3 & 4. Certification and Benchmark evidence check
            if impl.certification in (CertificationStatus.STALE, CertificationStatus.REQUIRES_REBENCHMARK, CertificationStatus.REVOKED):
                provenance["rejection_reasons"][impl_id] = f"Certification status invalid: {impl.certification.value}"
                continue
            
            score, conf, latency = self._get_benchmark_stats(impl_id, request.capability_id)
            if score == 0.0 and conf == 0.0:
                provenance["rejection_reasons"][impl_id] = "No valid benchmark evidence found"
                continue

            # 5. Resource fit check
            resource_fit = ResourceFit.UNKNOWN
            if request.resource_constraints:
                req_gpu = request.resource_constraints.get("requires_gpu")
                impl_has_gpu = impl.resource_profile.get("gpu_present")
                if req_gpu and not impl_has_gpu:
                    resource_fit = ResourceFit.INSUFFICIENT
                    provenance["rejection_reasons"][impl_id] = "Resource fit incompatible: missing GPU"
                    continue
                # If constraints exist and no explicit denial occurred, mark as FIT (assuming other constraints are satisfied)
                resource_fit = ResourceFit.FIT
            else:
                # If no constraints requested, it fits by definition
                resource_fit = ResourceFit.FIT
                
            # 6. Policy fit check
            policy_fit = True
            if request.policy_constraints:
                network_policy = request.policy_constraints.get("network")
                requires_network = impl.resource_profile.get("requires_network", False)
                if network_policy == "disabled" and requires_network:
                    policy_fit = False
                    provenance["rejection_reasons"][impl_id] = "Policy denial: Implementation requires network access but policy forbids it"
                    continue

            provenance["eligible_candidates"].append(impl_id)
            candidates.append(ImplementationCandidate(
                implementation_id=impl_id,
                execution_class=impl.execution_class,
                availability=impl.availability,
                quality=score,
                confidence=conf,
                latency=latency,
                resource_fit=resource_fit,
                policy_fit=policy_fit
            ))
            
        # Filter valid candidates (Though we already continued on policy_fit/resource_fit above, just to be safe)
        valid_candidates = [
            c for c in candidates 
            if c.policy_fit and c.resource_fit in (ResourceFit.FIT, ResourceFit.PARTIAL)
        ]
        
        if not valid_candidates:
            return CapabilityAssessmentResponse(
                decision=DelegationDecision.FAIL_CAPABILITY_INSUFFICIENT,
                selected_implementation=None,
                quality_score=0.0,
                confidence=0.0,
                tier=CapabilityTier.L0,
                reason="No available implementations for capability met constraints",
                assessment_provenance=provenance
            )
            
        # Sort by quality descending to ensure deterministic ordering
        valid_candidates.sort(key=lambda x: (x.quality, x.confidence), reverse=True)
        best_candidate = valid_candidates[0]
        
        tier = self._determine_tier(best_candidate.quality)
        
        if best_candidate.quality >= request.quality_required:
            provenance["selected_implementation"] = best_candidate.implementation_id
            return CapabilityAssessmentResponse(
                decision=DelegationDecision.DELEGATE,
                selected_implementation=best_candidate,
                quality_score=best_candidate.quality,
                confidence=best_candidate.confidence,
                tier=tier,
                reason=f"Candidate {best_candidate.implementation_id} meets required quality ({best_candidate.quality} >= {request.quality_required})",
                assessment_provenance=provenance
            )
        else:
            provenance["rejection_reasons"]["all"] = "No candidate met required quality threshold"
            return CapabilityAssessmentResponse(
                decision=DelegationDecision.ESCALATE,
                selected_implementation=None,
                quality_score=best_candidate.quality,
                confidence=best_candidate.confidence,
                tier=tier,
                reason=f"Best candidate {best_candidate.implementation_id} below required quality ({best_candidate.quality} < {request.quality_required})",
                assessment_provenance=provenance
            )

    def check_certification_drift(self, profile: ImplementationProfile) -> CertificationStatus:
        """Check if an implementation's certification has drifted due to revision changes."""
        relevant = [
            b for b in self._benchmarks.values()
            if b.implementation_id == profile.implementation_id
        ]
        if not relevant:
            return CertificationStatus.REQUIRES_REBENCHMARK
        
        latest_b = max(relevant, key=lambda x: x.timestamp)
        b_adapter_rev = getattr(latest_b, 'adapter_revision', None)
        if profile.adapter_revision and b_adapter_rev and profile.adapter_revision != b_adapter_rev:
            return CertificationStatus.STALE
            
        return profile.certification

    def _check_certification_drift(self, profile: ImplementationProfile) -> CertificationStatus:
        return self.check_certification_drift(profile)

