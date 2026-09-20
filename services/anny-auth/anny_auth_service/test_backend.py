from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .contracts import AuthorizationState


@dataclass
class TestTransaction:
    transaction_id: str
    runtime_id: str
    installation_id: str
    runtime_public_key_fingerprint: str
    onboarding_session_hash: str
    expires_at: datetime
    state: AuthorizationState = AuthorizationState.PENDING
    redeemed: bool = False
    grant: str | None = None


class TestTransactionStore:
    """Non-production deterministic backend for contract/load testing only."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl_seconds = ttl_seconds
        self._items: dict[str, TestTransaction] = {}
        self._lock = threading.RLock()

    def create(
        self,
        transaction_id: str,
        runtime_id: str,
        installation_id: str,
        runtime_public_key: str,
        onboarding_session_hash: str,
    ) -> TestTransaction:
        with self._lock:
            if transaction_id in self._items:
                raise ValueError("duplicate transaction_id")
            fingerprint = hashlib.sha256(
                runtime_public_key.encode("utf-8")
            ).hexdigest()
            tx = TestTransaction(
                transaction_id=transaction_id,
                runtime_id=runtime_id,
                installation_id=installation_id,
                runtime_public_key_fingerprint=fingerprint,
                onboarding_session_hash=onboarding_session_hash,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=self._ttl_seconds),
            )
            self._items[transaction_id] = tx
            return tx

    def get(self, transaction_id: str) -> TestTransaction | None:
        with self._lock:
            tx = self._items.get(transaction_id)
            if tx is None:
                return None
            if tx.expires_at <= datetime.now(timezone.utc):
                tx.state = AuthorizationState.EXPIRED
            return tx

    def authorize(self, transaction_id: str) -> TestTransaction:
        with self._lock:
            tx = self._items[transaction_id]
            if tx.expires_at <= datetime.now(timezone.utc):
                tx.state = AuthorizationState.EXPIRED
                return tx
            tx.state = AuthorizationState.AUTHORIZED
            return tx

    def redeem(
        self,
        transaction_id: str,
        runtime_id: str,
        installation_id: str,
        runtime_public_key: str,
        onboarding_session_hash: str,
    ) -> str:
        with self._lock:
            tx = self._items[transaction_id]
            if tx.expires_at <= datetime.now(timezone.utc):
                tx.state = AuthorizationState.EXPIRED
                raise ValueError("transaction expired")
            if tx.state is not AuthorizationState.AUTHORIZED:
                raise ValueError("transaction is not authorized")
            if tx.redeemed:
                raise ValueError("grant already redeemed")
            fingerprint = hashlib.sha256(
                runtime_public_key.encode("utf-8")
            ).hexdigest()
            if (
                tx.runtime_id != runtime_id
                or tx.installation_id != installation_id
                or tx.runtime_public_key_fingerprint != fingerprint
                or tx.onboarding_session_hash != onboarding_session_hash
            ):
                raise ValueError("runtime binding mismatch")
            tx.redeemed = True
            tx.state = AuthorizationState.REDEEMED
            tx.grant = "TEST-GRANT-" + secrets.token_urlsafe(18)
            return tx.grant


def new_test_transaction_id() -> str:
    return "test-" + secrets.token_hex(16)


_TEST_STORE = TestTransactionStore()


def get_test_store() -> TestTransactionStore:
    return _TEST_STORE
