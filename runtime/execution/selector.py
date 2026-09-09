from dataclasses import dataclass
from typing import Optional
from runtime.execution.models import Task
from runtime.execution.capability import CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy

@dataclass
class ExecutorSelection:
    executor_type: ExecutorType
    executor_id: str
    model_id: Optional[str]
    reason: str
    policy_version: str
    risk_class: str

class ExecutorSelector:
    def select(self, task: Task, capability: CapabilityDefinition, policy: RuntimePolicy) -> ExecutorSelection:
        if not capability.enabled:
            raise ValueError(f"Capability {capability.capability_id} is disabled")
            
        if not capability.inference_required:
            if not capability.deterministic_allowed:
                raise ValueError(f"Capability {capability.capability_id} must be deterministic but deterministic_allowed is False")
            
            return ExecutorSelection(
                executor_type=ExecutorType.DETERMINISTIC,
                executor_id="deterministic-v1",
                model_id=None,
                reason="Policy requires deterministic executor for non-inference tasks",
                policy_version=policy.version,
                risk_class=capability.risk_level
            )
            
        if not policy.allow_llm:
            raise ValueError("LLM capabilities are disabled by runtime policy")
            
        raise NotImplementedError("LLM Executors are not currently implemented")
