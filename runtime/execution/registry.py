import uuid
import os
import json
import tempfile
import dataclasses
from typing import List, Optional, Dict, Any
from .models import (
    ModelDefinition, ModelState, ModelCapabilityBinding,
    HardwareProfile, ModelPerformanceProfile, EvaluationRecord
)

class RegistryRecoveryRequired(RuntimeError):
    """Raised when durable registry state is corrupted and explicit recovery is required."""


class ModelRegistry:
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self._models: Dict[str, ModelDefinition] = {}
        self._bindings: List[ModelCapabilityBinding] = []
        self._hardware = HardwareProfile(
            cpu="UNKNOWN",
            cores="UNKNOWN",
            ram="UNKNOWN",
            gpu_present="UNKNOWN",
            gpu_vendor="UNKNOWN",
            gpu_memory="UNKNOWN",
            storage_available="UNKNOWN",
            os="UNKNOWN",
            python_version="UNKNOWN"
        )
        self._performance: Dict[str, ModelPerformanceProfile] = {}
        self._evaluations: List[EvaluationRecord] = []
        
        if self.storage_path:
            recovery_path = f"{self.storage_path}.recovery.json"

            # A durable recovery marker has precedence over normal bootstrap.
            # Until an explicit, evidence-backed authority clears the marker,
            # the registry must remain blocked rather than synthesizing trust.
            if os.path.exists(recovery_path):
                raise RegistryRecoveryRequired(
                    f"Model registry recovery is required: {recovery_path}"
                )

            if os.path.exists(self.storage_path):
                try:
                    self._load_from_disk()
                except Exception as e:
                    import hashlib
                    import shutil
                    from datetime import datetime, timezone
                    import logging
                    logger = logging.getLogger(__name__)

                    recovery_timestamp = datetime.now(timezone.utc).isoformat()
                    quarantine_path = (
                        f"{self.storage_path}.quarantine."
                        f"{int(datetime.now(timezone.utc).timestamp())}"
                    )

                    original_hash = "UNKNOWN"
                    try:
                        with open(self.storage_path, "rb") as f:
                            original_hash = hashlib.sha256(f.read()).hexdigest()
                    except Exception:
                        pass

                    try:
                        shutil.move(self.storage_path, quarantine_path)
                    except Exception as move_err:
                        logger.error(
                            f"Failed to quarantine corrupted registry: {move_err}"
                        )
                        raise RegistryRecoveryRequired(
                            "Registry is corrupted and could not be quarantined"
                        ) from move_err

                    recovery_reason = f"CORRUPTED_REGISTRY: {str(e)}"
                    marker = {
                        "version": "1.0",
                        "state": "BLOCKED_OR_UNKNOWN",
                        "original_registry_path": self.storage_path,
                        "quarantine_path": quarantine_path,
                        "original_sha256": original_hash,
                        "recovery_timestamp": recovery_timestamp,
                        "recovery_reason": recovery_reason,
                        "reconstruction_required": True,
                        "verification_required": True,
                    }
                    marker_dir = os.path.dirname(recovery_path)
                    if marker_dir:
                        os.makedirs(marker_dir, exist_ok=True)
                    with open(recovery_path, "w") as f:
                        json.dump(marker, f, indent=2)

                    logger.warning(
                        "ModelRegistry blocked after corruption: "
                        f"original_hash={original_hash}, "
                        f"quarantine_path={quarantine_path}, "
                        f"recovery_timestamp={recovery_timestamp}, "
                        f"recovery_reason={recovery_reason}"
                    )
                    raise RegistryRecoveryRequired(
                        f"Corrupted model registry quarantined; explicit recovery required: "
                        f"{recovery_path}"
                    ) from e
            else:
                # First bootstrap is allowed only when no durable registry or
                # recovery marker exists. This is not corruption recovery.
                self._register_initial_models()
                self._register_initial_bindings()
                self._save_to_disk()
        else:
            self._register_initial_models()
            self._register_initial_bindings()
            self._save_to_disk()

    class _EnumEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, ModelState):
                return obj.value
            return super().default(obj)

    def _save_to_disk(self):
        if not self.storage_path:
            return
            
        data = {
            "version": "1.0",
            "models": [dataclasses.asdict(m) for m in self._models.values()],
            "bindings": [dataclasses.asdict(b) for b in self._bindings],
            "hardware": dataclasses.asdict(self._hardware),
            "performance": {k: dataclasses.asdict(v) for k, v in self._performance.items()},
        }
        
        dir_name = os.path.dirname(self.storage_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".registry-", suffix=".tmp")
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, cls=self._EnumEncoder, indent=2)
            os.replace(temp_path, self.storage_path)
        except Exception:
            os.unlink(temp_path)
            raise

    def _load_from_disk(self):
        with open(self.storage_path, 'r') as f:
            data = json.load(f)
            
        if data.get("version") != "1.0":
            raise ValueError("Unsupported registry schema version")
            
        self._models.clear()
        for m_dict in data.get("models", []):
            m_dict["status"] = ModelState(m_dict["status"])
            model = ModelDefinition(**m_dict)
            self._models[model.model_id] = model
            
        self._bindings.clear()
        for b_dict in data.get("bindings", []):
            self._bindings.append(ModelCapabilityBinding(**b_dict))
            
        if "hardware" in data:
            self._hardware = HardwareProfile(**data["hardware"])
            
        self._performance.clear()
        for k, p_dict in data.get("performance", {}).items():
            self._performance[k] = ModelPerformanceProfile(**p_dict)

    def _register_initial_models(self):
        # Phase 3, 4: Qwen3-8b Registration
        self.register_model(ModelDefinition(
            model_id="qwen3-8b",
            display_name="Qwen3 8B Local",
            provider="local",
            executor_type="LOCAL_MODEL",
            version="3.0",
            status=ModelState.INSTALL_REQUIRED,
            capabilities_supported=["document.classify", "code.generation", "text.summarize"],
            capabilities_forbidden=["architecture.analysis", "system.mutate"],
            hardware_requirements={"memory": "REQUIREMENT_PROFILE", "gpu": "REQUIREMENT_PROFILE"},
            memory_requirements={"min_ram": "16GB"},
            context_window=32000,
            quantization="int8",
            artifact_uri="local://models/qwen3-8b",
            artifact_sha256="dummy_hash_for_now",
            runtime_interface="llama.cpp",
            max_concurrency=1,
            max_runtime=300,
            max_input_size=20000,
            max_output_size=4000,
            network_policy="none",
            evidence_policy="required"
        ))

        # Phase 5: Luna Registration
        self.register_model(ModelDefinition(
            model_id="luna",
            display_name="Luna Remote",
            provider="remote",
            executor_type="REMOTE_MODEL",
            version="1.0",
            status=ModelState.AVAILABLE,
            capabilities_supported=["architecture.analysis", "system.mutate", "repository.diff"],
            capabilities_forbidden=[],
            hardware_requirements={},
            memory_requirements={},
            context_window=128000,
            quantization="fp16",
            artifact_uri="remote://luna-api",
            artifact_sha256="",
            runtime_interface="rest",
            max_concurrency=10,
            max_runtime=600,
            max_input_size=100000,
            max_output_size=10000,
            network_policy="egress_only",
            evidence_policy="required"
        ))

    def _register_initial_bindings(self):
        # Phase 6 mappings
        self.add_binding(ModelCapabilityBinding(
            model_id="qwen3-8b",
            capability_id="document.classify",
            authorization="allowed",
            quality_profile="standard",
            risk_limit="low",
            preferred=False,
            fallback=True,
            reason="Local processing preferred for privacy"
        ))
        
        self.add_binding(ModelCapabilityBinding(
            model_id="qwen3-8b",
            capability_id="architecture.analysis",
            authorization="forbidden",
            quality_profile="none",
            risk_limit="none",
            preferred=False,
            fallback=False,
            reason="Insufficient reasoning capacity"
        ))
        
        self.add_binding(ModelCapabilityBinding(
            model_id="luna",
            capability_id="architecture.analysis",
            authorization="allowed",
            quality_profile="high",
            risk_limit="high",
            preferred=True,
            fallback=False,
            reason="Advanced reasoning model"
        ))
        
        # Deterministic fallback conceptually
        self.add_binding(ModelCapabilityBinding(
            model_id="deterministic",
            capability_id="repository.diff",
            authorization="allowed",
            quality_profile="perfect",
            risk_limit="low",
            preferred=True,
            fallback=True,
            reason="Model not required"
        ))

    def register_model(self, model: ModelDefinition):
        if model.model_id in self._models:
            raise ValueError(f"Model {model.model_id} is already registered")
        self._models[model.model_id] = model
        self._performance[model.model_id] = ModelPerformanceProfile(
            model_id=model.model_id,
            capability_id="*"
        )
        self._save_to_disk()

    def register(self, model: ModelDefinition):
        """Alias for register_model."""
        self.register_model(model)

    def unregister(self, model_id: str):
        """Remove a model from the registry."""
        if model_id in self._models:
            del self._models[model_id]
            if model_id in self._performance:
                del self._performance[model_id]
            self._save_to_disk()

    def set_availability(self, model_id: str, available: bool):
        """Set availability state of a model."""
        model = self.get_model(model_id)
        if model:
            model.status = ModelState.AVAILABLE if available else ModelState.UNAVAILABLE
            self._save_to_disk()

    def add_binding(self, binding: ModelCapabilityBinding):
        self._bindings.append(binding)
        self._save_to_disk()

    def get_model(self, model_id: str) -> Optional[ModelDefinition]:
        return self._models.get(model_id)
        
    def list_models(self) -> List[ModelDefinition]:
        return list(self._models.values())
        
    def is_available(self, model_id: str) -> bool:
        # Phase 10 logic
        model = self.get_model(model_id)
        if not model:
            return False
            
        if model.status not in [ModelState.AVAILABLE]:
            return False
            
        if not model.artifact_uri:
            return False
            
        if not model.runtime_interface:
            return False
            
        return True

    def get_bindings_for_capability(self, capability_id: str) -> List[ModelCapabilityBinding]:
        return [b for b in self._bindings if b.capability_id == capability_id]

    def update_hardware_profile(self, profile: HardwareProfile):
        self._hardware = profile
        self._save_to_disk()
        
    def get_hardware_profile(self) -> HardwareProfile:
        return self._hardware
        
    def get_performance_profile(self, model_id: str) -> Optional[ModelPerformanceProfile]:
        return self._performance.get(model_id)
