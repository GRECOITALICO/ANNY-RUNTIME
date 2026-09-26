"""Evidence-first Runtime diagnostics.

Doctor reports observable local state. It never returns PASS merely because a
subsystem class exists; unavailable/unverified components remain UNKNOWN.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from runtime.core.config import get_data_dir
from runtime.identity.runtime_identity import RuntimeIdentity


@dataclass
class DiagnosticCheck:
    name: str
    status: str  # PASS, FAIL, WARN, UNKNOWN, SKIP
    message: str
    details: Any = None


class RuntimeDoctor:
    """Evidence-first local Runtime diagnostic service."""

    def __init__(self, engine_ref: Any = None) -> None:
        self.engine_ref = engine_ref
        self.data_dir = Path(get_data_dir())

    def run_all(self) -> List[DiagnosticCheck]:
        return [
            self.check_core(),
            self.check_identity(),
            self.check_enrollment(),
            self.check_session(),
            self.check_capabilities(),
            self.check_tools(),
            self.check_workspace(),
            self.check_process_manager(),
            self.check_filesystem(),
            self.check_shell(),
            self.check_git(),
            self.check_secrets(),
            self.check_fabric(),
            self.check_updater(),
            self.check_journal(),
        ]

    def check_core(self) -> DiagnosticCheck:
        return DiagnosticCheck(
            "Core",
            "PASS",
            "Runtime diagnostic subsystem initialized",
            {"data_dir": str(self.data_dir)},
        )

    def check_identity(self) -> DiagnosticCheck:
        identity_path = self.data_dir / "identity" / "runtime_identity.json"
        if not identity_path.is_file():
            return DiagnosticCheck("Identity", "UNKNOWN", "Runtime identity record is not present")
        try:
            identity = RuntimeIdentity.load(str(self.data_dir))
            return DiagnosticCheck(
                "Identity",
                "PASS",
                "Runtime identity loaded",
                {"runtime_id": identity.runtime_id, "installation_id": identity.installation_id},
            )
        except Exception as exc:
            return DiagnosticCheck("Identity", "FAIL", "Runtime identity record could not be loaded", type(exc).__name__)

    def check_enrollment(self) -> DiagnosticCheck:
        enrollment = getattr(self.engine_ref, "enrollment", None)
        if enrollment is None:
            return DiagnosticCheck("Enrollment", "UNKNOWN", "No authoritative enrollment manager is attached")
        state = getattr(getattr(enrollment, "state", None), "name", None)
        if state in {"READY", "PAIRED"}:
            return DiagnosticCheck("Enrollment", "PASS", f"Enrollment state observed: {state}")
        if state is None:
            return DiagnosticCheck("Enrollment", "UNKNOWN", "Enrollment state is unavailable")
        return DiagnosticCheck("Enrollment", "FAIL", f"Enrollment state is not ready: {state}")

    def check_session(self) -> DiagnosticCheck:
        sessions = getattr(self.engine_ref, "session_manager", None)
        if sessions is None:
            return DiagnosticCheck("Session", "UNKNOWN", "No authoritative session manager is attached")
        return DiagnosticCheck("Session", "PASS", "Session manager is attached")

    def check_capabilities(self) -> DiagnosticCheck:
        execution = getattr(self.engine_ref, "execution_manager", None)
        registry = getattr(execution, "capability_registry", None) if execution else None
        if registry is None:
            registry = getattr(self.engine_ref, "capability_registry", None)
        if registry is None:
            return DiagnosticCheck("Capabilities", "UNKNOWN", "Canonical Runtime CapabilityRegistry is unavailable")
        try:
            count = len(registry.list_all())
            return DiagnosticCheck("Capabilities", "PASS", f"Canonical capability registry loaded ({count})")
        except Exception as exc:
            return DiagnosticCheck("Capabilities", "FAIL", "Capability registry could not be read", type(exc).__name__)

    def check_tools(self) -> DiagnosticCheck:
        gateway = getattr(self.engine_ref, "mcp_gateway", None)
        if gateway is None:
            return DiagnosticCheck("Tools", "UNKNOWN", "MCP Gateway is not attached")
        try:
            available = len(gateway.tool_registry.list_available())
            return DiagnosticCheck("Tools", "PASS", f"MCP Gateway attached ({available} available tools)")
        except Exception as exc:
            return DiagnosticCheck("Tools", "FAIL", "MCP tool registry could not be read", type(exc).__name__)

    def check_workspace(self) -> DiagnosticCheck:
        workspace = getattr(self.engine_ref, "workspace_manager", None)
        if workspace is None:
            execution = getattr(self.engine_ref, "execution_manager", None)
            workspace = getattr(execution, "workspace_manager", None) if execution else None
        if workspace is None:
            return DiagnosticCheck("Workspace", "UNKNOWN", "No authoritative WorkspaceManager is attached")
        return DiagnosticCheck("Workspace", "PASS", "Workspace manager is attached")

    def check_process_manager(self) -> DiagnosticCheck:
        process_manager = getattr(self.engine_ref, "process_manager", None)
        if process_manager is None:
            return DiagnosticCheck("Process Manager", "UNKNOWN", "No authoritative ProcessManager is attached")
        try:
            active = len(process_manager.active_processes())
            return DiagnosticCheck("Process Manager", "PASS", f"Process manager observable; {active} active process(es)")
        except Exception as exc:
            return DiagnosticCheck("Process Manager", "FAIL", "Process manager status could not be read", type(exc).__name__)

    def check_filesystem(self) -> DiagnosticCheck:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            probe = self.data_dir / ".doctor-write-probe"
            probe.write_text("doctor", encoding="utf-8")
            probe.unlink()
            return DiagnosticCheck("Filesystem", "PASS", "Runtime data directory is readable and writable")
        except Exception as exc:
            return DiagnosticCheck("Filesystem", "FAIL", "Runtime data directory write probe failed", type(exc).__name__)

    def check_shell(self) -> DiagnosticCheck:
        if shutil.which("bash") is None:
            return DiagnosticCheck("Shell", "FAIL", "bash executable not found")
        shell = getattr(self.engine_ref, "shell_executor", None)
        if shell is None:
            return DiagnosticCheck("Shell", "UNKNOWN", "No authoritative ShellExecutor is attached")
        return DiagnosticCheck("Shell", "PASS", "Shell executable and ShellExecutor are present")

    def check_git(self) -> DiagnosticCheck:
        executable = shutil.which("git")
        if executable is None:
            return DiagnosticCheck("Git", "FAIL", "git executable not found")
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return DiagnosticCheck("Git", "PASS", result.stdout.strip(), {"path": executable})
            return DiagnosticCheck("Git", "FAIL", "git --version failed", result.stderr.strip())
        except Exception as exc:
            return DiagnosticCheck("Git", "FAIL", "git probe failed", type(exc).__name__)

    def check_secrets(self) -> DiagnosticCheck:
        secret_backend = getattr(self.engine_ref, "secret_backend", None)
        if secret_backend is None:
            return DiagnosticCheck("Secrets", "UNKNOWN", "No authoritative SecretBackend is attached")
        return DiagnosticCheck("Secrets", "PASS", "Secret backend is attached")

    def check_fabric(self) -> DiagnosticCheck:
        fabric = getattr(self.engine_ref, "fabric_adapter", None)
        if fabric is None:
            return DiagnosticCheck("Fabric", "UNKNOWN", "Fabric adapter is not attached")
        probe = getattr(fabric, "probe_reachability", None)
        if probe is None:
            return DiagnosticCheck("Fabric", "UNKNOWN", "Fabric adapter exposes no reachability probe")
        try:
            reachable, latency_ms, status = probe()
            if reachable:
                return DiagnosticCheck("Fabric", "PASS", "Fabric reachability observed", {"latency_ms": latency_ms, "status": status})
            return DiagnosticCheck("Fabric", "FAIL", "Fabric reachability failed", {"status": status})
        except Exception as exc:
            return DiagnosticCheck("Fabric", "UNKNOWN", "Fabric reachability could not be established", type(exc).__name__)

    def check_updater(self) -> DiagnosticCheck:
        updater = getattr(self.engine_ref, "update_manager", None)
        if updater is None:
            return DiagnosticCheck("Updater", "UNKNOWN", "No UpdateManager is attached")
        state = getattr(getattr(updater, "state", None), "name", None)
        if state == "NOT_IMPLEMENTED":
            return DiagnosticCheck("Updater", "UNKNOWN", "Update lifecycle is not implemented")
        return DiagnosticCheck("Updater", "WARN", "UpdateManager is attached; lifecycle state requires execution evidence", state)

    def check_journal(self) -> DiagnosticCheck:
        journal_dir = self.data_dir / "journal"
        if not journal_dir.exists():
            return DiagnosticCheck("Journal", "UNKNOWN", "Runtime journal directory is not present")
        if not journal_dir.is_dir():
            return DiagnosticCheck("Journal", "FAIL", "Runtime journal path is not a directory")
        return DiagnosticCheck("Journal", "PASS", "Runtime journal directory is present")
