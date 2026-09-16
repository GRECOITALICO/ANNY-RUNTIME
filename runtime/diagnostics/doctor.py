import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, List


@dataclass
class DiagnosticCheck:
    name: str
    status: str  # PASS, FAIL, WARN, SKIP
    message: str
    details: Any = None


class RuntimeDoctor:
    """Evidence-first diagnostics for the runtime admin surface.

    Diagnostics complement the deterministic bootstrap; they do not grant
    runtime admission. Checks that cannot be verified from the supplied
    engine/context are reported as SKIP rather than optimistic PASS values.
    """

    def __init__(self, engine_ref: Any = None) -> None:
        self.engine_ref = engine_ref

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
        if self.engine_ref is None:
            return DiagnosticCheck("Core", "FAIL", "Runtime engine is not initialized")
        return DiagnosticCheck("Core", "PASS", "Runtime engine is initialized")

    def check_identity(self) -> DiagnosticCheck:
        identity = getattr(self.engine_ref, "identity", None)
        if identity is None:
            return DiagnosticCheck("Identity", "FAIL", "Runtime identity is not loaded")
        runtime_id = getattr(identity, "runtime_id", "UNKNOWN")
        return DiagnosticCheck("Identity", "PASS", "Runtime identity loaded", {"runtime_id": runtime_id})

    def check_enrollment(self) -> DiagnosticCheck:
        report = getattr(self.engine_ref, "bootstrap_report", None)
        if report is None:
            return DiagnosticCheck("Enrollment", "SKIP", "Fabric enrollment is verified by deterministic bootstrap")
        if getattr(report, "anny_ready", False):
            return DiagnosticCheck("Enrollment", "PASS", "Bootstrap reports runtime admitted")
        return DiagnosticCheck("Enrollment", "FAIL", "Bootstrap does not report runtime admission")

    def check_session(self) -> DiagnosticCheck:
        if self.engine_ref is None:
            return DiagnosticCheck("Session", "SKIP", "No runtime engine available")
        state = getattr(getattr(self.engine_ref, "state", None), "name", None)
        if state == "WAITING_FOR_SESSION":
            return DiagnosticCheck("Session", "PASS", "Runtime is waiting for a session")
        return DiagnosticCheck("Session", "SKIP", f"No active session state to verify (state={state or 'UNKNOWN'})")

    def check_capabilities(self) -> DiagnosticCheck:
        return DiagnosticCheck("Capabilities", "SKIP", "Capability readiness is verified by bootstrap inventory/access gates")

    def check_tools(self) -> DiagnosticCheck:
        return DiagnosticCheck("Tools", "SKIP", "Tool readiness is verified by bootstrap inventory/access gates")

    def check_workspace(self) -> DiagnosticCheck:
        return DiagnosticCheck("Workspace", "SKIP", "Workspace readiness is not independently exposed by the diagnostic context")

    def check_process_manager(self) -> DiagnosticCheck:
        return DiagnosticCheck("Process Manager", "SKIP", "Process-manager readiness is not independently exposed by the diagnostic context")

    def check_filesystem(self) -> DiagnosticCheck:
        if self.engine_ref is None:
            return DiagnosticCheck("Filesystem", "SKIP", "No runtime engine available")
        config = getattr(self.engine_ref, "config", None)
        data_dir = getattr(config, "data_dir", None)
        if not data_dir:
            return DiagnosticCheck("Filesystem", "SKIP", "Runtime data directory is not configured")
        try:
            stat = os.stat(data_dir)
            if not os.access(data_dir, os.R_OK):
                return DiagnosticCheck("Filesystem", "FAIL", f"Runtime data directory is not readable: {data_dir}")
            return DiagnosticCheck(
                "Filesystem",
                "PASS",
                "Runtime data directory is readable",
                {"path": data_dir, "mode": oct(stat.st_mode)},
            )
        except OSError as e:
            return DiagnosticCheck("Filesystem", "FAIL", f"Runtime data directory check failed: {e}")

    def check_shell(self) -> DiagnosticCheck:
        shell = os.environ.get("SHELL")
        if not shell:
            return DiagnosticCheck("Shell", "SKIP", "SHELL environment variable is not set")
        executable = shutil.which(shell)
        if executable is None:
            return DiagnosticCheck("Shell", "FAIL", f"Configured shell is not executable: {shell}")
        return DiagnosticCheck("Shell", "PASS", f"Configured shell available: {executable}")

    def check_git(self) -> DiagnosticCheck:
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return DiagnosticCheck("Git", "PASS", result.stdout.strip())
            return DiagnosticCheck("Git", "FAIL", "Git execution failed")
        except FileNotFoundError:
            return DiagnosticCheck("Git", "FAIL", "Git not found")
        except OSError as e:
            return DiagnosticCheck("Git", "FAIL", f"Git check failed: {e}")

    def check_secrets(self) -> DiagnosticCheck:
        return DiagnosticCheck("Secrets", "SKIP", "Secrets backend cannot be certified by this diagnostic without backend evidence")

    def check_fabric(self) -> DiagnosticCheck:
        return DiagnosticCheck("Fabric", "SKIP", "Fabric reachability/trust/admission are authoritative only in deterministic bootstrap")

    def check_updater(self) -> DiagnosticCheck:
        manager = getattr(self.engine_ref, "evolution_manager", None) if self.engine_ref else None
        if manager is None:
            return DiagnosticCheck("Updater", "SKIP", "Evolution manager is not initialized")
        return DiagnosticCheck("Updater", "PASS", "Evolution manager is initialized")

    def check_journal(self) -> DiagnosticCheck:
        continuity = getattr(self.engine_ref, "continuity_engine", None) if self.engine_ref else None
        if continuity is None:
            return DiagnosticCheck("Journal", "SKIP", "Continuity engine is not initialized")
        try:
            status = continuity.status
        except Exception as e:
            return DiagnosticCheck("Journal", "FAIL", f"Continuity journal status failed: {e}")
        state = status.get("state", "UNKNOWN") if isinstance(status, dict) else "UNKNOWN"
        if state == "COHERENT":
            return DiagnosticCheck("Journal", "PASS", "Continuity journal is coherent", status)
        return DiagnosticCheck("Journal", "FAIL", f"Continuity journal state: {state}", status)
