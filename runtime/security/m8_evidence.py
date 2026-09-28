"""Local durable M8 evidence sink with secret-safe serialization."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            low = str(key).lower()
            if any(marker in low for marker in ("token", "secret", "password", "credential", "private_key", "authorization")):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _safe(child)
        return result
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class M8EvidenceStore:
    def __init__(self, data_dir: str) -> None:
        self.root = Path(data_dir) / "evidence" / "m8"
        self.root.mkdir(parents=True, exist_ok=True)

    def record(self, evidence_type: str, payload: Dict[str, Any]) -> Path:
        safe_payload = _safe(payload)
        safe_payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
        target = self.root / f"{evidence_type}.json"
        fd, tmp_name = tempfile.mkstemp(prefix=".m8-", dir=str(self.root), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(safe_payload, handle, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return target
