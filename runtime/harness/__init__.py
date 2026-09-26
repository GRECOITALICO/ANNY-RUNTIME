"""Governed ANNY Harness boundary.

The Harness validates an ANNY intent against the canonical Runtime capability
registry and ExecutionContext before execution.
"""

from runtime.harness.dispatcher import (
    DispatchStatus,
    FailureCode,
    HarnessDispatchRequest,
    HarnessDispatchDecision,
    HarnessExecutionHandoff,
    HarnessResultEnvelope,
    HarnessDispatcher,
)

__all__ = [
    "DispatchStatus",
    "FailureCode",
    "HarnessDispatchRequest",
    "HarnessDispatchDecision",
    "HarnessExecutionHandoff",
    "HarnessResultEnvelope",
    "HarnessDispatcher",
]
