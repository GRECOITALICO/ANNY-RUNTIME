import logging
from typing import Optional, Dict, Any, List
from runtime.execution.models import Task
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.registry import ModelRegistry
from runtime.intelligence.layer import LocalIntelligenceLayer
from runtime.intelligence.models import (
    CapabilityAssessmentRequest,
    DelegationDecision,
    CertificationStatus,
    ResourceFit,
)
from runtime.orchestration.plan import ExecutionPlan, RoutingClass
from runtime.orchestration.frontier import FrontierExecutor, DefaultFrontierExecutor

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Canonical Orchestration Kernel for ANNY Runtime (AG-041).
    
    Evaluates incoming tasks against capability definitions, runtime policies,
    and model registries to produce secret-free, auditable ExecutionPlans.
    """

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        model_registry: Optional[ModelRegistry] = None,
        intelligence_layer: Optional[LocalIntelligenceLayer] = None,
        frontier_executor: Optional[FrontierExecutor] = None,
    ):
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.model_registry = model_registry or ModelRegistry()
        self.intelligence_layer = intelligence_layer or LocalIntelligenceLayer()
        self.frontier_executor = frontier_executor or DefaultFrontierExecutor()
        self._reconcile_registries()

    def _reconcile_registries(self) -> None:
        """
        Reconcile ModelRegistry models with LocalIntelligenceLayer profiles
        so registered models are known candidates for evaluation.
        """
        registered_models = self.model_registry.list_models()
        for m in registered_models:
            impl_id = m.model_id
            if impl_id not in self.intelligence_layer._implementations:
                # Synchronize registered model to intelligence layer profile
                from runtime.intelligence.models import ImplementationProfile
                profile = ImplementationProfile(
                    implementation_id=impl_id,
                    capability_ids=m.capabilities_supported or ["document.classify"],
                    quality_profile="high" if getattr(m, "performance_score", 0.90) > 0.8 else "standard",
                    resource_profile={"gpu_present": getattr(m, "requires_gpu", False)},
                    latency_profile={"p50": 100},
                    cost_profile={"token_cost": 0.0},
                    availability=self.model_registry.is_available(impl_id),
                    certification=getattr(m, "certification_status", CertificationStatus.CERTIFIED),
                    artifact_references=[],
                    adapter_references=[],
                )
                self.intelligence_layer.register_implementation(profile)

    def plan_task(self, task: Task, policy: Optional[RuntimePolicy] = None) -> ExecutionPlan:
        """
        Analyze task and produce a canonical ExecutionPlan.
        """
        policy = policy or RuntimePolicy()
        cap_id = getattr(task, "capability_id", None) or getattr(task, "type", "unknown")
        task_id = getattr(task, "task_id", "task-001")
        
        provenance: Dict[str, Any] = {
            "task_id": task_id,
            "requested_capability": cap_id,
            "considered_implementations": [],
            "rejection_reasons": {},
            "policy_applied": policy.version,
        }

        # Rule 6 — Unknown Capability Check
        cap_def = self.capability_registry.get(cap_id)
        if not cap_def:
            reason = f"Unknown capability: '{cap_id}'"
            return ExecutionPlan(
                task_id=task_id,
                capability_id=cap_id or "unknown",
                capability_version="0.0.0",
                routing_class=RoutingClass.BLOCKED,
                executor_type="NONE",
                executor_id="none",
                policy_version=policy.version,
                decision_reason=reason,
                provenance=provenance,
            )

        provenance["capability_version"] = cap_def.version
        provenance["risk_level"] = cap_def.risk_level

        # Check if capability is disabled
        if not cap_def.enabled:
            reason = f"Capability '{cap_id}' is disabled"
            return ExecutionPlan(
                task_id=task_id,
                capability_id=cap_id,
                capability_version=cap_def.version,
                routing_class=RoutingClass.BLOCKED,
                executor_type="NONE",
                executor_id="none",
                policy_version=policy.version,
                decision_reason=reason,
                provenance=provenance,
            )

        # Rule 7 — Policy Denial Check
        if cap_def.inference_required and not policy.allow_llm:
            reason = "Policy denial: LLM capabilities are disabled by runtime policy"
            return ExecutionPlan(
                task_id=task_id,
                capability_id=cap_id,
                capability_version=cap_def.version,
                routing_class=RoutingClass.BLOCKED,
                executor_type="NONE",
                executor_id="none",
                policy_version=policy.version,
                decision_reason=reason,
                provenance=provenance,
            )

        if cap_def.network_policy == "disabled" and getattr(task, "requires_network", False):
            reason = f"Policy denial: Capability '{cap_id}' forbids network access"
            return ExecutionPlan(
                task_id=task_id,
                capability_id=cap_id,
                capability_version=cap_def.version,
                routing_class=RoutingClass.BLOCKED,
                executor_type="NONE",
                executor_id="none",
                policy_version=policy.version,
                decision_reason=reason,
                provenance=provenance,
            )

        # Rule 1 — Deterministic Selection
        if not cap_def.inference_required:
            if cap_def.deterministic_allowed:
                provenance["selected_executor"] = "deterministic-v1"
                return ExecutionPlan(
                    task_id=task_id,
                    capability_id=cap_id,
                    capability_version=cap_def.version,
                    routing_class=RoutingClass.DETERMINISTIC,
                    executor_type=ExecutorType.DETERMINISTIC.value,
                    executor_id="deterministic-v1",
                    model_id=None,
                    model_version=None,
                    policy_version=policy.version,
                    authority="anny-governed-deterministic",
                    decision_reason="Non-inference capability routed to deterministic executor",
                    provenance=provenance,
                )
            else:
                reason = f"Capability '{cap_id}' requires non-inference execution but deterministic_allowed is False"
                return ExecutionPlan(
                    task_id=task_id,
                    capability_id=cap_id,
                    capability_version=cap_def.version,
                    routing_class=RoutingClass.BLOCKED,
                    executor_type="NONE",
                    executor_id="none",
                    policy_version=policy.version,
                    decision_reason=reason,
                    provenance=provenance,
                )

        # Re-sync any new ModelRegistry changes before assessment
        self._reconcile_registries()

        # Rule 2, 3, 4, 8, 9 — Inference Required Path
        req = CapabilityAssessmentRequest(
            capability_id=cap_id,
            quality_required=0.85,
            resource_constraints=getattr(task, "constraints", None),
            policy_constraints={"network": cap_def.network_policy},
        )

        available_impls = [
            m.model_id for m in self.model_registry.list_models()
            if self.model_registry.is_available(m.model_id)
        ]
        provenance["available_registry_models"] = available_impls

        # Evaluate Candidates against Rules 8 (Certification) and 9 (Resource Fit)
        candidate_impls = []
        for impl_id in available_impls:
            profile = self.intelligence_layer._implementations.get(impl_id)
            if not profile:
                provenance["rejection_reasons"][impl_id] = "No intelligence profile registered"
                continue
            
            # Rule 8 — Reject STALE, REQUIRES_REBENCHMARK, REVOKED
            if profile.certification in (
                CertificationStatus.STALE,
                CertificationStatus.REQUIRES_REBENCHMARK,
                CertificationStatus.REVOKED,
            ):
                provenance["rejection_reasons"][impl_id] = f"Certification status invalid: {profile.certification.value}"
                continue

            # Rule 9 — Resource Fit check
            req_constraints = getattr(task, "constraints", {}) or {}
            if req_constraints.get("requires_gpu") and not profile.resource_profile.get("gpu_present"):
                provenance["rejection_reasons"][impl_id] = "Resource fit incompatible: missing GPU"
                continue

            candidate_impls.append(impl_id)

        provenance["eligible_candidates"] = candidate_impls

        assessment = self.intelligence_layer.assess_capability(req, available_implementations=candidate_impls)

        # Rule 3 — Local Model Selection
        if assessment.decision == DelegationDecision.DELEGATE and assessment.selected_implementation:
            candidate = assessment.selected_implementation
            provenance["selected_implementation"] = candidate.implementation_id
            return ExecutionPlan(
                task_id=task_id,
                capability_id=cap_id,
                capability_version=cap_def.version,
                routing_class=RoutingClass.LOCAL_MODEL,
                executor_type=ExecutorType.LOCAL_MODEL.value,
                executor_id="local-model-executor",
                model_id=candidate.implementation_id,
                model_version="1.0.0",
                policy_version=policy.version,
                authority="anny-governed-local-intelligence",
                decision_reason=assessment.reason,
                provenance=provenance,
            )

        # Rule 4 — Frontier Fallback
        # When local model is unavailable / insufficient, check if frontier fallback is authorized
        frontier_authorized = (
            cap_def.fallback_executor == ExecutorType.REMOTE_MODEL or
            getattr(policy, "allow_frontier_fallback", False) or
            getattr(task, "allow_frontier", False)
        )

        if frontier_authorized and self.frontier_executor and self.frontier_executor.is_available():
            frontier_model_id = getattr(task, "preferred_frontier_model", "frontier-gpt4")
            provenance["selected_executor"] = "frontier-executor"
            provenance["frontier_model_id"] = frontier_model_id
            return ExecutionPlan(
                task_id=task_id,
                capability_id=cap_id,
                capability_version=cap_def.version,
                routing_class=RoutingClass.FRONTIER_MODEL,
                executor_type=ExecutorType.REMOTE_MODEL.value,
                executor_id="frontier-executor",
                model_id=frontier_model_id,
                model_version="1.0.0",
                policy_version=policy.version,
                authority="anny-governed-frontier",
                decision_reason=f"Local model unavailable ({assessment.reason}); routed to authorized frontier model",
                provenance=provenance,
            )

        # Rule 2 & 5 — No valid executor => BLOCKED (Strictly NO silent fallback to DETERMINISTIC or ANNY_SELF)
        reason = f"No valid executor available for inference-required capability '{cap_id}' ({assessment.reason})"
        provenance["downgrade_prevented"] = True
        return ExecutionPlan(
            task_id=task_id,
            capability_id=cap_id,
            capability_version=cap_def.version,
            routing_class=RoutingClass.BLOCKED,
            executor_type="NONE",
            executor_id="none",
            policy_version=policy.version,
            decision_reason=reason,
            provenance=provenance,
        )
