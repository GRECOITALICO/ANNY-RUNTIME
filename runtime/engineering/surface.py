"""Runtime-owned engineering surface.

This is dependency composition only. It is not a second registry, authority
source, router, or certification mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class EngineeringSurface:
    workspace_manager: Any
    process_manager: Any
    shell_executor: Any
    filesystem_service: Any
    git_service: Any
    toolchain_runner: Any
    execution_manager: Any = None
    harness_contract: Any = None
    harness_dispatcher: Any = None
    github_client: Any = None
    github_engineering: Any = None
    browser_manager: Any = None

    def inventory(self) -> Dict[str, str]:
        fields = {
            "workspace": self.workspace_manager,
            "process": self.process_manager,
            "shell": self.shell_executor,
            "filesystem": self.filesystem_service,
            "git": self.git_service,
            "toolchain": self.toolchain_runner,
            "execution": self.execution_manager,
            "harness_contract": self.harness_contract,
            "harness_dispatcher": self.harness_dispatcher,
            "github_read": self.github_client,
            "github_engineering": self.github_engineering,
            "browser": self.browser_manager,
        }
        return {
            key: "ATTACHED" if value is not None else "UNAVAILABLE"
            for key, value in fields.items()
        }

    def component(self, name: str) -> Optional[Any]:
        return getattr(self, name, None)
