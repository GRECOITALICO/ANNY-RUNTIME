import abc
from pathlib import Path
from typing import Optional


class PlatformAdapter(abc.ABC):
    """Abstract base class for platform adapters."""

    @abc.abstractmethod
    def platform_name(self) -> str:
        """Return the name of the platform."""
        pass

    @abc.abstractmethod
    def is_supported(self) -> bool:
        """Check if this platform is supported on the current system."""
        pass

    @abc.abstractmethod
    def get_service_manager(self) -> str:
        """Return the service manager (e.g., systemd)."""
        pass

    @abc.abstractmethod
    def get_default_data_dir(self) -> Path:
        """Return the default data directory."""
        pass

    @abc.abstractmethod
    def get_secure_storage_path(self) -> Path:
        """Return the path for secure storage."""
        pass

    @abc.abstractmethod
    def get_shell_path(self) -> str:
        """Return the default shell path."""
        pass

    @abc.abstractmethod
    def detect_git(self) -> Optional[str]:
        """Detect and return git executable path if present."""
        pass

    @abc.abstractmethod
    def detect_wsl(self) -> bool:
        """Return True if running in WSL."""
        pass
