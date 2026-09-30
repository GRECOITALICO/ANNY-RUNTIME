import os
import platform
from dataclasses import dataclass, field
from pathlib import Path


class RuntimeConfigError(RuntimeError):
    """Raised when Runtime configuration cannot be loaded safely."""


def detect_platform() -> str:
    """Auto-detect the platform."""
    return platform.system().lower()


def get_install_mode() -> str:
    """Returns the installation mode: 'system' or 'user'."""
    return os.environ.get("ANNY_INSTALL_MODE", "user").lower()


def get_data_dir() -> Path:
    """Returns the canonical data directory based on install mode or explicit environment override."""
    env_dir = os.environ.get("ANNY_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    if get_install_mode() == "system":
        return Path("/var/lib/anny-runtime")
    return Path.home() / ".anny-runtime"


def get_config_dir() -> Path:
    """Returns the directory containing configuration files."""
    return get_data_dir()


def get_runtime_dir() -> Path:
    """Returns the path to the runtime executable/installation."""
    if get_install_mode() == "system":
        return Path("/opt/anny-runtime")
    return Path.home() / ".local/share/anny-runtime"


def get_admin_port() -> int:
    """Returns the configured admin port."""
    try:
        from runtime.admin.port import PREFERRED_PORT
        default_port = PREFERRED_PORT
    except ImportError:
        default_port = 3643

    env_port = os.environ.get("ANNY_ADMIN_PORT")
    if env_port and env_port.isdigit():
        return int(env_port)
    return default_port


@dataclass
class RuntimeConfig:
    """Configuration for the ANNY Runtime."""
    data_dir: str = field(default_factory=lambda: str(get_data_dir()))
    max_concurrent_executions: int = 10
    max_process_duration_seconds: int = 3600
    max_workspace_disk_mb: int = 10240
    max_memory_mb: int = 4096
    session_lease_ttl_seconds: int = 3600
    health_check_interval_seconds: int = 30
    update_check_interval_seconds: int = 86400
    update_channel: str = 'dev'
    log_level: str = 'INFO'

    github_client_id: str = field(default_factory=lambda: os.environ.get("ANNY_GITHUB_CLIENT_ID", ""))

    # Fabric config
    fabric_org: str = None
    fabric_repo: str = None

    # M8 external authority integration (references/endpoints only; no secret material)
    conrrad_preflight_endpoint: str = field(default_factory=lambda: os.environ.get("CONRRAD_PREFLIGHT_ENDPOINT", ""))
    conrrad_installation_credential_ref: str = field(default_factory=lambda: os.environ.get("CONRRAD_INSTALLATION_CREDENTIAL_REF", ""))
    fabric_trust_verifier_endpoint: str = field(default_factory=lambda: os.environ.get("FABRIC_TRUST_VERIFIER_ENDPOINT", ""))
    execution_context_issuer_endpoint: str = field(default_factory=lambda: os.environ.get("EXECUTION_CONTEXT_ISSUER_ENDPOINT", ""))
    conrrad_audience: str = field(default_factory=lambda: os.environ.get("CONRRAD_AUDIENCE", ""))
    conrrad_trust_issuer: str = field(default_factory=lambda: os.environ.get("CONRRAD_TRUST_ISSUER", ""))
    conrrad_trust_root_id: str = field(default_factory=lambda: os.environ.get("CONRRAD_TRUST_ROOT_ID", ""))
    conrrad_trust_root_reference: str = field(default_factory=lambda: os.environ.get("CONRRAD_TRUST_ROOT_REFERENCE", ""))

    # Admin panel configuration
    admin_enabled: bool = True
    admin_host: str = '127.0.0.1'
    admin_port: int = field(default_factory=get_admin_port)
    admin_session_ttl_seconds: int = 1800

    platform: str = field(default_factory=detect_platform)

    @classmethod
    def load(cls) -> "RuntimeConfig":
        """Load configuration deterministically and fail closed on malformed input."""
        config_path = get_config_dir() / "config.yaml"
        config_data = {}
        if config_path.exists():
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeConfigError("PyYAML is required to load Runtime configuration") from exc
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except (OSError, yaml.YAMLError) as exc:
                raise RuntimeConfigError(
                    f"Invalid Runtime configuration at {config_path}: {exc}"
                ) from exc
            if data is None:
                config_data = {}
            elif not isinstance(data, dict):
                raise RuntimeConfigError(
                    f"Runtime configuration at {config_path} must be a YAML mapping"
                )
            else:
                config_data = data

        valid_keys = cls.__dataclass_fields__.keys()
        admin_config = config_data.get('admin', {})
        if isinstance(admin_config, dict):
            for ak, av in admin_config.items():
                flat_key = f'admin_{ak}'
                if flat_key in valid_keys:
                    config_data[flat_key] = av

        env_overrides = {
            "ANNY_GITHUB_CLIENT_ID": "github_client_id",
            "CONRRAD_PREFLIGHT_ENDPOINT": "conrrad_preflight_endpoint",
            "CONRRAD_INSTALLATION_CREDENTIAL_REF": "conrrad_installation_credential_ref",
            "FABRIC_TRUST_VERIFIER_ENDPOINT": "fabric_trust_verifier_endpoint",
            "EXECUTION_CONTEXT_ISSUER_ENDPOINT": "execution_context_issuer_endpoint",
            "CONRRAD_AUDIENCE": "conrrad_audience",
            "CONRRAD_TRUST_ISSUER": "conrrad_trust_issuer",
            "CONRRAD_TRUST_ROOT_ID": "conrrad_trust_root_id",
            "CONRRAD_TRUST_ROOT_REFERENCE": "conrrad_trust_root_reference",
        }
        for env_name, field_name in env_overrides.items():
            value = os.environ.get(env_name)
            if value:
                config_data[field_name] = value

        filtered_data = {k: v for k, v in config_data.items() if k in valid_keys}
        return cls(**filtered_data)

    def save(self) -> None:
        """Saves the current configuration to config.yaml."""
        import yaml
        config_path = get_config_dir() / "config.yaml"
        get_config_dir().mkdir(parents=True, exist_ok=True)
        data = {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
        admin_keys = [k for k in data.keys() if k.startswith('admin_')]
        if admin_keys:
            data['admin'] = {k.replace('admin_', ''): data.pop(k) for k in admin_keys}
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False)
