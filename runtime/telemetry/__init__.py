"""ANNY Universe Telemetry Foundation.

Provides transversal observability across the ANNY Universe through a unified
TelemetryEnvelope, distributed TraceContext, and a TelemetryCollector that
persists events to append-only JSONL storage.
"""

from runtime.telemetry.telemetry import TelemetryEnvelope
from runtime.telemetry.collector import TelemetryCollector
from runtime.telemetry.context import TraceContext
from runtime.telemetry.scrubber import scrub_metadata

__all__ = [
    "TelemetryEnvelope",
    "TelemetryCollector",
    "TraceContext",
    "scrub_metadata",
]
