import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

class EventType(Enum):
    SESSION_ATTACHED = auto()
    SESSION_DETACHED = auto()
    WORKSPACE_CREATED = auto()
    WORKSPACE_READY = auto()
    WORKSPACE_DESTROYED = auto()
    PROCESS_STARTED = auto()
    PROCESS_OUTPUT = auto()
    PROCESS_EXITED = auto()
    EXECUTION_STARTED = auto()
    EXECUTION_COMPLETED = auto()
    EXECUTION_FAILED = auto()
    RUNTIME_HEALTH_CHANGED = auto()
    UPDATE_AVAILABLE = auto()
    UPDATE_COMPLETED = auto()
    UPDATE_FAILED = auto()
    RUNTIME_STARTED = auto()
    RUNTIME_STOPPING = auto()
    RUNTIME_RECOVERY = auto()
    GENERATION_INCREMENTED = auto()
    BOOTSTRAP_STARTED = auto()
    GITHUB_DISCOVERED = auto()
    ORGANIZATION_DISCOVERED = auto()
    REPOSITORIES_DISCOVERED = auto()
    OPERATIONAL_REPOSITORY_RESOLVED = auto()
    CANONICAL_STATE_LOADED = auto()
    CURRENT_MISSION_RESOLVED = auto()
    BLOCKERS_LOADED = auto()
    NEXT_ACTION_LOADED = auto()
    CONTINUITY_RECONCILED = auto()
    BOOTSTRAP_COMPLETED = auto()

@dataclass
class Event:
    event_type: EventType
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

class EventBus:
    """Synchronous event bus for runtime components."""
    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._history: List[Event] = []
        self._history_limit = 100
        
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            
    def emit(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]
            
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Log exception but do not interrupt other handlers
                pass

    def history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]
