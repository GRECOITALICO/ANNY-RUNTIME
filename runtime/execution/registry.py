import uuid
from typing import List, Optional, Dict, Any
from .models import (
    ModelDefinition, ModelState, ModelCapabilityBinding,
    HardwareProfile, ModelPerformanceProfile, EvaluationRecord
)

class ModelRegistry:
    def __init__(self):
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
        
        self._register_initial_models()
        self._register_initial_bindings()

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
            raise ValueError(f"Model {model.model_id} already registered.")
        self._models[model.model_id] = model
        self._performance[model.model_id] = ModelPerformanceProfile(
            model_id=model.model_id,
            capability_id="*"
        )

    def add_binding(self, binding: ModelCapabilityBinding):
        self._bindings.append(binding)

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
        
    def get_hardware_profile(self) -> HardwareProfile:
        return self._hardware
        
    def get_performance_profile(self, model_id: str) -> Optional[ModelPerformanceProfile]:
        return self._performance.get(model_id)
