import datetime
from dataclasses import dataclass, field
from typing import List, Any
from ..events.bus import EventType, Event

@dataclass
class RecoveryReport:
    previous_generation: int
    new_generation: int
    interrupted_operations: List[str]
    stale_processes: List[str]
    recovered_workspaces: List[str]
    recovery_timestamp: str

class RecoveryManager:
    """Manages system recovery across restarts."""
    def __init__(self, journal: Any, workspace_manager: Any, process_manager: Any, generation: int, event_bus: Any) -> None:
        self.journal = journal
        self.workspace_manager = workspace_manager
        self.process_manager = process_manager
        self.generation = generation
        self.event_bus = event_bus

    def recover(self) -> RecoveryReport:
        """Executes recovery procedure and reports status."""
        self.journal.load()
        
        interrupted_entries = self.journal.get_interrupted(self.generation)
        interrupted_operations = list(set(e.operation_id for e in interrupted_entries))
        
        recovered_workspaces = []
        if hasattr(self.workspace_manager, "list_workspaces"):
            recovered_workspaces = [ws.id for ws in self.workspace_manager.list_workspaces()]
            
        previous_generation = self.generation
        self.generation += 1
        
        stale_processes = []
        if hasattr(self.process_manager, "mark_stale"):
            stale_processes = self.process_manager.mark_stale(previous_generation)
            
        report = RecoveryReport(
            previous_generation=previous_generation,
            new_generation=self.generation,
            interrupted_operations=interrupted_operations,
            stale_processes=stale_processes,
            recovered_workspaces=recovered_workspaces,
            recovery_timestamp=datetime.datetime.utcnow().isoformat()
        )
        
        self.event_bus.emit(Event(
            event_type=EventType.RUNTIME_RECOVERY,
            source="RecoveryManager",
            payload={"report": report.__dict__}
        ))
        
        self.event_bus.emit(Event(
            event_type=EventType.GENERATION_INCREMENTED,
            source="RecoveryManager",
            payload={"previous_generation": previous_generation, "new_generation": self.generation}
        ))
        
        return report
