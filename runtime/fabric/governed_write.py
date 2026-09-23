"""Fail-closed boundary for Repository Fabric authoritative writes.

This module deliberately has no GitHub fallback.  GitHub API access can be a
transport implementation, but is not itself proof of Fabric authority.
"""
from __future__ import annotations

from typing import Callable, Optional

from .models import GovernedWriteReceipt, GovernedWriteRequest, GovernedWriteState


class GovernedWriteError(ValueError):
    pass


AuthoritativeTransport = Callable[[GovernedWriteRequest], GovernedWriteReceipt]


class GovernedFabricWriteBoundary:
    def __init__(self, authoritative_transport: Optional[AuthoritativeTransport] = None):
        self._authoritative_transport = authoritative_transport

    @staticmethod
    def _validate(request: GovernedWriteRequest, current_generation: int) -> Optional[str]:
        required = (
            request.request_id, request.runtime_id, request.tenant_id,
            request.account_id, request.project_id, request.repository_scope,
            request.authorization_ref, request.policy_ref, request.evidence_ref,
            request.operation, request.payload_digest,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            return "REQUIRED_GOVERNANCE_BINDING_MISSING"
        if request.generation != current_generation:
            return "STALE_GENERATION"
        return None

    def submit(self, request: GovernedWriteRequest, *, current_generation: int) -> GovernedWriteReceipt:
        violation = self._validate(request, current_generation)
        if violation:
            return GovernedWriteReceipt(
                receipt_id=f"blocked:{request.request_id}", request_id=request.request_id,
                state=GovernedWriteState.BLOCKED, reason=violation,
            )
        if self._authoritative_transport is None:
            return GovernedWriteReceipt(
                receipt_id=f"not-executed:{request.request_id}", request_id=request.request_id,
                state=GovernedWriteState.NOT_EXECUTED,
                reason="AUTHORITATIVE_FABRIC_TRANSPORT_UNAVAILABLE",
            )
        receipt = self._authoritative_transport(request)
        if not isinstance(receipt, GovernedWriteReceipt) or receipt.request_id != request.request_id:
            raise GovernedWriteError("AUTHORITATIVE_RECEIPT_CORRELATION_INVALID")
        if receipt.state is GovernedWriteState.SUCCEEDED and not (
            receipt.authoritative_operation_id and receipt.evidence_ref
        ):
            raise GovernedWriteError("AUTHORITATIVE_SUCCESS_RECEIPT_INCOMPLETE")
        return receipt
