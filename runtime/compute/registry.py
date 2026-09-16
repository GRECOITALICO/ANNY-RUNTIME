"""Runtime Capability Registry.

Stores observed and tested capabilities for a remote compute session.
Each capability is tagged with provenance: UNKNOWN, OBSERVED, TESTED, UNAVAILABLE.

ANNY consults this registry to determine what functional capabilities
are available. ANNY never requests hardware — only functional capabilities.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from datetime import datetime, timezone


class CapabilityState(Enum):
    """Provenance/trust level for a runtime capability."""
    UNKNOWN = "UNKNOWN"
    OBSERVED = "OBSERVED"
    TESTED = "TESTED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class RuntimeCapability:
    """A single observed or tested capability."""
    name: str
    state: CapabilityState
    observed_at: Optional[datetime] = None
    details: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "details": self.details,
        }


class RuntimeCapabilityRegistry:
    """Registry of runtime capabilities observed from a remote session.

    Populated by RuntimeResourceDiscovery after a successful connection.
    ANNY queries this registry to make functional decisions.
    """

    def __init__(self):
        self._capabilities: Dict[str, RuntimeCapability] = {}

    def register(self, name: str, state: CapabilityState, details: Optional[str] = None) -> None:
        """Register or update a capability."""
        self._capabilities[name] = RuntimeCapability(
            name=name,
            state=state,
            observed_at=datetime.now(timezone.utc),
            details=details,
        )

    def get(self, name: str) -> Optional[RuntimeCapability]:
        """Get a specific capability by name."""
        return self._capabilities.get(name)

    def list_all(self) -> List[RuntimeCapability]:
        """List all registered capabilities."""
        return list(self._capabilities.values())

    def clear(self) -> None:
        """Clear all capabilities (used on new session)."""
        self._capabilities.clear()

    def to_dict(self) -> dict:
        """Serialize the entire registry to a dict."""
        return {
            "capabilities": [c.to_dict() for c in self._capabilities.values()],
            "count": len(self._capabilities),
        }

    def from_resource_profile(self, profile) -> None:
        """Populate capabilities from a RuntimeResourceProfile.

        Each observed resource becomes a capability entry with appropriate state.
        """
        now = datetime.now(timezone.utc)

        # CPU
        if profile.get("cpu") and profile["cpu"] != "UNKNOWN":
            self.register("cpu.compute", CapabilityState.OBSERVED,
                          f"{profile.get('cpu_count', '?')} cores, {profile.get('ram_gb', '?')} GB RAM")
        else:
            self.register("cpu.compute", CapabilityState.UNKNOWN)

        # GPU
        gpu_present = profile.get("gpu_present", False)
        if gpu_present:
            gpu_name = profile.get("gpu_name", "UNKNOWN")
            vram = profile.get("vram_gb", "UNKNOWN")
            self.register("gpu.compute", CapabilityState.OBSERVED,
                          f"{gpu_name}, {vram} GB VRAM")
        else:
            self.register("gpu.compute", CapabilityState.UNAVAILABLE)

        # TPU
        tpu_present = profile.get("tpu_present", False)
        if tpu_present:
            self.register("tpu.compute", CapabilityState.OBSERVED,
                          profile.get("tpu_type", "UNKNOWN"))
        else:
            self.register("tpu.compute", CapabilityState.UNAVAILABLE)

        # CUDA
        cuda_available = profile.get("cuda_available", False)
        if cuda_available:
            self.register("cuda", CapabilityState.OBSERVED,
                          f"CUDA {profile.get('cuda_version', '?')}, Driver {profile.get('driver_version', '?')}")
        elif gpu_present:
            self.register("cuda", CapabilityState.UNKNOWN)
        else:
            self.register("cuda", CapabilityState.UNAVAILABLE)

        # Remote execution
        if profile.get("remote_execution") == "PASS":
            self.register("remote.execution", CapabilityState.TESTED)
        else:
            self.register("remote.execution", CapabilityState.UNKNOWN)

        # Software stack
        for pkg, key in [
            ("software.python", "python_version"),
            ("software.pytorch", "torch_version"),
            ("software.transformers", "transformers_version"),
            ("software.peft", "peft_version"),
            ("software.bitsandbytes", "bitsandbytes_version"),
            ("software.accelerate", "accelerate_version"),
        ]:
            val = profile.get(key)
            if val and val not in ("UNKNOWN", "NOT_INSTALLED"):
                self.register(pkg, CapabilityState.OBSERVED, val)
            elif val == "NOT_INSTALLED":
                self.register(pkg, CapabilityState.UNAVAILABLE)
            else:
                self.register(pkg, CapabilityState.UNKNOWN)

        # CausalLM
        if profile.get("causallm_inference") == "PASS":
            self.register("model.causal_lm", CapabilityState.TESTED,
                          profile.get("causallm_model_class", "UNKNOWN"))
        else:
            self.register("model.causal_lm", CapabilityState.UNKNOWN)

        # Tensor compute tests
        if profile.get("cuda_tensor_test") == "PASS":
            self.register("gpu.tensor_compute", CapabilityState.TESTED)
        elif gpu_present:
            self.register("gpu.tensor_compute", CapabilityState.UNKNOWN)

        if profile.get("fp16_test") == "PASS":
            self.register("gpu.fp16", CapabilityState.TESTED)
        elif gpu_present:
            self.register("gpu.fp16", CapabilityState.UNKNOWN)
