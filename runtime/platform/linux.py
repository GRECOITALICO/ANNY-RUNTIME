import shutil
import platform
import os
from pathlib import Path
from typing import Optional
from .base import PlatformAdapter


class LinuxAdapter(PlatformAdapter):
    """Platform adapter for Linux systems."""

    def platform_name(self) -> str:
        return "linux"

    def is_supported(self) -> bool:
        return platform.system().lower() == "linux"

    def get_service_manager(self) -> str:
        if shutil.which("systemctl"):
            return "systemd"
        return "unknown"

    def get_default_data_dir(self) -> Path:
        from runtime.core.config import get_data_dir
        return get_data_dir()

    def get_secure_storage_path(self) -> Path:
        from runtime.core.config import get_data_dir
        return get_data_dir() / "secure"

    def get_shell_path(self) -> str:
        return os.environ.get("SHELL", "/bin/bash")

    def detect_git(self) -> Optional[str]:
        return shutil.which("git")

    def detect_wsl(self) -> bool:
        return False
