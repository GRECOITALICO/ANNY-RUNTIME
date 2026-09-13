"""
Google Colab remote compute provider.

CLI DISCOVERY RECORD
====================
Performed: 2026-09-13
Host: ANNY-RUNTIME development environment

Commands run:
  which colab                → EXIT:1 (not found)
  which google-colab-cli     → EXIT:1 (not found)
  which colab-cli            → EXIT:1 (not found)
  pip show google-colab-cli  → WARNING: Package not found
  pip show colab             → WARNING: Package not found
  pip list | grep -i colab   → (empty)

Result:
  PROVIDER_UNAVAILABLE — no colab CLI binary present on this host.

COMMAND CONTRACT
================
CLI command surface is NOT yet discovered because the CLI is not installed.
Commands in this file are PLACEHOLDERS ONLY — gated behind availability check.
They MUST be reconciled against the actual CLI help output before use.

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
import json
import logging
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


class ColabComputeProvider(RemoteComputeProvider):
    """
    Provider adapter for Google Colab runtime.

    This adapter targets the `colab` CLI (or a user-specified binary).
    The CLI command surface is determined at runtime by probing the installed
    binary. No commands are assumed from memory.

    When the CLI is absent, availability is UNAVAILABLE and all operations
    that require real backend contact are rejected.
    """

    # These are CANDIDATE command fragments inferred from common CLI patterns.
    # They MUST be validated against actual `colab --help` output before use.
    # Marked as UNVERIFIED until CLI is installed and probed.
    _CMD_NEW        = ["new"]           # UNVERIFIED
    _CMD_SESSIONS   = ["sessions"]      # UNVERIFIED
    _CMD_STATUS     = ["status"]        # UNVERIFIED
    _CMD_STOP       = ["stop"]          # UNVERIFIED

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

    # ──────────────────────────────────────────────────────────────────────────
    # AVAILABILITY
    # ──────────────────────────────────────────────────────────────────────────

    def probe_availability(self) -> ProviderAvailability:
        """
        Determines whether the CLI is present and responsive.

        Records actual version and help text for audit.
        Does NOT perform authentication.
        Does NOT create a session.
        """
        if self.cli_path is None:
            self._availability = ProviderAvailability.UNAVAILABLE
            return self._availability

        # Try --version
        try:
            r = subprocess.run(
                [self.cli_path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            self._cli_version = (r.stdout or r.stderr).strip()
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            self._availability = ProviderAvailability.UNAVAILABLE
            logger.warning(f"Colab CLI not found at {self.cli_path}: {e}")
            return self._availability

        # Try --help
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

    # ──────────────────────────────────────────────────────────────────────────
    # CLASSIFICATION
    # ──────────────────────────────────────────────────────────────────────────

    def _determine_classification(self) -> ExecutionClassification:
        """
        Returns REAL_REMOTE only when the CLI is installed and a real backend
        interaction is confirmed. Returns TEST otherwise.
        """
        if self._availability != ProviderAvailability.AVAILABLE:
            return ExecutionClassification.TEST
        # Placeholder: when CLI is available, a real auth/status probe would
        # go here. Until CLI is installed and command surface verified,
        # conservative TEST classification is returned even if binary exists.
        return ExecutionClassification.TEST

    # ──────────────────────────────────────────────────────────────────────────
    # CLI EXECUTION
    # ──────────────────────────────────────────────────────────────────────────

    def _run_cli(self, args: List[str], timeout: int = 30) -> Dict[str, Any]:
        """
        Executes the CLI binary and returns parsed JSON stdout.

        Raises ColabCLINotFoundError if binary absent.
        Raises ColabCLIError on non-zero exit or parse failure.
        """
        self._assert_available()
        try:
            result = subprocess.run(
                [self.cli_path] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise ColabCLIError(
                    f"CLI exited {result.returncode}: {(result.stderr or result.stdout).strip()}"
                )
            return json.loads(result.stdout)
        except FileNotFoundError:
            raise ColabCLINotFoundError(f"CLI binary not found: {self.cli_path}")
        except subprocess.TimeoutExpired:
            raise ColabCLIError("CLI command timed out")
        except json.JSONDecodeError as e:
            raise ColabCLIError(f"CLI returned non-JSON output: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # SECURITY
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _assert_no_credentials(context: Dict[str, Any]) -> None:
        forbidden = {"credentials", "token", "private_keys", "secret", "api_key"}
        found = forbidden & set(context.keys())
        if found:
            raise ValueError(
                f"Security violation: forbidden keys in provision() context: {found}"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # LEASE
    # ──────────────────────────────────────────────────────────────────────────

    def _check_lease(self, session: RemoteComputeSession) -> None:
        """Force EXPIRED state if lease deadline has passed."""
        if session.lease and datetime.now(timezone.utc) > session.lease.expires_at:
            session.state = RemoteSessionState.EXPIRED

    # ──────────────────────────────────────────────────────────────────────────
    # PROVIDER CONTRACT IMPLEMENTATION
    # ──────────────────────────────────────────────────────────────────────────

    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        """
        Creates a new remote Colab session.

        REQUIRES CLI to be available. If CLI absent → raises ColabCLINotFoundError.

        Context keys:
          accelerator  (str, optional) : Requested accelerator preference (NOT guaranteed)
          lease_duration (timedelta, optional) : Default 1 hour
        """
        self._assert_no_credentials(context)
        self._assert_available()

        requested_accelerator = context.get("accelerator", "UNKNOWN")
        classification = self._determine_classification()

        # NOTE: The actual CLI command for session creation is UNVERIFIED.
        # The candidate command `colab new` will be validated once CLI is installed.
        # _run_cli(self._CMD_NEW + [...]) would go here.
        raise NotImplementedError(
            "Session creation requires a verified CLI command surface. "
            "Install the colab CLI, run probe_availability(), then reconcile "
            "_CMD_NEW against `colab new --help` output."
        )

    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        """
        Returns observed resource profile for a session.

        All fields default to None with TrustLevel.UNKNOWN.
        Values are only promoted to OBSERVED when returned by actual CLI response.
        """
        self._check_lease(session)
        if session.state in (RemoteSessionState.EXPIRED, RemoteSessionState.TERMINATED):
            raise RuntimeError(f"Cannot inspect session in state {session.state.value}")

        self._assert_available()

        # NOTE: CLI command UNVERIFIED. Candidate: `colab status <session_id>`
        # _run_cli(self._CMD_STATUS + [session.session_id]) would go here.
        # Until verified, return all-UNKNOWN profile.
        return RemoteComputeResourceProfile(
            cpu=None,
            cores=None,
            ram=None,
            gpu_present=None,
            gpu_vendor=None,
            gpu_model=None,
            vram=None,
            accelerator_type=None,
            runtime=None,
            python_version=None,
            observed_at=datetime.now(timezone.utc),
            trust_levels=TrustProfile()  # all UNKNOWN
        )

    def health(self, session: RemoteComputeSession) -> RemoteSessionState:
        """
        Polls the actual session health via CLI.

        Enforces lease expiry before polling.
        """
        self._check_lease(session)
        if session.state in (
            RemoteSessionState.EXPIRED,
            RemoteSessionState.TERMINATED,
            RemoteSessionState.FAILED,
        ):
            return session.state

        self._assert_available()

        # NOTE: CLI command UNVERIFIED. Candidate: `colab status <session_id>`
        # Full implementation requires verified command surface.
        raise NotImplementedError(
            "health() requires a verified CLI status command. "
            "Reconcile _CMD_STATUS against `colab status --help` output."
        )

    def execute(self, session: RemoteComputeSession, job: RemoteComputeJob) -> RemoteComputeJob:
        """CONNECTED != READY: only READY sessions may execute."""
        self._check_lease(session)

        if session.state == RemoteSessionState.TERMINATED:
            raise RuntimeError("Cannot execute on TERMINATED session.")
        if session.state != RemoteSessionState.READY:
            raise RuntimeError(
                f"Cannot execute. Session state is {session.state.value}. Must be READY."
            )

        self._assert_available()

        # NOTE: CLI command for remote execution UNVERIFIED.
        raise NotImplementedError(
            "execute() requires a verified CLI exec/run command. "
            "Reconcile against `colab exec --help` or `colab run --help`."
        )

    def collect(self, session: RemoteComputeSession, job: RemoteComputeJob) -> List[RemoteComputeArtifact]:
        """Collects artifacts from a completed job."""
        self._check_lease(session)
        self._assert_available()

        # NOTE: CLI artifact collection command UNVERIFIED.
        raise NotImplementedError(
            "collect() requires a verified CLI artifact command. "
            "Reconcile against installed CLI help."
        )

    def terminate(self, session: RemoteComputeSession) -> None:
        """
        Terminates the session.

        Forces TERMINATED state locally even if the CLI call fails,
        to prevent zombie sessions from being reused.
        """
        try:
            self._assert_available()
            # NOTE: CLI stop command UNVERIFIED. Candidate: `colab stop <session_id>`
            # _run_cli(self._CMD_STOP + [session.session_id]) would go here.
        except (ColabCLINotFoundError, NotImplementedError):
            pass  # CLI absent — force state locally
        finally:
            session.state = RemoteSessionState.TERMINATED
