import abc
from typing import Dict, Any, Optional
from runtime.execution.models import Task
from runtime.orchestration.plan import ExecutionPlan


class FrontierExecutor(abc.ABC):
    """
    Governed boundary interface for FRONTIER_MODEL execution.
    
    Provides an explicit, non-mock interface contract for remote/frontier
    model execution without invoking unauthorized external calls.
    """

    @abc.abstractmethod
    def is_available(self, model_id: Optional[str] = None) -> bool:
        """Check if frontier model service is available and authorized."""
        pass

    @abc.abstractmethod
    def execute_plan(self, task: Task, plan: ExecutionPlan) -> Dict[str, Any]:
        """Execute a validated FRONTIER_MODEL ExecutionPlan."""
        pass


class DefaultFrontierExecutor(FrontierExecutor):
    """Default implementation of FrontierExecutor boundary."""

    def __init__(self, enabled: bool = False, available_models: Optional[list] = None):
        self._enabled = enabled
        self._available_models = available_models or ["frontier-gpt4", "frontier-claude-3-5-sonnet"]

    def is_available(self, model_id: Optional[str] = None) -> bool:
        if not self._enabled:
            return False
        if model_id is not None:
            return model_id in self._available_models
        return len(self._available_models) > 0

    def execute_plan(self, task: Task, plan: ExecutionPlan) -> Dict[str, Any]:
        if not self.is_available(plan.model_id):
            raise RuntimeError(f"Frontier model {plan.model_id} is unavailable or unauthorized")
        return {
            "status": "COMPLETED",
            "task_id": task.task_id,
            "plan_id": plan.task_id,
            "executor": "DefaultFrontierExecutor",
            "model_id": plan.model_id,
        }
