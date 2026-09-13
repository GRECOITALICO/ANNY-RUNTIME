"""
Google Colab remote compute provider.

CLI DISCOVERY RECORD
====================
Performed: 2026-09-13
Mission:   ANNY-REMOTE-COMPUTE-001B-S
Host:      ANNY development host (Debian 6.12.107, Python 3.13.5, user=anny)

Installation:
  Package: google-colab-cli==0.6.0
  Method:  python3 -m venv + pip install (uv unavailable)
  Venv:    ~/.local/share/google-colab-cli-venv
  Binary:  ~/.local/bin/colab (symlink)
  Dependency fix: jupyter-kernel-client pinned to 0.15.0
    (0.6.0 ships 1.0.2 which removed KernelClient - renamed JupyterKernelClient)

Commands Verified (colab --help, 2026-09-13):
  colab new     --session <name> [--gpu <T4|L4|G4|H100|A100>] [--tpu <v5e1|v6e1>]
  colab sessions
  colab status  --session <name>
  colab exec    --session <name> --file <path> [--timeout <float>]
  colab run     <script> [--session <name>] [--gpu <variant>] [--keep] [--timeout <float>]
  colab stop    --session <name>
  colab whoami
  colab version

Auth strategies (--auth flag on root command):
  oauth2  -- default (InstalledAppFlow, browser redirect)
  adc     -- Application Default Credentials

Session status output format (colab 0.6.0 observed):
  [<name>] <backend_id> | Hardware: <CPU|GPU> | Variant: DEFAULT | Status: IDLE

colab new output observed:
  [colab] Creating session '<name>'...
  [colab] Session READY.

colab stop output observed:
  [colab] Stopping session '<name>'...
  [colab] Session terminated.

colab sessions (empty) output observed:
  [colab] No active sessions found on server.

REAL SESSION SMOKE:
  Executed: print("ANNY_REMOTE_SMOKE_OK")
  Result:   ANNY_REMOTE_SMOKE_OK  (REAL_REMOTE confirmed 2026-09-13)

FABRICATION POLICY
==================
No hardware values (CPU, RAM, GPU, cores) may be hardcoded.
All resource fields default to None / UNKNOWN trust until observed from the
actual backend response.

SECURITY
========
Credentials must never be passed through provision() context.
provision() raises ValueError if 'credentials', 'token', or 'private_keys'
are present in the context dict.
"""

import shutil
import subprocess
import re
import logging
import tempfile
import os
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from runtime.compute.models import (
    RemoteComputeSession,
    RemoteComputeResourceProfile,
    RemoteComputeJob,
    RemoteComputeArtifact,
    RemoteComputeLease,
    RemoteSessionState,
    ExecutionClassification,
    TrustLevel,
    TrustProfile,
)
from runtime.compute.provider import RemoteComputeProvider

logger = logging.getLogger(__name__)


class ProviderAvailability(Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class ColabCLIError(Exception):
    pass


class ColabCLINotFoundError(ColabCLIError):
    """Raised when the colab CLI binary cannot be found on the host."""
    pass


class ColabSessionNotFoundError(ColabCLIError):
    """Raised when a named session does not exist on the backend."""
    pass


# ── Verified CLI command fragments (sourced from installed colab 0.6.0) ───────
# Verified 2026-09-13 via ANNY-REMOTE-COMPUTE-001B-S
_CMD_NEW      = "new"       # colab new --session <name> [--gpu <variant>]
_CMD_SESSIONS = "sessions"  # colab sessions
_CMD_STATUS   = "status"    # colab status --session <name>
_CMD_EXEC     = "exec"      # colab exec --session <name> --file <path>
_CMD_STOP     = "stop"      # colab stop --session <name>
_CMD_VERSION  = "version"   # colab version (--version flag NOT supported in 0.6.0)


def _parse_session_status_line(line: str) -> Dict[str, Any]:
    """
    Parse the status output format observed from colab 0.6.0:
      [<name>] <backend_id> | Hardware: <hw> | Variant: <var> | Status: <status>
    Returns dict with keys: name, backend_id, hardware, variant, status.
    Returns empty dict on parse failure (non-fatal).
    """
    pattern = (
        r'\[(.+?)\]\s+(\S+)\s*\|\s*Hardware:\s*(\S+)\s*\|\s*Variant:\s*(\S+)'
        r'(?:\s*\|\s*Status:\s*(\S+))?'
    )
    m = re.search(pattern, line)
    if not m:
        return {}
    return {
        "name": m.group(1),
        "backend_id": m.group(2),
        "hardware": m.group(3),
        "variant": m.group(4),
        "status": m.group(5) or "UNKNOWN",
    }


class ColabComputeProvider(RemoteComputeProvider):
    """
    Provider adapter for Google Colab runtime.

    Targets the `colab` CLI (google-colab-cli 0.6.0).
    CLI command surface verified 2026-09-13 via ANNY-REMOTE-COMPUTE-001B-S.
    Session smoke test confirmed (REAL_REMOTE).

    When the CLI is absent, availability is UNAVAILABLE and all operations
    that require real backend contact are rejected.
    """

    def __init__(self, cli_path: Optional[str] = None):
        """
        Args:
            cli_path: Explicit path to the colab CLI. If None, searches PATH
                      for 'colab' then 'google-colab-cli'.
        """
        self.cli_path = cli_path or self._find_cli()
        self._sessions: Dict[str, RemoteComputeSession] = {}
        self._availability: Optional[ProviderAvailability] = None
        self._cli_version: Optional[str] = None
        self._cli_help: Optional[str] = None

    @staticmethod
    def _find_cli() -> Optional[str]:
        """Search PATH for known CLI binary names. Returns path or None."""
        for candidate in ("colab", "google-colab-cli", "colab-cli"):
            found = shutil.which(candidate)
            if found:
                return found
        return None

    @property
    def provider_id(self) -> str:
        return "google-colab"

    # -------------------------------------------------------------------------
    # AVAILABILITY
    # -------------------------------------------------------------------------

    def probe_availability(self) -> ProviderAvailability:
        """
        Determines whether the CLI is present and responsive.

        Uses `colab version` subcommand (--version flag NOT supported in 0.6.0).
        Does NOT perform authentication.
        Does NOT create a session.
        """
        if self.cli_path is None:
            self._availability = ProviderAvailability.UNAVAILABLE
            return self._availability

        # Use verified `colab version` subcommand
        try:
            r = subprocess.run(
                [self.cli_path, _CMD_VERSION],
                capture_output=True, text=True, timeout=10
            )
            self._cli_version = (r.stdout or r.stderr).strip()
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            self._availability = ProviderAvailability.UNAVAILABLE
            logger.warning(f"Colab CLI not found at {self.cli_path}: {e}")
            return self._availability

        # Capture --help for audit record
        try:
            r = subprocess.run(
                [self.cli_path, "--help"],
                capture_output=True, text=True, timeout=10
            )
            self._cli_help = r.stdout or r.stderr
        except Exception:
            self._cli_help = None

        self._availability = ProviderAvailability.AVAILABLE
        return self._availability

    def _assert_available(self) -> None:
        """Raises ColabCLINotFoundError if provider is unavailable."""
        if self._availability is None:
            self.probe_availability()
        if self._availability != ProviderAvailability.AVAILABLE:
            raise ColabCLINotFoundError(
                f"Colab CLI not available. cli_path={self.cli_path!r}. "
                "Install google-colab-cli and re-run probe_availability()."
            )

    # -------------------------------------------------------------------------
    # CLASSIFICATION
    # -------------------------------------------------------------------------

    def _determine_classification(self, session_confirmed: bool = False) -> ExecutionClassification:
        """
        Returns REAL_REMOTE only when:
          - CLI is installed and AVAILABLE
          - A real authenticated backend session was confirmed

        Returns TEST otherwise.
        """
        if self._availability != ProviderAvailability.AVAILABLE:
            return ExecutionClassification.TEST
        if session_confirmed:
            return ExecutionClassification.REAL_REMOTE
        return ExecutionClassification.TEST

    # -------------------------------------------------------------------------
    # CLI EXECUTION HELPERS
    # -------------------------------------------------------------------------

    def _run_cli_raw(self, args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """
        Executes the CLI binary and returns the raw CompletedProcess.
        Raises ColabCLINotFoundError if binary absent.
        """
        self._assert_available()
        try:
            return subprocess.run(
                [self.cli_path] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            raise ColabCLINotFoundError(f"CLI binary not found: {self.cli_path}")
        except subprocess.TimeoutExpired:
            raise ColabCLIError("CLI command timed out")

    # -------------------------------------------------------------------------
    # SECURITY
    # -------------------------------------------------------------------------

    @staticmethod
    def _assert_no_credentials(context: Dict[str, Any]) -> None:
        forbidden = {"credentials", "token", "private_keys", "secret", "api_key"}
        found = forbidden & set(context.keys())
        if found:
            raise ValueError(
                f"Security violation: forbidden keys in provision() context: {found}"
            )

    # -------------------------------------------------------------------------
    # LEASE
    # -------------------------------------------------------------------------

    def _check_lease(self, session: RemoteComputeSession) -> None:
        """Force EXPIRED state if lease deadline has passed."""
        if session.lease and datetime.now(timezone.utc) > session.lease.expires_at:
            session.state = RemoteSessionState.EXPIRED

    # -------------------------------------------------------------------------
    # PROVIDER CONTRACT IMPLEMENTATION
    # -------------------------------------------------------------------------

    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        """
        Creates a new remote Colab session via `colab new --session <name>`.

        Verified command: colab new --session <name> [--gpu <variant>]
        Observed output:
          [colab] Creating session '<name>'...
          [colab] Session READY.

        Context keys:
          session_name   (str, optional)      : Session name. Auto-generated if absent.
          accelerator    (str, optional)      : GPU variant (T4/L4/G4/H100/A100).
          lease_duration (timedelta, optional): Default 1 hour.
        """
        self._assert_no_credentials(context)
        self._assert_available()

        import uuid
        session_name = context.get("session_name") or f"anny-{uuid.uuid4().hex[:8]}"
        requested_accelerator = context.get("accelerator")
        lease_duration = context.get("lease_duration", timedelta(hours=1))

        # Build verified CLI command
        args = [_CMD_NEW, "--session", session_name]
        if requested_accelerator:
            args += ["--gpu", requested_accelerator]

        logger.info(f"Provisioning colab session: {session_name}")
        result = self._run_cli_raw(args, timeout=120)

        if result.returncode != 0:
            raise ColabCLIError(
                f"colab new failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout).strip()}"
            )

        # Verify "Session READY" in output (observed from 0.6.0)
        output = result.stdout + result.stderr
        if "Session READY" not in output:
            raise ColabCLIError(
                f"Session creation did not confirm READY state. Output: {output!r}"
            )

        now = datetime.now(timezone.utc)
        session = RemoteComputeSession(
            session_id=session_name,
            provider_id=self.provider_id,
            state=RemoteSessionState.CONNECTED,
            requested_accelerator=requested_accelerator,
            assigned_accelerator=None,   # not yet observed from status
            observed_accelerator=None,
            classification=self._determine_classification(session_confirmed=True),
            created_at=now,
            lease=RemoteComputeLease(
                granted_at=now,
                expires_at=now + lease_duration,
            ),
        )
        self._sessions[session_name] = session
        return session

    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        """
        Returns observed resource profile for a session via `colab status`.

        Verified command: colab status --session <name>
        Observed output:
          [<name>] <backend_id> | Hardware: CPU | Variant: DEFAULT | Status: IDLE
        """
        self._check_lease(session)
        if session.state in (RemoteSessionState.EXPIRED, RemoteSessionState.TERMINATED):
            raise RuntimeError(f"Cannot inspect session in state {session.state.value}")

        self._assert_available()

        result = self._run_cli_raw(
            [_CMD_STATUS, "--session", session.session_id], timeout=30
        )

        parsed = {}
        if result.returncode == 0:
            for line in (result.stdout + result.stderr).splitlines():
                p = _parse_session_status_line(line)
                if p:
                    parsed = p
                    break

        # Map observed hardware string -> fields; default UNKNOWN
        hardware = parsed.get("hardware")   # e.g. "CPU", "T4"
        gpu_present = (hardware not in (None, "CPU")) if hardware else None

        # Populate session observed accelerator from status
        session.observed_accelerator = hardware

        return RemoteComputeResourceProfile(
            cpu=None,               # not reported by colab status
            cores=None,
            ram=None,
            gpu_present=gpu_present,
            gpu_vendor=None,        # not reported by colab status
            gpu_model=hardware if gpu_present else None,
            vram=None,
            accelerator_type=hardware,
            runtime=None,
            python_version=None,
            observed_at=datetime.now(timezone.utc),
            trust_levels=TrustProfile(
                accelerator_type=TrustLevel.OBSERVED if hardware else TrustLevel.UNKNOWN,
            )
        )

    def health(self, session: RemoteComputeSession) -> RemoteSessionState:
        """
        Polls the actual session health via `colab status --session <name>`.

        Verified command: colab status --session <name>
        Interprets Status field: IDLE -> CONNECTED (alive), absent session -> TERMINATED.
        """
        self._check_lease(session)
        if session.state in (
            RemoteSessionState.EXPIRED,
            RemoteSessionState.TERMINATED,
            RemoteSessionState.FAILED,
        ):
            return session.state

        self._assert_available()

        result = self._run_cli_raw(
            [_CMD_STATUS, "--session", session.session_id], timeout=30
        )

        output = result.stdout + result.stderr
        if result.returncode != 0 or "not found" in output.lower():
            session.state = RemoteSessionState.TERMINATED
            return session.state

        parsed = {}
        for line in output.splitlines():
            p = _parse_session_status_line(line)
            if p:
                parsed = p
                break

        cli_status = parsed.get("status", "UNKNOWN").upper()
        if cli_status in ("IDLE", "BUSY", "RUNNING"):
            session.state = RemoteSessionState.CONNECTED
        elif cli_status == "TERMINATED":
            session.state = RemoteSessionState.TERMINATED
        elif cli_status == "FAILED":
            session.state = RemoteSessionState.FAILED

        return session.state

    def execute(self, session: RemoteComputeSession, job: RemoteComputeJob) -> RemoteComputeJob:
        """
        Executes code via `colab exec --session <name> --file <path>`.

        Verified command: colab exec --session <name> --file <path> [--timeout <float>]
        CONNECTED != READY: only READY sessions may accept workloads.
        """
        self._check_lease(session)

        if session.state == RemoteSessionState.TERMINATED:
            raise RuntimeError("Cannot execute on TERMINATED session.")
        if session.state != RemoteSessionState.READY:
            raise RuntimeError(
                f"Cannot execute. Session state is {session.state.value}. Must be READY."
            )

        self._assert_available()

        code = getattr(job, "code", None) or getattr(job, "script", None)
        if not code:
            raise ValueError("RemoteComputeJob has no executable code payload.")

        # Write code to a temp file for colab exec --file
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, prefix="anny_job_"
        ) as tf:
            tf.write(code)
            tmp_path = tf.name

        try:
            args = [_CMD_EXEC, "--session", session.session_id, "--file", tmp_path]
            timeout = getattr(job, "timeout_seconds", 30) or 30
            result = self._run_cli_raw(args, timeout=int(timeout) + 10)
        finally:
            os.unlink(tmp_path)

        if result.returncode != 0:
            job.state = "FAILED"
            job.error = (result.stderr or result.stdout).strip()
            raise ColabCLIError(
                f"colab exec failed (exit {result.returncode}): {job.error}"
            )

        job.state = "COMPLETED"
        job.stdout = result.stdout
        return job

    def collect(self, session: RemoteComputeSession, job: RemoteComputeJob) -> List[RemoteComputeArtifact]:
        """
        Collect artifacts from a completed job.

        colab 0.6.0 does not have a dedicated artifact-listing command;
        `colab download` and `colab ls` are available for file transfer.
        Returns an empty list until a higher-level workflow specifies artifact paths.
        """
        self._check_lease(session)
        self._assert_available()
        return []

    def terminate(self, session: RemoteComputeSession) -> None:
        """
        Terminates the session via `colab stop --session <name>`.

        Verified command: colab stop --session <name>
        Observed output:
          [colab] Stopping session '<name>'...
          [colab] Session terminated.

        Forces TERMINATED state locally even if the CLI call fails,
        to prevent zombie sessions from being reused.
        """
        try:
            self._assert_available()
            result = self._run_cli_raw(
                [_CMD_STOP, "--session", session.session_id], timeout=60
            )
            if result.returncode != 0:
                output = (result.stderr or result.stdout).strip()
                logger.warning(
                    f"colab stop returned exit {result.returncode}: {output}"
                )
        except (ColabCLINotFoundError, ColabCLIError) as e:
            logger.warning(f"terminate(): CLI error ignored, forcing TERMINATED: {e}")
        finally:
            session.state = RemoteSessionState.TERMINATED
