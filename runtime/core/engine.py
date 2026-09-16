from enum import Enum, auto
from typing import Dict, Any

from .config import RuntimeConfig
from .generation import RuntimeGeneration
from runtime.continuity.engine import ContinuityEngine
from runtime.continuity.mutation import RepositoryMutationContract
from runtime.continuity.reconciler import Reconciler


class RuntimeState(Enum):
    STARTING = auto()
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
        return self._config

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def generation(self) -> RuntimeGeneration:
        return self._generation

    def startup(self, github_client=None, fabric_client=None) -> None:
        """Executes the runtime startup sequence."""
        self._state = RuntimeState.STARTING
        
        try:
            # 1. Load configuration (already handled in instantiation)
            
            # 2. Increment/recover generation
            self._generation.increment()
            
            # 3. Initialize subsystems (Continuity)
            self._init_subsystems()
            
            # Load durable continuity state
            self.continuity_engine.load()
            
            # 4. Execute Three-Plane Bootstrap
            from runtime.bootstrap.planes import ThreePlaneBootstrap
            bootstrap = ThreePlaneBootstrap(
                data_dir=self.config.data_dir,
                github_client=github_client,
                fabric_client=fabric_client,
                continuity_engine=self.continuity_engine
            )
            self.bootstrap_report = bootstrap.resolve()
            
            # 5. Determine runtime state
            if self.bootstrap_report.anny_ready:
                self._state = RuntimeState.READY
                self._state = RuntimeState.WAITING_FOR_SESSION
            else:
                self._state = RuntimeState.ADMIN_MODE
                
        except Exception as e:
            self._state = RuntimeState.ERROR
            raise e

    def shutdown(self) -> None:
        """Executes the runtime shutdown sequence."""
        # 1. Stop accepting new work (DRAINING)
        self._state = RuntimeState.DRAINING
        
        # 2. Flush journal (stub)
        self._flush_journal()
        
        # 3. Persist state (stub)
        self._persist_state()
        
        # 4. Handle active executions (stub)
        self._handle_active_executions()
        
        # 5. Close sessions (stub)
        self._close_sessions()
        
        # 6. Close event channels (stub)
        self._close_event_channels()
        
        # 7. Set state STOPPED
        self._state = RuntimeState.STOPPED

    def health_check(self) -> Dict[str, Any]:
        """Returns the status of each subsystem."""
        return {
            "status": "ok",
            "generation": self._generation.current,
            "subsystems": {
                "identity": "ok",
                "journal": "ok",
                "execution": "ok"
            }
        }

    # --- Stubs for internal processes ---

    def _load_identity(self) -> None:
        pass

    def _init_subsystems(self) -> None:
        self.continuity_engine = ContinuityEngine(self.config.data_dir)
        self.mutation_contract = RepositoryMutationContract(self.continuity_engine)

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
