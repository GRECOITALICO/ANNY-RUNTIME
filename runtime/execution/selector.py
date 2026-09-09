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

class ExecutorSelector:
    def __init__(self, registry: Optional[ModelRegistry] = None):
        self.registry = registry or ModelRegistry()

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
            
        bindings = self.registry.get_bindings_for_capability(capability.capability_id)
        if not bindings:
            raise ValueError(f"No models bound to capability {capability.capability_id}")
            
        selected_model_id = None
        for b in sorted(bindings, key=lambda x: (not x.preferred, not x.fallback)):
            if b.authorization == "forbidden":
                continue
            if self.registry.is_available(b.model_id):
                selected_model_id = b.model_id
                break
                
        if not selected_model_id:
            raise ValueError(f"No available models found for capability {capability.capability_id}")
            
        model_def = self.registry.get_model(selected_model_id)
        
        return ExecutorSelection(
            executor_type=ExecutorType(model_def.executor_type),
            executor_id=f"worker-compatible-{model_def.executor_type.lower()}",
            executor_version="1.0.0",
            model_id=selected_model_id,
            model_version=model_def.version,
            reason=f"Selected model {selected_model_id} via binding",
            policy_version=policy.version,
            risk_class=capability.risk_level
        )
