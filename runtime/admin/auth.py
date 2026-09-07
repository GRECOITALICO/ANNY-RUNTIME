"""Admin session authentication for the ANNY Runtime browser panel.

Uses a one-time bootstrap token printed to the console for initial login.
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
from typing import Dict, Optional

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

    def generate_bootstrap_token(self) -> str:
        """Generate a one-time bootstrap token for initial admin login.
        This token is printed to the console and used for first authentication.
        """
        self._bootstrap_token = secrets.token_urlsafe(32)
        token_path = self.data_dir / "admin_bootstrap_token"
        token_path.write_text(self._bootstrap_token)
        os.chmod(token_path, 0o600)
        logger.info("=" * 60)
        logger.info("ANNY RUNTIME ADMIN BOOTSTRAP TOKEN")
        logger.info(f"Token: {self._bootstrap_token}")
        logger.info("Use this token to log in at http://127.0.0.1:<port>/login")
        logger.info("=" * 60)
        return self._bootstrap_token

    def load_bootstrap_token(self) -> Optional[str]:
        """Load existing bootstrap token from disk."""
        token_path = self.data_dir / "admin_bootstrap_token"
        if token_path.exists():
            self._bootstrap_token = token_path.read_text().strip()
            return self._bootstrap_token
        return None

    def authenticate(self, token: str) -> Optional[AdminSession]:
        """Authenticate using the bootstrap token. Returns a new admin session."""
        if not self._bootstrap_token:
            self.load_bootstrap_token()

        if not self._bootstrap_token or not secrets.compare_digest(
                token, self._bootstrap_token):
            logger.warning("Admin authentication failed: invalid bootstrap token")
            return None

        now = datetime.now(timezone.utc)
        session = AdminSession(
            admin_session_id=secrets.token_hex(16),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.ttl_seconds)).isoformat(),
            runtime_id=self.runtime_id,
            scope="ADMIN",
            principal="local-admin",
            csrf_token=generate_csrf_token()
        )
        self._sessions[session.admin_session_id] = session
        self._persist_session(session)
        logger.info(f"Admin session created: {session.admin_session_id}")
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
