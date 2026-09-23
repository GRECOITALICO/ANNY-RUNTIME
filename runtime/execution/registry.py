import uuid
import os
import json
import tempfile
import dataclasses
from typing import List, Optional, Dict, Any, Callable
from .models import (
    ModelDefinition, ModelState, ModelCapabilityBinding,
    HardwareProfile, ModelPerformanceProfile, EvaluationRecord
)

class RegistryRecoveryRequired(RuntimeError):
    """Raised when durable registry state is corrupted and explicit recovery is required."""


class RecoveryAttestationError(RuntimeError):
    """Raised when an external recovery attestation is missing or invalid."""


@dataclasses.dataclass(frozen=True)
class RecoveryAttestation:
    """Externally produced, evidence-backed authorization to restore a registry."""

    recovery_id: str
    source_registry_hash: str
    quarantine_reference: str
    authority_ref: str
    authority_decision: str
    source_evidence_ids: List[str]
    reconstructed_registry_digest: str
    registry_payload: Dict[str, Any]
    verification_evidence_ids: List[str]
    recovery_timestamp: str


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

    @classmethod
    def open_for_recovery(cls, storage_path: str):
        """Open a blocked registry only for an explicit recovery operation.

        Normal construction remains fail-closed when a pending recovery marker
        exists. This recovery-only entry point performs no bootstrap, model
        registration, binding creation, authorization, or routing reconstruction.
        """
        if not storage_path:
            raise RecoveryAttestationError("Recovery requires a durable registry path")
        recovery_path = f"{storage_path}.recovery.json"
        if not os.path.exists(recovery_path):
            raise RecoveryAttestationError("No pending recovery marker exists")

        self = cls.__new__(cls)
        self.storage_path = storage_path
        self._models = {}
        self._bindings = []
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
        self._performance = {}
        self._evaluations = []
        return self

    class _EnumEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, ModelState):
                return obj.value
            return super().default(obj)

    def _build_data(self):
        return {
            "version": "1.0",
            "models": [dataclasses.asdict(m) for m in self._models.values()],
            "bindings": [dataclasses.asdict(b) for b in self._bindings],
            "hardware": dataclasses.asdict(self._hardware),
            "performance": {k: dataclasses.asdict(v) for k, v in self._performance.items()},
        }

    def _serialize_data(self, data: Dict[str, Any]) -> bytes:
        return json.dumps(data, cls=self._EnumEncoder, indent=2).encode("utf-8")

    def _save_to_disk(self):
        if not self.storage_path:
            return

        data = self._build_data()
        serialized = self._serialize_data(data)

        dir_name = os.path.dirname(self.storage_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".registry-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(serialized)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.storage_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _load_data(self, data: Dict[str, Any]):
        if data.get("version") != "1.0":
            raise ValueError("Unsupported registry schema version")

        self._models.clear()
        for m_dict in data.get("models", []):
            m_dict = dict(m_dict)
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

    def _load_from_disk(self):
        with open(self.storage_path, 'r') as f:
            data = json.load(f)
        self._load_data(data)

    def restore_from_attestation(
        self,
        attestation: RecoveryAttestation,
        authority_verifier: Callable[[RecoveryAttestation], bool],
    ) -> None:
        """Restore a blocked registry from an externally authorized attestation."""

        if not self.storage_path:
            raise RecoveryAttestationError("Recovery requires a durable registry path")

        import re
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", attestation.recovery_id):
            raise RecoveryAttestationError("Recovery id contains invalid characters")

        recovery_path = f"{self.storage_path}.recovery.json"
        if not os.path.exists(recovery_path):
            raise RecoveryAttestationError("No pending recovery marker exists")

        with open(recovery_path, "r") as f:
            marker = json.load(f)

        required = (
            attestation.recovery_id,
            attestation.source_registry_hash,
            attestation.quarantine_reference,
            attestation.authority_ref,
            attestation.authority_decision,
            attestation.reconstructed_registry_digest,
            attestation.registry_payload,
            attestation.recovery_timestamp,
        )
        if any(value in (None, "", [], {}) for value in required):
            raise RecoveryAttestationError("Recovery attestation is incomplete")
        if not attestation.source_evidence_ids:
            raise RecoveryAttestationError("Recovery attestation has no source evidence")
        if not attestation.verification_evidence_ids:
            raise RecoveryAttestationError("Recovery attestation has no verification evidence")
        if attestation.authority_decision != "APPROVE_RESTORE":
            raise RecoveryAttestationError("Recovery authority decision is not APPROVE_RESTORE")

        if marker.get("state") != "BLOCKED_OR_UNKNOWN":
            raise RecoveryAttestationError("Recovery marker is not in BLOCKED_OR_UNKNOWN state")
        if marker.get("original_sha256") != attestation.source_registry_hash:
            raise RecoveryAttestationError("Source registry hash does not match recovery marker")

        quarantine_reference = os.path.abspath(attestation.quarantine_reference)
        marker_quarantine = os.path.abspath(marker.get("quarantine_path", ""))
        if quarantine_reference != marker_quarantine:
            raise RecoveryAttestationError("Quarantine reference does not match recovery marker")
        if not os.path.exists(quarantine_reference):
            raise RecoveryAttestationError("Quarantine evidence is missing")

        import hashlib
        with open(quarantine_reference, "rb") as f:
            quarantine_hash = hashlib.sha256(f.read()).hexdigest()
        if quarantine_hash != attestation.source_registry_hash:
            raise RecoveryAttestationError("Quarantine evidence hash mismatch")

        try:
            authorized = bool(authority_verifier(attestation))
        except Exception as exc:
            raise RecoveryAttestationError("Recovery authority verifier failed") from exc
        if not authorized:
            raise RecoveryAttestationError("Recovery authority did not authorize restoration")

        candidate = json.loads(json.dumps(attestation.registry_payload))
        try:
            probe = ModelRegistry()
            probe._load_data(candidate)
        except Exception as exc:
            raise RecoveryAttestationError(
                f"Reconstructed registry payload is invalid: {exc}"
            ) from exc

        serialized = self._serialize_data(candidate)
        reconstructed_digest = hashlib.sha256(serialized).hexdigest()
        if reconstructed_digest != attestation.reconstructed_registry_digest:
            raise RecoveryAttestationError("Reconstructed registry digest mismatch")

        dir_name = os.path.dirname(self.storage_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            dir=dir_name, prefix=".registry-recovery-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(serialized)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.storage_path)

            record_path = (
                f"{self.storage_path}.recovery-record.{attestation.recovery_id}.json"
            )
            record = {
                "version": "1.0",
                "state": "RESTORED_VERIFIED",
                "recovery_id": attestation.recovery_id,
                "source_registry_hash": attestation.source_registry_hash,
                "quarantine_reference": quarantine_reference,
                "authority_ref": attestation.authority_ref,
                "authority_decision": attestation.authority_decision,
                "source_evidence_ids": attestation.source_evidence_ids,
                "verification_evidence_ids": attestation.verification_evidence_ids,
                "reconstructed_registry_digest": reconstructed_digest,
                "recovery_timestamp": attestation.recovery_timestamp,
            }
            with open(record_path, "w") as rf:
                json.dump(record, rf, indent=2)
                rf.flush()
                os.fsync(rf.fileno())

            os.unlink(recovery_path)
            self._load_from_disk()
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

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
            artifact_sha256="",
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

    _PLACEHOLDER_ARTIFACT_DIGESTS = frozenset({
        "dummy_hash_for_now",
        "UNKNOWN",
        "UNVERIFIED",
        "REPLACE_ME",
    })

    def _validate_artifact_provenance(self, model: ModelDefinition) -> None:
        digest = (model.artifact_sha256 or "").strip()
        if digest in self._PLACEHOLDER_ARTIFACT_DIGESTS:
            raise ValueError(
                f"Model {model.model_id} has placeholder artifact provenance"
            )
        if model.executor_type == "LOCAL_MODEL" and model.status == ModelState.AVAILABLE:
            if not __import__("re").fullmatch(r"[0-9a-fA-F]{64}", digest):
                raise ValueError(
                    f"Available local model {model.model_id} requires a verified 64-hex artifact SHA-256"
                )

    def register_model(self, model: ModelDefinition):
        if model.model_id in self._models:
            raise ValueError(f"Model {model.model_id} is already registered")
        self._validate_artifact_provenance(model)
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
