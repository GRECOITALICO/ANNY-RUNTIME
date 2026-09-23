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
            
            # 5. Inspect previous engine_state
            state_file = Path(self.config.data_dir) / "engine_state.json"
            previous_clean = True
            if state_file.exists():
                try:
                    with open(state_file, "r") as f:
                        state_data = json.load(f)
                        previous_clean = state_data.get("clean_shutdown", False)
                        logger.info(f"Recovered previous engine state: {state_data}")
                except Exception as e:
                    logger.error(f"Failed to load engine_state.json: {e}")
                    previous_clean = False
            
            # 6. Detect clean vs abnormal previous termination
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

    def shutdown(self) -> None:
        """Executes the runtime shutdown sequence."""
        # 1. DRAINING
        self._state = RuntimeState.DRAINING
        
        # 2. Stop accepting new work by entering DRAINING state.
        
        # 3. Handle active executions
        self._handle_active_executions()
        
        # 4. Close sessions
        self._close_sessions()
        
        # 5. Close event channels
        self._close_event_channels()
        
        # 6. Flush continuity
        self._flush_journal()
        
        # 7. STOPPED
        self._state = RuntimeState.STOPPED
        
        # 8. Atomic engine_state persistence
        self._persist_state(clean_shutdown=True)

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
        checks["execution"] = "ok" if execution_manager is not None else "not_initialized"

        values = set(checks.values())
        overall = "ok" if values == {"ok"} else ("unknown" if "unknown" in values else "degraded")
        return {
            "status": overall,
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

    def _handle_active_executions(self) -> None:
        import logging
        logger = logging.getLogger(__name__)
        execution_manager = getattr(self, "execution_manager", None)
        if execution_manager is None:
            logger.warning("Active execution registry unavailable; shutdown drain state is UNKNOWN.")
            return

        active_states = {"QUEUED", "RUNNING"}
        classifications = {"COMPLETED": 0, "CANCELLED": 0, "FENCED": 0, "ORPHANED_REQUIRES_RECONCILIATION": 0}
        for exec_obj in execution_manager.get_all_executions():
            state = getattr(getattr(exec_obj, "status", None), "value", None)
            if state in active_states:
                classifications["ORPHANED_REQUIRES_RECONCILIATION"] += 1

        logger.info(f"Drained active executions: {classifications}")

    def _close_sessions(self) -> None:
        import logging
        logging.getLogger(__name__).info("Closing sessions...")

    def _close_event_channels(self) -> None:
        import logging
        logging.getLogger(__name__).info("Closing event channels...")
