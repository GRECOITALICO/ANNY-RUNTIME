import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict

from runtime.continuity.models import ContinuityRecord, EventRecord

class ContinuityEngine:
    """Native ANNY Operational Continuity Engine (L0, L1, L2).
    
    Provides append-only persistence and in-memory caching for continuity records and events.
    Does not use external frameworks.
    """
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.continuity_dir = self.data_dir / "continuity"
        self.continuity_dir.mkdir(parents=True, exist_ok=True)
        
        self.records_path = self.continuity_dir / "continuity_records.jsonl"
        self.events_path = self.continuity_dir / "event_records.jsonl"
        
        self._records: Dict[str, ContinuityRecord] = {}
        self._events: List[EventRecord] = []
        self._event_sequence = 0
        self._lock = threading.RLock()
        
        self.load()

    def load(self) -> None:
        """Bootstrap the engine from durable append-only logs."""
        with self._lock:
            self._records.clear()
            self._events.clear()
            
            # Load Continuity Records (replay updates)
            if self.records_path.exists():
                with open(self.records_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                record = ContinuityRecord(**data)
                                self._records[record.continuity_id] = record
                            except Exception:
                                pass
                                
            # Load Events
            if self.events_path.exists():
                with open(self.events_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                event = EventRecord(**data)
                                self._events.append(event)
                                if event.sequence > self._event_sequence:
                                    self._event_sequence = event.sequence
                            except Exception:
                                pass

    def save_record(self, record: ContinuityRecord) -> None:
        """Persist a ContinuityRecord state change append-only."""
        with self._lock:
            self._records[record.continuity_id] = record
            with open(self.records_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record)) + "\n")

    def append_event(self, event: EventRecord) -> None:
        """Append a new EventRecord to the log."""
        with self._lock:
            event.sequence = self._event_sequence + 1
            self._event_sequence = event.sequence
            self._events.append(event)
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event)) + "\n")

    def get_record(self, continuity_id: str) -> Optional[ContinuityRecord]:
        with self._lock:
            return self._records.get(continuity_id)

    def get_records_by_mission(self, mission_id: str) -> List[ContinuityRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.mission_id == mission_id]

    def get_events_by_mission(self, mission_id: str) -> List[EventRecord]:
        with self._lock:
            return [e for e in self._events if e.mission_id == mission_id]

    def flush(self) -> None:
        with self._lock:
            if self.records_path.exists():
                with open(self.records_path, "a") as f:
                    f.flush()
                    os.fsync(f.fileno())
            if self.events_path.exists():
                with open(self.events_path, "a") as f:
                    f.flush()
                    os.fsync(f.fileno())
