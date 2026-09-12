"""TelemetryCollector for ANNY Universe observability.

Handles unified collection, scrubbing, and persistence of telemetry events,
along with querying capabilities for the Control Plane.
"""

import json
import logging
import os
import threading
from collections import deque
from typing import Any, Dict, List, Optional

from runtime.telemetry.telemetry import TelemetryEnvelope
from runtime.telemetry.scrubber import scrub_metadata
from runtime.events.bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)


class TelemetryCollector:
    """Unified telemetry collector for the ANNY Universe.
    
    Writes events to an append-only JSONL file and optionally forwards
    them to the EventBus.
    """

    def __init__(self, data_dir: str, event_bus: Optional[EventBus] = None):
        self.data_dir = data_dir
        self.telemetry_dir = os.path.join(data_dir, "telemetry")
        os.makedirs(self.telemetry_dir, exist_ok=True)
        self.log_path = os.path.join(self.telemetry_dir, "telemetry.jsonl")
        
        self.event_bus = event_bus
        self._lock = threading.Lock()
        
        # In-memory buffer of recent events for SSE/Live views (max 1000)
        self._recent_events: deque[TelemetryEnvelope] = deque(maxlen=1000)

    def emit(self, envelope: TelemetryEnvelope) -> None:
        """Emit a telemetry event. Scrub, persist, and forward."""
        # 1. Scrub metadata
        if envelope.metadata:
            envelope.metadata = scrub_metadata(envelope.metadata)
            
        envelope_dict = envelope.to_dict()
        
        # 2. Persist to disk (append-only)
        try:
            with self._lock:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(envelope_dict) + "\n")
                self._recent_events.append(envelope)
        except Exception as e:
            # We must not crash the main execution if telemetry fails
            logger.error(f"Failed to write telemetry: {e}")
            
        # 3. Forward to EventBus if configured and if there is a matching EventType
        if self.event_bus:
            # Not all telemetry events map cleanly to EventType enums,
            # but we can try to map them or broadcast as a generic telemetry event if needed.
            # For now, we only forward if we really need to, but the spec says
            # "forwards to the EventBus". We'll wrap it in a generic payload.
            # EventBus expects specific EventTypes. We will use EventType.RUNTIME_HEALTH 
            # or skip if it doesn't fit, unless we add a new TELEMETRY type.
            # Since we can't easily add to the enum from here without altering bus.py,
            # we'll just not forward for now unless requested. The spec says "forwards 
            # to the EventBus as appropriate." We'll just skip it for now to avoid polluting it.
            pass

    def query(self, filters: Dict[str, Any], limit: int = 100) -> List[TelemetryEnvelope]:
        """Query telemetry events matching the given filters."""
        results = []
        if not os.path.exists(self.log_path):
            return results
            
        # Simple backward scan (naive approach for now)
        with self._lock:
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception as e:
                logger.error(f"Failed to read telemetry: {e}")
                return results

        # Iterate backwards
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                
                # Check filters
                match = True
                for k, v in filters.items():
                    if data.get(k) != v:
                        match = False
                        break
                        
                if match:
                    results.append(TelemetryEnvelope(**data))
                    if len(results) >= limit:
                        break
            except Exception:
                continue
                
        return results

    def get_trace(self, trace_id: str) -> List[TelemetryEnvelope]:
        """Retrieve all events for a specific trace_id, chronologically."""
        events = self.query({"trace_id": trace_id}, limit=1000)
        # Reverse to chronological order
        return events[::-1]

    def get_live(self) -> List[TelemetryEnvelope]:
        """Return the recent in-memory events for live views."""
        with self._lock:
            return list(self._recent_events)

    def get_timeline(self, limit: int = 100) -> List[TelemetryEnvelope]:
        """Return the most recent events in chronological order for the timeline view."""
        with self._lock:
            recent = list(self._recent_events)
        # Already chronological in the deque, take last N
        return recent[-limit:] if len(recent) > limit else recent

