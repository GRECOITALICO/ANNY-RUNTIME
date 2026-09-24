import json
import os
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import asdict

from runtime.continuity.models import ContinuityRecord, EventRecord
from runtime.continuity.events import ContinuityEventType

logger = logging.getLogger(__name__)


class CorruptionSeverity:
    CLEAN = "CLEAN"
    RECOVERED = "RECOVERED"
    QUARANTINED = "QUARANTINED"
    BLOCKED = "BLOCKED"


class ContinuityEngine:
    """Native ANNY Operational Continuity Engine (L0, L1, L2).
    
    Provides append-only persistence, corruption handling, deterministic event sequencing,
    state reconstruction, and process interruption recovery.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.continuity_dir = self.data_dir / "continuity"
        self.continuity_dir.mkdir(parents=True, exist_ok=True)
        
        self.records_path = self.continuity_dir / "continuity_records.jsonl"
        self.events_path = self.continuity_dir / "event_records.jsonl"
        self.quarantine_path = self.continuity_dir / "quarantine.jsonl"
        
        self._records: Dict[str, ContinuityRecord] = {}
        self._events: List[EventRecord] = []
        self._event_sequence = 0
        self.quarantined_records: List[Dict[str, Any]] = []
        self.corruption_status: str = CorruptionSeverity.CLEAN
        self._lock = threading.RLock()
        
        self.load()

    def load(self) -> None:
        """Bootstrap the engine from durable append-only logs with explicit corruption handling."""
        with self._lock:
            self._records.clear()
            self._events.clear()
            self._event_sequence = 0
            self.quarantined_records.clear()
            self.corruption_status = CorruptionSeverity.CLEAN

            # Load Continuity Records (replay updates)
            if self.records_path.exists():
                with open(self.records_path, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            data = json.loads(line_str)
                            record = ContinuityRecord(**data)
                            self._records[record.continuity_id] = record
                        except Exception as err:
                            logger.warning(f"Corrupted record at line {line_no} of {self.records_path}: {err}")
                            quarantine_entry = {
                                "file": str(self.records_path),
                                "line_no": line_no,
                                "raw_content": line_str,
                                "error": str(err),
                            }
                            self.quarantined_records.append(quarantine_entry)
                            self.corruption_status = CorruptionSeverity.QUARANTINED
                            self._append_to_quarantine(quarantine_entry)

            # Load Events
            if self.events_path.exists():
                with open(self.events_path, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            data = json.loads(line_str)
                            event = EventRecord(**data)
                            # Verify sequence monotonicity
                            if event.sequence <= self._event_sequence:
                                logger.warning(
                                    f"Sequence inconsistency at line {line_no}: "
                                    f"event sequence {event.sequence} <= current sequence {self._event_sequence}"
                                )
                                self.corruption_status = CorruptionSeverity.RECOVERED
                                event.sequence = self._event_sequence + 1
                            
                            self._events.append(event)
                            if event.sequence > self._event_sequence:
                                self._event_sequence = event.sequence
                        except Exception as err:
                            logger.warning(f"Corrupted event at line {line_no} of {self.events_path}: {err}")
                            quarantine_entry = {
                                "file": str(self.events_path),
                                "line_no": line_no,
                                "raw_content": line_str,
                                "error": str(err),
                            }
                            self.quarantined_records.append(quarantine_entry)
                            self.corruption_status = CorruptionSeverity.QUARANTINED
                            self._append_to_quarantine(quarantine_entry)

    def _append_to_quarantine(self, entry: Dict[str, Any]) -> None:
        try:
            with open(self.quarantine_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to quarantine file: {e}")

    def save_record(self, record: ContinuityRecord) -> None:
        """Persist a ContinuityRecord state change append-only."""
        with self._lock:
            self._records[record.continuity_id] = record
            with open(self.records_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record)) + "\n")
                f.flush()

    def append_event(self, event: EventRecord) -> None:
        """Append a new EventRecord to the log."""
        with self._lock:
            event.sequence = self._event_sequence + 1
            self._event_sequence = event.sequence
            self._events.append(event)
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event)) + "\n")
                f.flush()

    def get_record(self, continuity_id: str) -> Optional[ContinuityRecord]:
        with self._lock:
            return self._records.get(continuity_id)

    def get_records_by_mission(self, mission_id: str) -> List[ContinuityRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.mission_id == mission_id]

    def get_events_by_mission(self, mission_id: str) -> List[EventRecord]:
        with self._lock:
            return [e for e in self._events if e.mission_id == mission_id]

    def get_records_by_task(self, task_id: str) -> List[ContinuityRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.task_id == task_id]

    def get_events_by_task(self, task_id: str) -> List[EventRecord]:
        with self._lock:
            return [e for e in self._events if e.task_id == task_id]

    def get_recent_events(self, limit: int = 100) -> List[EventRecord]:
        """Return the newest durable continuity events without mutating state."""
        with self._lock:
            if limit <= 0:
                return []
            return list(self._events[-limit:])

    def reconstruct_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Deductively reconstruct full execution context state from durable logs.
        Does not depend on Python in-memory state.
        """
        with self._lock:
            relevant_records = [
                r for r in self._records.values()
                if getattr(r, "execution_id", None) == execution_id or r.task_id == execution_id or r.continuity_id == execution_id
            ]
            relevant_events = [
                e for e in self._events
                if getattr(e, "execution_id", None) == execution_id or e.task_id == execution_id or (isinstance(e.inputs, dict) and e.inputs.get("execution_id") == execution_id)
            ]

            if not relevant_records and not relevant_events:
                return None

            latest_record = relevant_records[-1] if relevant_records else None
            
            # Sort events deterministically by sequence
            sorted_events = sorted(relevant_events, key=lambda x: x.sequence)
            last_event = sorted_events[-1] if sorted_events else None

            status = last_event.status if (last_event and last_event.status in ("COMPLETE", "SUCCESS", "FAILED", "VERIFIED", "SUCCEEDED", "TIMED_OUT")) else (latest_record.status if latest_record else (last_event.status if last_event else "UNKNOWN"))

            
            reconstruction = {
                "execution_id": execution_id,
                "task_id": latest_record.task_id if latest_record else (last_event.task_id if last_event else execution_id),
                "capability_id": latest_record.step_id if latest_record else (last_event.step_id if last_event else "unknown"),
                "status": status,
                "events_count": len(sorted_events),
                "latest_event_type": last_event.event_type.value if last_event and hasattr(last_event.event_type, "value") else str(last_event.event_type if last_event else None),
                "latest_sequence": last_event.sequence if last_event else 0,
                "evidence_refs": latest_record.evidence_refs if latest_record else (last_event.evidence_refs if last_event else []),
                "files_changed": latest_record.files_changed if latest_record else (last_event.files_changed if last_event else []),
                "commit_before": latest_record.commit_before if latest_record else (last_event.commit_before if last_event else None),
                "commit_after": latest_record.commit_after if latest_record else (last_event.commit_after if last_event else None),
                "fabric_node": latest_record.fabric_node if latest_record else (last_event.fabric_node if last_event else None),
                "fabric_tenant": latest_record.fabric_tenant if latest_record else (last_event.fabric_tenant if last_event else None),
            }
            if last_event and isinstance(last_event.inputs, dict):
                reconstruction["routing_class"] = last_event.inputs.get("routing_class")
                reconstruction["executor_type"] = last_event.inputs.get("executor_type")
                reconstruction["executor_id"] = last_event.inputs.get("executor_id")
                reconstruction["model_id"] = last_event.inputs.get("model_id")
                reconstruction["model_version"] = last_event.inputs.get("model_version")
                reconstruction["worker_id"] = last_event.inputs.get("worker_id")
                reconstruction["generation"] = last_event.inputs.get("generation")
                reconstruction["failure_reason"] = last_event.inputs.get("failure_reason")
                reconstruction["error_message"] = last_event.inputs.get("error_message")

            return reconstruction


    def flush(self) -> None:
        """Explicitly flush OS buffers to disk using fsync."""
        with self._lock:
            if self.records_path.exists():
                with open(self.records_path, "a") as f:
                    f.flush()
                    os.fsync(f.fileno())
            if self.events_path.exists():
                with open(self.events_path, "a") as f:
                    f.flush()
                    os.fsync(f.fileno())
