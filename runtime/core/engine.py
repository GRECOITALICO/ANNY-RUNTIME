from enum import Enum, auto
from typing import Dict, Any
from pathlib import Path

from .config import RuntimeConfig
from .generation import RuntimeGeneration
from runtime.continuity.engine import ContinuityEngine
from runtime.continuity.mutation import RepositoryMutationContract
from runtime.continuity.reconciler import Reconciler


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
    """The main runtime core engine."""

    def __init__(self, config: RuntimeConfig):
        self._config = config
        self._state = RuntimeState.STOPPED
        self._generation = RuntimeGeneration(config.data_dir)
        self.bootstrap_report = None
        
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
        """Executes the runtime startup sequence."""
        import json
        import logging
        from datetime import datetime, timezone
        
        logger = logging.getLogger(__name__)
        
        # Read the prior durable state before writing this generation's active
        # checkpoint.  Otherwise every startup would overwrite the evidence it
        # is supposed to assess.
        previous_clean = self._load_previous_clean_state()

        # 1. RuntimeGeneration.load() and state=STARTING
        self._state = RuntimeState.STARTING
        self._generation.increment()
        
        # 2. Persist recovery checkpoint (clean_shutdown = false)
        self._persist_state(clean_shutdown=False)
        
        try:
            # 3. Initialize continuity
            self._init_subsystems()
            
            # 4. Load continuity
            self.continuity_engine.load()
            
            # 5. Detect clean vs abnormal previous termination.  The value was
            # captured before the active checkpoint above was persisted.
            if not previous_clean:
                logger.warning("Abnormal termination detected! Requires reconciliation.")
                # We do not assume success or automatically erase evidence.
            
            # 7. Run Three-Plane Bootstrap
            from runtime.bootstrap.planes import ThreePlaneBootstrap
            bootstrap = ThreePlaneBootstrap(
                data_dir=self.config.data_dir,
                github_client=github_client,
                fabric_client=fabric_client,
                continuity_engine=self.continuity_engine,
                config=self._config,
            )
            self.bootstrap_report = bootstrap.resolve()
            
            # 8. Derive current runtime state
            if self.bootstrap_report.anny_ready:
                self._state = RuntimeState.WAITING_FOR_SESSION
            else:
                self._state = RuntimeState.ADMIN_MODE
                
            # Update state file to reflect derived state (but still active, so clean_shutdown=False)
            self._persist_state(clean_shutdown=False)
                
        except Exception as e:
            self._state = RuntimeState.ERROR
            self._persist_state(clean_shutdown=False)
            raise e

    def verify(self, github_client=None, fabric_client=None) -> None:
        """Manually trigger the deterministic verification pipeline."""
        self._state = RuntimeState.VERIFYING
        self._persist_state(clean_shutdown=False)
        
        try:
            from runtime.bootstrap.planes import ThreePlaneBootstrap
            bootstrap = ThreePlaneBootstrap(
                data_dir=self.config.data_dir,
                github_client=github_client,
                fabric_client=fabric_client,
                continuity_engine=getattr(self, 'continuity_engine', None),
                config=self._config,
            )
            self.bootstrap_report = bootstrap.resolve()
            
            if self.bootstrap_report.anny_ready:
                self._state = RuntimeState.WAITING_FOR_SESSION
            else:
                self._state = RuntimeState.ADMIN_MODE
                
            self._persist_state(clean_shutdown=False)
                
        except Exception as e:
            self._state = RuntimeState.ERROR
            self._persist_state(clean_shutdown=False)
            raise e

    def shutdown(self, drain_timeout_seconds: float | None = None) -> Dict[str, Any]:
        """Request a logical Runtime shutdown; never claim process termination.

        The engine can fence new Runtime work and persist a drain observation,
        but it has no process supervisor or worker cancellation interface.
        Consequently a queued/running execution keeps the engine in DRAINING;
        an unavailable execution registry yields an explicitly unverified
        shutdown marker rather than a synthetic successful drain.
        """
        if self._state == RuntimeState.DRAINING:
            return {
                "shutdown_state": "DRAINING_ALREADY_REQUESTED",
                "process_state": "NOT_IMPLEMENTED",
                "clean_shutdown": False,
            }
        if self._state == RuntimeState.STOPPED:
            return {
                "shutdown_state": "ALREADY_STOPPED",
                "process_state": "NOT_IMPLEMENTED",
                "clean_shutdown": False,
            }

        # 1. DRAINING
        self._state = RuntimeState.DRAINING
        self._persist_state(clean_shutdown=False)
        
        # 2. Stop accepting new work by entering DRAINING state.
        
        # 3. Handle active executions
        drain = self._handle_active_executions()
        
        # 4. Close sessions
        self._close_sessions()
        
        # 5. Close event channels
        self._close_event_channels()
        
        # 6. Flush continuity
        self._flush_journal()
        
        # A Runtime with outstanding work must remain in DRAINING.  There is
        # no implementation here that cancels or waits for workers.
        if drain["active_count"]:
            self._persist_state(clean_shutdown=False)
            return {
                "shutdown_state": (
                    "TIMEOUT_ACTIVE_EXECUTIONS"
                    if drain_timeout_seconds is not None
                    else "DRAINING_ACTIVE_EXECUTIONS"
                ),
                "process_state": "NOT_IMPLEMENTED",
                "clean_shutdown": False,
                "timeout_seconds": drain_timeout_seconds,
                "active_executions": drain,
            }

        # STOPPED here means the in-process engine state only.  No physical
        # process restart or termination has been observed or requested.
        self._state = RuntimeState.STOPPED
        clean_shutdown = drain["registry_state"] == "AVAILABLE"
        self._persist_state(clean_shutdown=clean_shutdown)
        return {
            "shutdown_state": "ENGINE_STOPPED" if clean_shutdown else "ENGINE_STOPPED_UNVERIFIED_DRAIN",
            "process_state": "NOT_IMPLEMENTED",
            "clean_shutdown": clean_shutdown,
            "active_executions": drain,
        }

    def health_check(self) -> Dict[str, Any]:
        """Report observed subsystem health without synthetic success."""
        checks = {}
        identity_dir = Path(self.config.data_dir) / "identity"
        identity_file = identity_dir / "runtime_identity.json"
        private_key = identity_dir / "private_key.pem"
        checks["identity"] = "ok" if identity_file.is_file() and private_key.is_file() else "not_ready"
        continuity = getattr(self, "continuity_engine", None)
        checks["journal"] = "ok" if continuity is not None else "not_initialized"
        execution_manager = getattr(self, "execution_manager", None)
        if execution_manager is None:
            checks["execution"] = "not_initialized"
        elif not hasattr(execution_manager, "get_all_executions"):
            checks["execution"] = "unknown"
        else:
            checks["execution"] = "ok"

        values = set(checks.values())
        overall = "ok" if values == {"ok"} else ("unknown" if "unknown" in values else "degraded")
        return {
            "status": overall,
            "engine_state": self._state.name,
            "process_state": "UNVERIFIED",
            "generation": self._generation.current,
            "subsystems": checks,
        }

    # --- Stubs for internal processes ---

    def _init_subsystems(self) -> None:
        self.continuity_engine = ContinuityEngine(self.config.data_dir)
        self.mutation_contract = RepositoryMutationContract(self.continuity_engine)

    def _flush_journal(self) -> None:
        if getattr(self, 'continuity_engine', None):
            self.continuity_engine.flush()

    def _persist_state(self, clean_shutdown: bool) -> None:
        import json
        import os
        from datetime import datetime, timezone
        
        state_file = Path(self.config.data_dir) / "engine_state.json"
        temp_file = state_file.with_suffix('.tmp')
        
        data = {
            "schema_version": 1,
            "generation": self._generation.current,
            "state": self._state.name,
            "clean_shutdown": clean_shutdown,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with open(temp_file, "w") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
            
        os.replace(temp_file, state_file)

    def _handle_active_executions(self) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        execution_manager = getattr(self, "execution_manager", None)
        if execution_manager is None:
            logger.warning("Active execution registry unavailable; shutdown drain state is UNKNOWN.")
            return {
                "registry_state": "UNAVAILABLE",
                "active_count": 0,
                "classification": "UNKNOWN",
            }

        active_states = {"QUEUED", "RUNNING"}
        classifications = {"COMPLETED": 0, "CANCELLED": 0, "FENCED": 0, "ORPHANED_REQUIRES_RECONCILIATION": 0}
        for exec_obj in execution_manager.get_all_executions():
            state = getattr(getattr(exec_obj, "status", None), "value", None)
            if state in active_states:
                classifications["ORPHANED_REQUIRES_RECONCILIATION"] += 1

        logger.info(f"Drained active executions: {classifications}")
        active_count = classifications["ORPHANED_REQUIRES_RECONCILIATION"]
        return {
            "registry_state": "AVAILABLE",
            "active_count": active_count,
            "classification": "DRAINED" if active_count == 0 else "REQUIRES_RECONCILIATION",
            "classifications": classifications,
        }

    def _load_previous_clean_state(self) -> bool:
        """Return only a durable clean marker; absent/unreadable is unverified."""
        import json
        import logging

        state_file = Path(self.config.data_dir) / "engine_state.json"
        if not state_file.exists():
            return False
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("clean_shutdown", False))
        except (OSError, ValueError, TypeError) as exc:
            logging.getLogger(__name__).warning("Unable to read prior engine state: %s", exc)
            return False

    def _close_sessions(self) -> None:
        import logging
        logging.getLogger(__name__).info("Closing sessions...")

    def _close_event_channels(self) -> None:
        import logging
        logging.getLogger(__name__).info("Closing event channels...")
