from typing import List, Dict, Optional
import uuid
from datetime import datetime, timezone

from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.execution.deterministic_executor import DeterministicExecutor
from runtime.execution.capability import CapabilityRegistry
from runtime.execution.policy import RuntimePolicy
from runtime.execution.selector import ExecutorSelector
from runtime.execution.worker import WorkerManager

class ExecutionManager:
    """
    Manages the queue and history of workspace executions for the control plane.
    In a real system this would be backed by a database.
    """
    def __init__(self, workspace_manager: EphemeralWorkspaceManager, audit_manager=None):
        self._executions: Dict[str, TaskExecutionContext] = {}
        self._tasks: Dict[str, Task] = {}
        self.workspace_manager = workspace_manager
        
        self.registry = CapabilityRegistry()
        self.policy = RuntimePolicy()
        from runtime.execution.registry import ModelRegistry
        self.model_registry = ModelRegistry()
        self.selector = ExecutorSelector(self.model_registry)
        self.worker_manager = WorkerManager(workspace_manager, audit_manager)

    def submit_task(self, task: Task) -> TaskExecutionContext:
        execution_id = str(uuid.uuid4())
        
        # 1. Capability Lookup
        cap = self.registry.get(task.capability_id)
        if not cap:
            raise ValueError(f"Unknown capability: {task.capability_id}")
            
        # 2. Policy Evaluation & Executor Selection
        selection = self.selector.select(task, cap, self.policy)
        
        # Determine paths
        try:
            workspace_path = self.workspace_manager.create_workspace(execution_id)
        except Exception as e:
            raise RuntimeError(f"Failed to create workspace: {e}")
            
        context = TaskExecutionContext(
            execution_id=execution_id,
            task_id=task.task_id,
            capability_id=task.capability_id,
            workspace_path=workspace_path,
            environment={},
            allowed_tools=["filesystem.inspect"],
            deadline=task.deadline,
            resource_limits={"max_output_size": 1024*1024, "max_workspace_size": 10*1024*1024},
            network_policy="disabled",
            write_policy="workspace_only",
            status=ExecutionStatus.QUEUED
        )
        context.executor_type = selection.executor_type.value
        context.executor_id = selection.executor_id
        context.executor_version = selection.executor_version
        context.model_id = selection.model_id
        context.model_version = selection.model_version
        context.policy_version = selection.policy_version
        
        self._tasks[execution_id] = task
        self._executions[execution_id] = context
        
        self.worker_manager.create_worker(context, selection, task)
        
        return context
        
    def execute_sync(self, execution_id: str) -> TaskExecutionContext:
        """
        Executes a queued task synchronously via the worker manager.
        """
        context = self._executions.get(execution_id)
        task = self._tasks.get(execution_id)
        if not context or not task:
            raise ValueError("Execution not found")
            
        cap = self.registry.get(task.capability_id)
        worker = next((w for w in self.worker_manager.list_workers() if w.execution_id == execution_id), None)
        if not worker:
            raise ValueError("Worker not found for execution")
            
        self.worker_manager.start_worker(worker.worker_id, context, task, cap)
        self.worker_manager.terminate_worker(worker.worker_id)
        
        # If success or failure, we can clean up if policy dictates, 
        # but for Control Plane visibility, we keep the record in memory.
        # We clean up the ephemeral workspace to save space.
        if context.status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT, ExecutionStatus.LIMIT_EXCEEDED):
            if task.workspace_policy == "destroy_on_complete":
                self.workspace_manager.destroy_workspace(context.workspace_path)
                
        return context

    def get_execution(self, execution_id: str) -> Optional[TaskExecutionContext]:
        return self._executions.get(execution_id)
        
    def get_all_executions(self) -> List[TaskExecutionContext]:
        return sorted(list(self._executions.values()), key=lambda x: x.execution_id)
