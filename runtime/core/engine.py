from enum import Enum, auto
from typing import Dict, Any, Optional
import os

from .config import RuntimeConfig
from .generation import RuntimeGeneration
from runtime.continuity.engine import ContinuityEngine
from runtime.continuity.mutation import RepositoryMutationContract
from runtime.continuity.reconciler import Reconciler
from runtime.control_plane import RuntimeControlPlaneClient
from runtime.evolution.manager import RuntimeEvolutionManager
from runtime.identity.runtime_identity import RuntimeIdentity


class RuntimeState(Enum):
    STARTING = auto()
    VERIFYING = auto()
    READY = auto()
    WAITING_FOR_SESSION = auto()
    DRAINING = auto()
    STOPPED = auto()
    ERROR = auto()
    ADMIN_MODE = auto()


class RuntimeEngine:
    """The main runtime core engine and Citizen lifecycle coordinator."""

    def __init__(self, config: RuntimeConfig):
        self._config = config
        self._state = RuntimeState.STOPPED
        self._generation = RuntimeGeneration(config.data_dir)
        self.bootstrap_report = None
        self.identity: Optional[RuntimeIdentity] = None
        self.reconciliation_status = "UNKNOWN"
        self.control_plane: Optional[RuntimeControlPlaneClient] = None
        self.evolution_manager: Optional[RuntimeEvolutionManager] = None

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def generation(self) -> RuntimeGeneration:
        return self._generation

    def startup(self, github_client=None, fabric_client=None) -> None:
        """Executes deterministic runtime startup without automatic evolution."""
        self._state = RuntimeState.STARTING
        try:
            # 1. Runtime identity is loaded before any external lifecycle message.
            self._load_identity()

            # 2. Recover durable generation and initialize local subsystems.
            self._generation.increment()
            self._init_subsystems()
            self.continuity_engine.load()

            # 3. Reconcile local activity against durable continuity before admission.
            self.reconciliation_status = Reconciler(self.continuity_engine).reconcile().value

            # 4. Execute the mandatory Three-Plane Bootstrap.
            from runtime.bootstrap.planes import ThreePlaneBootstrap
            bootstrap = ThreePlaneBootstrap(
                data_dir=self.config.data_dir,
                github_client=github_client,
                fabric_client=fabric_client,
                continuity_engine=self.continuity_engine,
                config=self._config,
            )
            self.bootstrap_report = bootstrap.resolve()
            self.bootstrap_report.reconciliation_status = self.reconciliation_status

            # 5. Bootstrap owns Fabric admission. Do not infer admission from identity.
            if self.bootstrap_report.anny_ready:
                self._state = RuntimeState.READY
                self._initialize_telemetry()
                self._emit_heartbeat()
                self._emit_receipt("bootstrap_ready")
                self._state = RuntimeState.WAITING_FOR_SESSION
            else:
                self._initialize_telemetry()
                self._emit_heartbeat()
                self._emit_receipt("bootstrap_blocked")
                self._state = RuntimeState.ADMIN_MODE
        except Exception:
            self._state = RuntimeState.ERROR
            raise

    def verify(self, github_client=None, fabric_client=None) -> None:
        """Manually trigger reconciliation + deterministic Three-Plane verification."""
        self._state = RuntimeState.VERIFYING
        try:
            if self.identity is None:
                self._load_identity()
            if getattr(self, 'continuity_engine', None) is None:
                self._init_subsystems()
            self.continuity_engine.load()
            self.reconciliation_status = Reconciler(self.continuity_engine).reconcile().value

            from runtime.bootstrap.planes import ThreePlaneBootstrap
            bootstrap = ThreePlaneBootstrap(
                data_dir=self.config.data_dir,
                github_client=github_client,
                fabric_client=fabric_client,
                continuity_engine=self.continuity_engine,
                config=self._config,
            )
            self.bootstrap_report = bootstrap.resolve()
            self.bootstrap_report.reconciliation_status = self.reconciliation_status
            self._initialize_telemetry()
            self._emit_heartbeat()
            self._emit_receipt("verification_ready" if self.bootstrap_report.anny_ready else "verification_blocked")
            self._state = RuntimeState.WAITING_FOR_SESSION if self.bootstrap_report.anny_ready else RuntimeState.ADMIN_MODE
        except Exception:
            self._state = RuntimeState.ERROR
            raise

    def prepare_evolution(self, descriptor: Dict[str, Any], artifact_source: str, verifier) -> Dict[str, Any]:
        """Verify and stage an evolution candidate; never commits or restarts the runtime."""
        if self.evolution_manager is None:
            self._init_subsystems()
        if self.bootstrap_report is None or not self.bootstrap_report.anny_ready:
            raise RuntimeError("evolution preparation requires an admitted runtime")
        return self.evolution_manager.prepare(descriptor, artifact_source, verifier)

    def shutdown(self) -> None:
        """Executes the runtime shutdown sequence."""
        self._state = RuntimeState.DRAINING
        self._flush_journal()
        self._persist_state()
        self._handle_active_executions()
        self._close_sessions()
        self._close_event_channels()
        self._state = RuntimeState.STOPPED

    def health_check(self) -> Dict[str, Any]:
        """Returns explicit local lifecycle and bootstrap evidence."""
        continuity = getattr(self, 'continuity_engine', None)
        continuity_status = continuity.status if continuity else {"state": "UNINITIALIZED"}
        report = self.bootstrap_report
        return {
            "status": "ok" if self._state not in (RuntimeState.ERROR,) else "error",
            "state": self._state.name,
            "generation": self._generation.current,
            "subsystems": {
                "identity": "loaded" if self.identity else "unavailable",
                "journal": continuity_status.get("state", "UNKNOWN"),
                "execution": "initialized",
            },
            "bootstrap": {
                "state": "READY" if report and report.anny_ready else "BLOCKED" if report else "UNVERIFIED",
                "runtime_id": report.runtime_id if report else (self.identity.runtime_id if self.identity else "UNKNOWN"),
                "fabric_node": report.fabric_node if report else "UNKNOWN",
                "admission": report.admission_status if report else "UNKNOWN",
                "reconciliation": self.reconciliation_status,
            },
        }

    def _load_identity(self) -> None:
        self.identity = RuntimeIdentity.load(self.config.data_dir)

    def _init_subsystems(self) -> None:
        self.continuity_engine = ContinuityEngine(self.config.data_dir)
        self.mutation_contract = RepositoryMutationContract(self.continuity_engine)
        self.evolution_manager = RuntimeEvolutionManager(self.config.data_dir)
        self.control_plane = RuntimeControlPlaneClient(
            self.config.control_plane_url,
            token=os.environ.get("ANNY_CONTROL_PLANE_TOKEN"),
        )

    def _initialize_telemetry(self) -> None:
        if self.control_plane is None:
            self.control_plane = RuntimeControlPlaneClient(
                self.config.control_plane_url,
                token=os.environ.get("ANNY_CONTROL_PLANE_TOKEN"),
            )

    def _telemetry_payload(self) -> Dict[str, Any]:
        report = self.bootstrap_report
        continuity = getattr(self, 'continuity_engine', None)
        continuity_status = continuity.status if continuity else {"state": "UNINITIALIZED"}
        return {
            "runtime_id": self.identity.runtime_id if self.identity else "UNKNOWN",
            "installation_id": self.identity.installation_id if self.identity else "UNKNOWN",
            "runtime_version": self.identity.runtime_version if self.identity else "UNKNOWN",
            "protocol_version": self.identity.protocol_version if self.identity else "UNKNOWN",
            "generation": self._generation.current,
            "runtime_state": self._state.name,
            "bootstrap_state": "READY" if report and report.anny_ready else "BLOCKED" if report else "UNVERIFIED",
            "admission": report.admission_status if report else "UNKNOWN",
            "continuity": continuity_status.get("state", "UNKNOWN"),
            "fabric_node": report.fabric_node if report else "UNKNOWN",
            "last_verified": report.completed_at if report else None,
            "reconciliation": self.reconciliation_status,
        }

    def _emit_heartbeat(self) -> None:
        if self.control_plane is None:
            return
        try:
            self.control_plane.heartbeat(self._telemetry_payload())
        except Exception:
            # Telemetry is best-effort and can never grant or remove local admission.
            pass

    def _emit_receipt(self, event: str) -> None:
        if self.control_plane is None:
            return
        try:
            payload = self._telemetry_payload()
            payload["event"] = event
            self.control_plane.receipt(payload)
        except Exception:
            pass

    def _flush_journal(self) -> None:
        if getattr(self, 'continuity_engine', None):
            self.continuity_engine.flush()

    def _persist_state(self) -> None:
        pass

    def _handle_active_executions(self) -> None:
        pass

    def _close_sessions(self) -> None:
        pass

    def _close_event_channels(self) -> None:
        pass
