from dataclasses import dataclass
from typing import Optional
from runtime.execution.models import Task
from runtime.execution.capability import CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.registry import ModelRegistry
from runtime.orchestration.kernel import Orchestrator
from runtime.orchestration.plan import RoutingClass


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
    """Legacy ExecutorSelector wrapper backed by the canonical Orchestrator kernel."""

    def __init__(self, registry: Optional[ModelRegistry] = None, intelligence_layer=None):
        self.registry = registry or ModelRegistry()
        self.intelligence_layer = intelligence_layer
        self._orchestrator = Orchestrator(
            model_registry=self.registry,
            intelligence_layer=self.intelligence_layer,
        )

    def select(self, task: Task, capability: CapabilityDefinition, policy: RuntimePolicy) -> ExecutorSelection:
        # Guarantee task has capability_id for Orchestrator
        setattr(task, "capability_id", capability.capability_id)
        # Guarantee capability is in registry for Orchestrator
        self._orchestrator.capability_registry.register(capability)
        
        plan = self._orchestrator.plan_task(task, policy)
        
        if plan.routing_class == RoutingClass.BLOCKED:
            raise ValueError(f"Execution plan BLOCKED: {plan.decision_reason}")
            
        exec_type = ExecutorType(plan.executor_type)
        return ExecutorSelection(
            executor_type=exec_type,
            executor_id=plan.executor_id,
            executor_version="1.0.0",
            model_id=plan.model_id,
            model_version=plan.model_version,
            reason=plan.decision_reason,
            policy_version=plan.policy_version,
            risk_class=capability.risk_level,
            execution_mode=plan.routing_class.value,
        )
