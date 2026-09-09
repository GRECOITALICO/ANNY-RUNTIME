"""Admin session authentication for the ANNY Runtime browser panel.

Uses a local admin session for authenticated access.
Admin sessions are separate from ANNY session tokens and GitHub credentials.
Sessions expire after a configurable TTL (default 30 minutes).
"""
import json
import os
import secrets
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Any

from runtime.admin.csrf import generate_csrf_token

logger = logging.getLogger(__name__)


@dataclass
class AdminSession:
    """Represents an authenticated admin browser session."""
    admin_session_id: str
    issued_at: str
    expires_at: str
    runtime_id: str
    scope: str
    principal: str
    csrf_token: str


class AdminSessionManager:
    """Manages admin browser sessions with expiry and persistence.

    Admin sessions are COMPLETELY SEPARATE from:
    - GitHub credentials
    - ANNY session tokens
    - Runtime Fabric credentials
    """

    def __init__(self, data_dir: str, runtime_id: str, ttl_seconds: int = 1800):
        self.data_dir = Path(data_dir)
        self.runtime_id = runtime_id
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, AdminSession] = {}
        self._bootstrap_token: Optional[str] = None
        self._sessions_dir = self.data_dir / "admin_sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, principal: str = "local-admin") -> AdminSession:
        now = datetime.now(timezone.utc)
        session = AdminSession(
            admin_session_id=secrets.token_hex(16),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.ttl_seconds)).isoformat(),
            runtime_id=self.runtime_id,
            scope="ADMIN",
            principal=principal,
            csrf_token=generate_csrf_token()
        )
        self._sessions[session.admin_session_id] = session
        self._persist_session(session)
        logger.info(f"Admin session created: {session.admin_session_id}")
        return session

    def create_first_run_session(self) -> AdminSession:
        """Create a restricted session specifically for onboarding.
        
        Duration: 30 minutes.
        Scope: ONBOARDING_ONLY
        Revocation: Occurs manually upon successful setup or naturally via TTL.
        """
        now = datetime.now(timezone.utc)
        session = AdminSession(
            admin_session_id=secrets.token_hex(16),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=1800)).isoformat(),
            runtime_id=self.runtime_id,
            scope="ONBOARDING_ONLY",
            principal="local-first-run",
            csrf_token=generate_csrf_token()
        )
        self._sessions[session.admin_session_id] = session
        # Do not persist first run session to disk to keep it ephemeral
        logger.info(f"First-run session created: {session.admin_session_id}")
        return session

    def validate(self, session_id: str) -> Optional[AdminSession]:
        """Validate an admin session by ID. Returns None if invalid/expired."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(session.expires_at)
        if now >= expires:
            logger.info(f"Admin session expired: {session_id}")
            self.destroy(session_id)
            return None

        return session

    def destroy(self, session_id: str) -> None:
        """Destroy an admin session."""
        self._sessions.pop(session_id, None)
        session_file = self._sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
        logger.info(f"Admin session destroyed: {session_id}")

    def _persist_session(self, session: AdminSession) -> None:
        """Persist session to disk for recovery."""
        path = self._sessions_dir / f"{session.admin_session_id}.json"
        with open(path, 'w') as f:
            json.dump(asdict(session), f)

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of cleaned sessions."""
        now = datetime.now(timezone.utc)
        expired = []
        for sid, session in self._sessions.items():
            if now >= datetime.fromisoformat(session.expires_at):
                expired.append(sid)
        for sid in expired:
            self.destroy(sid)
        return len(expired)
