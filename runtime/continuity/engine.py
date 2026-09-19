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
    The status property is the read model consumed by ThreePlaneBootstrap.
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
        self._load_errors: List[str] = []
        self._lock = threading.RLock()

        self.load()

    @property
    def status(self) -> Dict[str, object]:
        """Return a deterministic continuity read model for bootstrap gates.

        The model is intentionally small and side-effect free. Any malformed durable
        record prevents a COHERENT claim; reconciliation-required events do the same.
        """
        with self._lock:
            if self._load_errors:
                return {
                    "state": "BLOCKED",
                    "reason": "Malformed durable continuity record",
                    "errors": list(self._load_errors),
                }

            for event in reversed(self._events):
                if event.status in {"RECONCILIATION_REQUIRED", "BLOCKED", "FAILED"}:
                    return {
                        "state": "RECONCILIATION_REQUIRED" if event.status == "RECONCILIATION_REQUIRED" else "BLOCKED",
                        "reason": event.observation or event.result or event.status,
                        "event_id": event.event_id,
                    }

            for record in self._records.values():
                if record.status in {"BLOCKED", "FAILED"}:
                    return {
                        "state": "BLOCKED",
                        "reason": record.reason or record.status,
                        "continuity_id": record.continuity_id,
                    }

            return {
                "state": "COHERENT",
                "record_count": len(self._records),
                "event_count": len(self._events),
                "generation": self._event_sequence,
            }

    @property
    def load_errors(self) -> List[str]:
        with self._lock:
            return list(self._load_errors)

    def load(self) -> None:
        """Bootstrap the engine from durable append-only logs.

        Corruption is observable and blocks a coherent bootstrap instead of being
        silently discarded.
        """
        with self._lock:
            self._records.clear()
            self._events.clear()
            self._event_sequence = 0
            self._load_errors.clear()

            if self.records_path.exists():
                with open(self.records_path, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            record = ContinuityRecord(**data)
                            self._records[record.continuity_id] = record
                        except Exception as exc:
                            self._load_errors.append(f"{self.records_path.name}:{line_no}:{type(exc).__name__}")

            if self.events_path.exists():
                with open(self.events_path, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            event = EventRecord(**data)
                            self._events.append(event)
                            if event.sequence > self._event_sequence:
                                self._event_sequence = event.sequence
                        except Exception as exc:
                            self._load_errors.append(f"{self.events_path.name}:{line_no}:{type(exc).__name__}")

            self._events.sort(key=lambda event: event.sequence)

    def save_record(self, record: ContinuityRecord) -> None:
        """Persist a ContinuityRecord state change append-only."""
        with self._lock:
            self._records[record.continuity_id] = record
            with open(self.records_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), default=str) + "\n")

    def append_event(self, event: EventRecord) -> None:
        """Append a new EventRecord to the log."""
        with self._lock:
            event.sequence = self._event_sequence + 1
            self._event_sequence = event.sequence
            self._events.append(event)
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), default=str) + "\n")

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
