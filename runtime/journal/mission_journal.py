import json
import os
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

@dataclass
class MissionJournalEntry:
    entry_id: str
    timestamp: str
    event_type: str
    mission_id: str
    actor: str
    payload: Dict[str, Any] = field(default_factory=dict)

class MissionJournal:
    """Append-only journal for persisting high-level mission events."""
    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self.journal_dir = self.data_dir / "journal"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.journal_dir / "missions.jsonl"
        self._entries: List[MissionJournalEntry] = []
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
                                self._entries.append(MissionJournalEntry(**data))
                            except Exception as e:
                                logger.error(f"Failed to parse mission entry: {e}")

    def record(self, event_type: str, mission_id: str, actor: str, payload: Dict[str, Any] = None) -> MissionJournalEntry:
        entry = MissionJournalEntry(
            entry_id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            mission_id=mission_id,
            actor=actor,
            payload=payload or {}
        )
        with self._lock:
            self._entries.append(entry)
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def get_mission_events(self, mission_id: str) -> List[MissionJournalEntry]:
        with self._lock:
            return [e for e in self._entries if e.mission_id == mission_id]

    def flush(self) -> None:
        with self._lock:
            if self.journal_path.exists():
                with open(self.journal_path, "a") as f:
                    f.flush()
                    os.fsync(f.fileno())
