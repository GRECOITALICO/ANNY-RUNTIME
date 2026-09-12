"""Distributed TraceContext for telemetry correlation.

Provides propagation of trace_id and span_id across process boundaries
and async boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional


def _generate_id(prefix: str) -> str:
    """Generate a compact hex UUID with a prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


@dataclass
class TraceContext:
    """Represents a distributed trace context."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None

    @classmethod
    def new_trace(cls) -> "TraceContext":
        """Create a new root trace context."""
        return cls(
            trace_id=_generate_id("trc"),
            span_id=_generate_id("spn"),
            parent_span_id=None,
        )

    def child_span(self) -> "TraceContext":
        """Create a child span context within this trace."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=_generate_id("spn"),
            parent_span_id=self.span_id,
        )
