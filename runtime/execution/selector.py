from dataclasses import dataclass
from typing import Optional
from runtime.execution.models import Task
from runtime.execution.capability import CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy

from runtime.execution.registry import ModelRegistry

@dataclass
class ExecutorSelection:
    executor_type: ExecutorType
    executor_id: str
    executor_version: str
    model_id: Optional[str]
    model_version: Optional[str]
    reason: str
    policy_version: str
    risk_class: str
    execution_mode: Optional[str] = None

class ExecutorSelector:
    def __init__(self, registry: Optional[ModelRegistry] = None, intelligence_layer=None):
        self.registry = registry or ModelRegistry()
        self.intelligence_layer = intelligence_layer

    def select(self, task: Task, capability: CapabilityDefinition, policy: RuntimePolicy) -> ExecutorSelection:
        if not capability.enabled:
            raise ValueError(f"Capability {capability.capability_id} is disabled")
            
        if not capability.inference_required:
            if not capability.deterministic_allowed:
                raise ValueError(f"Capability {capability.capability_id} must be deterministic but deterministic_allowed is False")
            
            return ExecutorSelection(
                executor_type=ExecutorType.DETERMINISTIC,
                executor_id="deterministic-v1",
                executor_version="1.0.0",
                model_id=None,
                model_version=None,
                reason="Policy requires deterministic executor for non-inference tasks",
                policy_version=policy.version,
                risk_class=capability.risk_level
            )
            
        if not policy.allow_llm:
            raise ValueError("LLM capabilities are disabled by runtime policy")
            
        from runtime.intelligence.layer import LocalIntelligenceLayer
        from runtime.intelligence.models import CapabilityAssessmentRequest, DelegationDecision
        
        # If no intelligence layer injected, create one
        layer = self.intelligence_layer
        if layer is None:
            layer = LocalIntelligenceLayer()
        
        # Construct the request
        req = CapabilityAssessmentRequest(
            capability_id=capability.capability_id,
            quality_required=0.85, # Default acceptable threshold
            latency_requirement=None,
            resource_constraints=getattr(task, 'constraints', None),
            policy_constraints={"network": capability.network_policy}
        )
        
        # Get implementations available in the registry
        # We find what implementations are registered and available
        # In a cleaner architecture, ModelRegistry would be replaced or merged with IntelligenceLayer,
        # but we preserve ModelRegistry for backward compatibility.
        available_impls = [
            m.model_id for m in self.registry.list_models() 
            if self.registry.is_available(m.model_id)
        ]
        
        assessment = layer.assess_capability(req, available_implementations=available_impls)
        
        if assessment.decision != DelegationDecision.DELEGATE or not assessment.selected_implementation:
            # Escalation / Self-execution path
            return ExecutorSelection(
                executor_type=ExecutorType.REMOTE_MODEL if capability.fallback_executor == ExecutorType.REMOTE_MODEL else ExecutorType.DETERMINISTIC,
                executor_id="anny-self-executor",
                executor_version="1.0.0",
                model_id=None,
                model_version=None,
                reason=assessment.reason,
                policy_version=policy.version,
                risk_class=capability.risk_level,
                execution_mode="ANNY_SELF",
            )
            
        # Delegation path (Local/Remote Inference based on Candidate)
        candidate = assessment.selected_implementation
        exec_type = ExecutorType(candidate.execution_class)
        
        return ExecutorSelection(
            executor_type=exec_type,
            executor_id=f"{exec_type.value.lower()}-executor",
            executor_version="1.0.0",
            model_id=candidate.implementation_id, # Use implementation_id instead of legacy model_id guessing
            model_version="1.0.0",
            reason=assessment.reason,
            policy_version=policy.version,
            risk_class=capability.risk_level,
            execution_mode=exec_type.value,
        )
