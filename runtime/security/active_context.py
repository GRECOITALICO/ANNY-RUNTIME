import threading
from dataclasses import dataclass
from typing import Optional

@dataclass
class ActiveContext:
    account_id: str
    project_id: str
    workspace_id: Optional[str] = None
    repository_id: Optional[str] = None

class ActiveContextManager:
    """Thread-safe context manager for tracking the active account/project scope."""
    def __init__(self):
        self._local = threading.local()

    def set_context(self, context: ActiveContext) -> None:
        self._local.context = context

    def get_context(self) -> Optional[ActiveContext]:
        return getattr(self._local, "context", None)

    def clear(self) -> None:
        if hasattr(self._local, "context"):
            del self._local.context

_manager = ActiveContextManager()

def set_active_context(context: ActiveContext) -> None:
    _manager.set_context(context)

def get_active_context() -> Optional[ActiveContext]:
    return _manager.get_context()

def clear_active_context() -> None:
    _manager.clear()
