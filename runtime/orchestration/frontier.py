import abc
from dataclasses import dataclass
from typing import Dict, Any, Optional
from runtime.execution.models import Task
from runtime.orchestration.plan import ExecutionPlan


@dataclass(frozen=True)
class FrontierExecutionReceipt:
    """Correlated evidence emitted by an injected physical Frontier executor.

    A plain result payload is not an execution receipt.  Runtime validates this
    structure before it can transition a worker to ``SUCCEEDED``; the executor
    must supply the result digest and an evidence reference itself.
    """

    execution_id: str
    task_id: str
    executor_id: str
    model_id: str
    result_data: Dict[str, Any]
    result_hash: str
    evidence_ref: str
    completed_at: str


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
    def identity(self) -> str:
        """Return the stable identity of the physically injected executor."""
        pass

    @abc.abstractmethod
    def is_authorized(self) -> bool:
        """Whether this executor was explicitly authorized for Runtime use."""
        pass

    @abc.abstractmethod
    def execute_plan(self, task: Task, plan: ExecutionPlan) -> FrontierExecutionReceipt:
        """Execute a validated plan and return a correlated physical receipt."""
        pass


class DefaultFrontierExecutor(FrontierExecutor):
    """Disabled sentinel; never a physical or authorized Frontier executor."""

    def __init__(self, enabled: bool = False, available_models: Optional[list] = None):
        self._enabled = enabled
        self._available_models = available_models or ["frontier-gpt4", "frontier-claude-3-5-sonnet"]

    def is_available(self, model_id: Optional[str] = None) -> bool:
        # ``enabled`` remains accepted for compatibility with old construction
        # sites, but cannot turn this local sentinel into a remote authority.
        return False

    def identity(self) -> str:
        return "default-frontier-sentinel"

    def is_authorized(self) -> bool:
        return False

    def execute_plan(self, task: Task, plan: ExecutionPlan) -> FrontierExecutionReceipt:
        raise RuntimeError(
            "DefaultFrontierExecutor is a disabled sentinel, not a physical executor"
        )
