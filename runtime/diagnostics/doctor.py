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
    """Diagnostic service to ensure runtime health."""
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
            self.check_journal()
        ]

    def check_core(self) -> DiagnosticCheck:
        if self.engine_ref is None:
            return DiagnosticCheck("Core", "UNKNOWN", "Runtime engine was not supplied")
        health = self.engine_ref.health_check()
        return DiagnosticCheck("Core", health["status"].upper(), "Observed Runtime health", health)

    def check_identity(self) -> DiagnosticCheck:
        return self._engine_subsystem_check("Identity", "identity")

    def check_enrollment(self) -> DiagnosticCheck:
        return DiagnosticCheck("Enrollment", "UNKNOWN", "No enrollment authority query is implemented")

    def check_session(self) -> DiagnosticCheck:
        return DiagnosticCheck("Session", "UNKNOWN", "No live session registry query is implemented")

    def check_capabilities(self) -> DiagnosticCheck:
        return DiagnosticCheck("Capabilities", "UNKNOWN", "No canonical capability registry was supplied")

    def check_tools(self) -> DiagnosticCheck:
        return DiagnosticCheck("Tools", "UNKNOWN", "No tool invocation health check is implemented")

    def check_workspace(self) -> DiagnosticCheck:
        return DiagnosticCheck("Workspace", "UNKNOWN", "No workspace health probe is implemented")

    def check_process_manager(self) -> DiagnosticCheck:
        return DiagnosticCheck("Process Manager", "NOT_IMPLEMENTED", "No process supervisor health interface exists")

    def check_filesystem(self) -> DiagnosticCheck:
        return DiagnosticCheck("Filesystem", "UNKNOWN", "No authorized filesystem probe was requested")

    def check_shell(self) -> DiagnosticCheck:
        return DiagnosticCheck("Shell", "UNKNOWN", "No shell health probe is implemented")

    def check_git(self) -> DiagnosticCheck:
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                return DiagnosticCheck("Git", "PASS", result.stdout.strip())
            else:
                return DiagnosticCheck("Git", "FAIL", "Git execution failed")
        except FileNotFoundError:
            return DiagnosticCheck("Git", "FAIL", "Git not found")

    def check_secrets(self) -> DiagnosticCheck:
        return DiagnosticCheck("Secrets", "BLOCKED", "No externally authorized secret-access context is available")

    def check_fabric(self) -> DiagnosticCheck:
        return DiagnosticCheck("Fabric", "FAIL", "Fabric reachable check deferred to bootstrap")

    def check_updater(self) -> DiagnosticCheck:
        return DiagnosticCheck("Updater", "UNKNOWN", "No updater health observation is available")

    def check_journal(self) -> DiagnosticCheck:
        return self._engine_subsystem_check("Journal", "journal")

    def _engine_subsystem_check(self, name: str, subsystem: str) -> DiagnosticCheck:
        if self.engine_ref is None:
            return DiagnosticCheck(name, "UNKNOWN", "Runtime engine was not supplied")
        health = self.engine_ref.health_check()
        state = health["subsystems"].get(subsystem, "unknown")
        return DiagnosticCheck(name, state.upper(), "Observed Runtime subsystem state", health)
