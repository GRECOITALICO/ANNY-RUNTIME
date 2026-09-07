"""Admin audit log — append-only record of all administrative actions.

Never stores credentials. Records session_id, action, principal, result.
"""
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AdminAuditEntry:
    """A single admin audit log entry. Never contains credentials."""
    admin_session_id: str
    action: str
    timestamp: str
    runtime_id: str
    principal: str
    result: str
    details: Optional[str] = None


class AdminAuditLog:
    """Append-only audit log for administrative actions."""

    # Known action types
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    GITHUB_CONNECT = "GITHUB_CONNECT"
    GITHUB_DISCONNECT = "GITHUB_DISCONNECT"
    GITHUB_VALIDATE = "GITHUB_VALIDATE"
    FABRIC_RECONNECT = "FABRIC_RECONNECT"
    UPDATE_CHECK = "UPDATE_CHECK"
    UPDATE_INSTALL = "UPDATE_INSTALL"
    RUNTIME_RESTART = "RUNTIME_RESTART"
    DIAGNOSTICS_RUN = "DIAGNOSTICS_RUN"

    def __init__(self, data_dir: str, runtime_id: str):
        self.data_dir = Path(data_dir)
        self.runtime_id = runtime_id
        self.log_path = self.data_dir / "admin_audit.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def record(self, session_id: str, action: str, principal: str,
               result: str, details: str = None) -> AdminAuditEntry:
        """Record an admin action to the audit log."""
        entry = AdminAuditEntry(
            admin_session_id=session_id,
            action=action,
            timestamp=datetime.now(timezone.utc).isoformat(),
            runtime_id=self.runtime_id,
            principal=principal,
            result=result,
            details=details
        )
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(asdict(entry)) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit entry: {e}")
        return entry

    def read_recent(self, count: int = 50) -> List[AdminAuditEntry]:
        """Read the most recent audit entries."""
        entries = []
        if not self.log_path.exists():
            return entries
        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
            for line in lines[-count:]:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    entries.append(AdminAuditEntry(**data))
        except Exception as e:
            logger.error(f"Failed to read audit log: {e}")
        return entries
