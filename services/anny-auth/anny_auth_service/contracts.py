from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AuthorizationState(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    REDEEMED = "REDEEMED"


@dataclass(frozen=True)
class RuntimeAuthorizationRequest:
    transaction_id: str
    nonce: str
    runtime_id: str
    installation_id: str
    runtime_public_key: str
    runtime_signature: str
    onboarding_session_hash: str
    csrf_token_hash: str
    return_origin: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthorizationTransaction:
    transaction_id: str
    runtime_id: str
    installation_id: str
    runtime_public_key_fingerprint: str
    onboarding_session_hash: str
    state: AuthorizationState
    expires_at: datetime
    one_time_redeemed: bool = False
