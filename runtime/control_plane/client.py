"""Best-effort Control Plane telemetry for ANNY Runtime.

This client deliberately does not participate in Fabric admission. Registration,
heartbeat, and receipt delivery may fail without changing local runtime safety.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ControlPlaneResponse:
    ok: bool
    status: Optional[int] = None
    body: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class RuntimeControlPlaneClient:
    """HTTPS JSON client for telemetry/control-plane lifecycle events."""

    def __init__(self, base_url: Optional[str], token: Optional[str] = None, timeout: int = 5):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _post(self, path: str, payload: Dict[str, Any]) -> ControlPlaneResponse:
        if not self.enabled:
            return ControlPlaneResponse(ok=False, error="CONTROL_PLANE_NOT_CONFIGURED")
        url = f"{self.base_url}{path}"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ssl.create_default_context()) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw) if raw else None
                return ControlPlaneResponse(ok=200 <= resp.status < 300, status=resp.status, body=parsed)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return ControlPlaneResponse(ok=False, error=type(exc).__name__)

    def register_after_birth(self, payload: Dict[str, Any]) -> ControlPlaneResponse:
        return self._post("/api/ingest/register", payload)

    def heartbeat(self, payload: Dict[str, Any]) -> ControlPlaneResponse:
        return self._post("/api/ingest/heartbeat", payload)

    def receipt(self, payload: Dict[str, Any]) -> ControlPlaneResponse:
        return self._post("/api/ingest/receipt", payload)
