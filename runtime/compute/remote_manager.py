"""Remote Compute Manager.

Orchestrates the lifecycle of a remote compute session:
DISCONNECTED → CONNECTING → WAITING_USER → AUDITING → READY

ANNY-RUNTIME activates remote compute.
The remote provider supplies whatever resource it can.
ANNY-RUNTIME observes, tests, and exposes capabilities.
ANNY consults the capability registry.

ANNY does NOT request hardware.
"""

import logging
import threading
import time
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from runtime.compute.models import RemoteSessionState, RemoteComputeSession
from runtime.compute.registry import RuntimeCapabilityRegistry
from runtime.compute.discovery import RuntimeResourceDiscovery

logger = logging.getLogger(__name__)


class RemoteComputeManager:
    """Manages the lifecycle of a remote compute session.

    Thread-safe. The connection flow runs in a background thread so
    the admin UI remains responsive.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = RemoteSessionState.DISCONNECTED
        self._session: Optional[RemoteComputeSession] = None
        self._transport = None
        self._resource_profile: Optional[Dict[str, Any]] = None
        self._capability_registry = RuntimeCapabilityRegistry()
        self._connect_thread: Optional[threading.Thread] = None
        self._cancel_requested = False
        self._error: Optional[str] = None
        self._attempt_id: Optional[str] = None
        self._attempts: list = []

    @property
    def state(self) -> RemoteSessionState:
        with self._lock:
            return self._state

    @property
    def session(self) -> Optional[RemoteComputeSession]:
        with self._lock:
            return self._session

    @property
    def resource_profile(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._resource_profile

    @property
    def capability_registry(self) -> RuntimeCapabilityRegistry:
        return self._capability_registry

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    def get_status(self) -> Dict[str, Any]:
        """Return a JSON-serializable status snapshot."""
        with self._lock:
            status = {
                "state": self._state.value,
                "provider": "google_colab",
                "session_id": self._session.session_id if self._session else None,
                "error": self._error,
                "attempt_id": self._attempt_id,
                "attempt_count": len(self._attempts),
            }
            if self._resource_profile:
                status["resources"] = {
                    "cpu": self._resource_profile.get("cpu"),
                    "cpu_count": self._resource_profile.get("cpu_count"),
                    "ram_gb": self._resource_profile.get("ram_gb"),
                    "gpu_present": self._resource_profile.get("gpu_present", False),
                    "gpu_name": self._resource_profile.get("gpu_name"),
                    "gpu_count": self._resource_profile.get("gpu_count"),
                    "vram_gb": self._resource_profile.get("vram_gb"),
                    "tpu_present": self._resource_profile.get("tpu_present", False),
                    "tpu_type": self._resource_profile.get("tpu_type"),
                    "cuda_available": self._resource_profile.get("cuda_available", False),
                    "cuda_version": self._resource_profile.get("cuda_version"),
                    "driver_version": self._resource_profile.get("driver_version"),
                }
            else:
                status["resources"] = None
            status["capabilities"] = self._capability_registry.to_dict()
            return status

    def connect(self) -> bool:
        """Start connecting to Google Colab in the background.

        Returns True if connection was initiated, False if already active.
        """
        with self._lock:
            if self._state not in (
                RemoteSessionState.DISCONNECTED,
                RemoteSessionState.FAILED,
                RemoteSessionState.LOST,
                RemoteSessionState.TERMINATED,
            ):
                logger.warning(f"Cannot connect: current state is {self._state.value}")
                return False

            self._state = RemoteSessionState.CONNECTING
            self._error = None
            self._cancel_requested = False
            self._attempt_id = uuid.uuid4().hex[:12]
            self._attempts.append({
                "attempt_id": self._attempt_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "failure_stage": None,
                "failure_reason": None,
            })

        self._connect_thread = threading.Thread(
            target=self._connect_worker,
            daemon=True,
            name="remote-compute-connect",
        )
        self._connect_thread.start()
        return True

    def disconnect(self) -> bool:
        """Disconnect and terminate the remote session."""
        with self._lock:
            if self._state == RemoteSessionState.DISCONNECTED:
                return True

            prev_state = self._state
            self._state = RemoteSessionState.TERMINATING

        # Terminate transport
        if self._transport:
            try:
                if self._session:
                    self._transport.terminate(self._session)
            except Exception as e:
                logger.warning(f"Error terminating transport: {e}")

        with self._lock:
            self._state = RemoteSessionState.DISCONNECTED
            self._session = None
            self._transport = None
            self._resource_profile = None
            self._capability_registry.clear()
            self._error = None

        logger.info("Remote compute session disconnected.")
        return True

    def reconnect(self) -> bool:
        """Disconnect and reconnect."""
        self.disconnect()
        return self.connect()

    def cancel(self) -> bool:
        """Cancel an in-progress connection."""
        with self._lock:
            if self._state not in (
                RemoteSessionState.CONNECTING,
                RemoteSessionState.WAITING_USER,
                RemoteSessionState.RUNTIME_CONNECTING,
                RemoteSessionState.AUDITING,
            ):
                return False
            self._cancel_requested = True
        return True

    def _connect_worker(self):
        """Background worker that runs the full connection flow."""
        attempt_id = self._attempt_id
        try:
            self._do_connect(attempt_id)
        except Exception as e:
            logger.error(f"Connection worker failed: {e}", exc_info=True)
            with self._lock:
                self._state = RemoteSessionState.FAILED
                self._error = str(e)
                self._record_attempt_failure(attempt_id, "WORKER", str(e))

    def _do_connect(self, attempt_id: str):
        """Execute the full connection flow."""
        # Check cancellation
        if self._cancel_requested:
            with self._lock:
                self._state = RemoteSessionState.DISCONNECTED
            return

        # Phase 1: Create transport
        with self._lock:
            self._state = RemoteSessionState.CONNECTING

        logger.info(f"[{attempt_id}] Creating BrowserColabTransport...")
        try:
            from runtime.compute.colab import BrowserColabTransport
            transport = BrowserColabTransport()
        except Exception as e:
            with self._lock:
                self._state = RemoteSessionState.FAILED
                self._error = f"Transport creation failed: {e}"
                self._record_attempt_failure(attempt_id, "TRANSPORT_INIT", str(e))
            return

        if self._cancel_requested:
            with self._lock:
                self._state = RemoteSessionState.DISCONNECTED
            return

        # Phase 2: Provision (this blocks waiting for user auth)
        with self._lock:
            self._state = RemoteSessionState.WAITING_USER

        logger.info(f"[{attempt_id}] Provisioning session (waiting for user authorization)...")
        try:
            context = {
                "session_name": f"anny-{attempt_id}",
                "transport_type": "browser",
            }
            session = transport.provision(context)
        except Exception as e:
            with self._lock:
                self._state = RemoteSessionState.FAILED
                self._error = f"Provisioning failed: {e}"
                self._record_attempt_failure(attempt_id, "PROVISION", str(e))
            return

        if session.state == RemoteSessionState.FAILED:
            error_msg = session.metadata.get("error", "Unknown provisioning error")
            with self._lock:
                self._state = RemoteSessionState.FAILED
                self._error = error_msg
                self._record_attempt_failure(attempt_id, "PROVISION", error_msg)
            return

        with self._lock:
            self._session = session
            self._transport = transport
            self._state = RemoteSessionState.AUDITING

        if self._cancel_requested:
            self.disconnect()
            return

        # Phase 3: Discovery
        logger.info(f"[{attempt_id}] Running resource discovery...")
        discovery = RuntimeResourceDiscovery()
        profile = discovery.discover(transport, session)

        with self._lock:
            self._resource_profile = profile

        # Phase 4: Populate capability registry
        logger.info(f"[{attempt_id}] Populating capability registry...")
        self._capability_registry.clear()
        self._capability_registry.from_resource_profile(profile)

        # Phase 5: Mark READY
        with self._lock:
            self._state = RemoteSessionState.READY
            self._error = None

        gpu_str = "GPU" if profile.get("gpu_present") else "CPU-only"
        tpu_str = ", TPU" if profile.get("tpu_present") else ""
        logger.info(f"[{attempt_id}] Remote runtime READY ({gpu_str}{tpu_str})")

    def _record_attempt_failure(self, attempt_id: str, stage: str, reason: str):
        """Record failure details on the current attempt."""
        for attempt in self._attempts:
            if attempt["attempt_id"] == attempt_id:
                attempt["failure_stage"] = stage
                attempt["failure_reason"] = reason
                break
