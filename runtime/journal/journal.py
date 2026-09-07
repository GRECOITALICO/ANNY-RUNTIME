import json
import os
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path

@dataclass
class JournalEntry:
    entry_id: str
    operation_id: str
    execution_id: str
    session_id: str
    actor_id: str
    workspace_id: str
    tool: str
    state: str
    started_at: str
    runtime_generation: int
    finished_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class OperationJournal:
    """Append-only journal for persisting operation executions."""
    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self.journal_dir = self.data_dir / "journal"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.journal_dir / "operations.jsonl"
        self._entries: List[JournalEntry] = []
        self._lock = threading.RLock()
        self.load()

    def load(self) -> None:
        with self._lock:
            self._entries.clear()
            if self.journal_path.exists():
                with open(self.journal_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                self._entries.append(JournalEntry(**data))
                            except Exception:
                                pass

    def record(self, entry: JournalEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry)) + "\n")

    def get_entry(self, entry_id: str) -> Optional[JournalEntry]:
        with self._lock:
            for entry in self._entries:
                if entry.entry_id == entry_id:
                    return entry
        return None

    def get_operation(self, operation_id: str) -> List[JournalEntry]:
        with self._lock:
            return [e for e in self._entries if e.operation_id == operation_id]

    def get_interrupted(self, generation: int) -> List[JournalEntry]:
        with self._lock:
            interrupted = []
            for entry in self._entries:
                if entry.runtime_generation < generation and entry.state not in ("COMPLETED", "FAILED"):
                    interrupted.append(entry)
            return interrupted

    def flush(self) -> None:
        with self._lock:
            if self.journal_path.exists():
                with open(self.journal_path, "a") as f:
                    f.flush()
                    os.fsync(f.fileno())
