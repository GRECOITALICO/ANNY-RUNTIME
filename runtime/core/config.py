import os
import platform
from dataclasses import dataclass, field
from pathlib import Path


def detect_platform() -> str:
    """Auto-detect the platform."""
    return platform.system().lower()


@dataclass
class RuntimeConfig:
    """Configuration for the ANNY Runtime."""
    data_dir: str = str(Path.home() / ".anny-runtime")
    max_concurrent_executions: int = 10
    max_process_duration_seconds: int = 3600
    max_workspace_disk_mb: int = 10240
    max_memory_mb: int = 4096
    session_lease_ttl_seconds: int = 3600
    health_check_interval_seconds: int = 30
    update_check_interval_seconds: int = 86400
    update_channel: str = 'dev'
    log_level: str = 'INFO'
    
    # Admin panel configuration
    admin_enabled: bool = True
    admin_host: str = '127.0.0.1'
    admin_port: int = 3643
    admin_session_ttl_seconds: int = 1800
    
    platform: str = field(default_factory=detect_platform)

    @classmethod
    def load(cls) -> "RuntimeConfig":
        """Loads configuration from YAML if present, merges with defaults."""
        config_path = Path.home() / ".anny-runtime" / "config.yaml"
        config_data = {}
        if config_path.exists():
            try:
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        config_data = data
            except ImportError:
                # Basic YAML fallback if python-yaml is not installed
                with open(config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if ":" in line:
                            key, val = line.split(":", 1)
                            key = key.strip()
                            val = val.strip()
                            if val.isdigit():
                                val = int(val)
                            config_data[key] = val
            except Exception:
                pass
        
        valid_keys = cls.__dataclass_fields__.keys()
        
        # Handle nested admin config
        admin_config = config_data.get('admin', {})
        if isinstance(admin_config, dict):
            for ak, av in admin_config.items():
                flat_key = f'admin_{ak}'
                if flat_key in valid_keys:
                    config_data[flat_key] = av
                    
        filtered_data = {k: v for k, v in config_data.items() if k in valid_keys}
        return cls(**filtered_data)
