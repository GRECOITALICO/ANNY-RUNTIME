import os
from .linux import LinuxAdapter


class WSL2Adapter(LinuxAdapter):
    """Platform adapter for WSL2 systems."""

    def platform_name(self) -> str:
        return "wsl2"

    def is_supported(self) -> bool:
        if not super().is_supported():
            return False
        return self.detect_wsl()

    def detect_wsl(self) -> bool:
        if "WSL_DISTRO_NAME" in os.environ:
            return True
        try:
            with open("/proc/version", "r") as f:
                content = f.read().lower()
                if "microsoft" in content and "wsl2" in content:
                    return True
        except FileNotFoundError:
            pass
        return False
