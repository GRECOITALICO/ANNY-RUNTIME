from dataclasses import dataclass
from typing import Dict, Any, List
import abc

from runtime.execution.models import Task
from runtime.execution.capability import CapabilityDefinition

@dataclass
class ContextPackage:
    """
    The strictly limited package of context provided to a ModelExecutor.
    Models DO NOT receive the full ExecutionContext, FileSystem, or API keys implicitly.
    """
    task: Task
    capability: CapabilityDefinition
    authorized_input: Dict[str, Any]
    allowed_tools: List[str]
    constraints: Dict[str, Any]
    evidence_policy: str

@dataclass
class ModelResult:
    status: str
    result_data: Dict[str, Any]
    evidence: Dict[str, Any]

class ModelExecutor(abc.ABC):
    """
    Abstract interface for executing an LLM model within a restricted ContextPackage.
    """
    @abc.abstractmethod
    def execute(self, context_package: ContextPackage) -> ModelResult:
        pass
