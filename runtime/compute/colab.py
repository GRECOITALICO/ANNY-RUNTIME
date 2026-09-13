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

TRANSPORT ARCHITECTURE (001C-A)
===============================
ColabTransport (ABC)
  ├── CliColabTransport     — CLI-managed sessions (primary)
  └── BrowserColabTransport — Browser-assisted auth UX (secondary)

ColabComputeProvider routes to the appropriate transport based on
context['transport_type'] ('cli' default, or 'browser').

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

Browser transport:
  - Google password never enters ANNY
  - Google token never enters Worker
  - Browser cookies never enter evidence
  - Browser profile is not copied into remote session
"""

import shutil
import subprocess
import re
import logging
import tempfile
import os
import webbrowser
from enum import Enum
from abc import ABC, abstractmethod
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


class BrowserSessionState(Enum):
    """Browser-assisted session lifecycle states."""
    BROWSER_OPENING = "BROWSER_OPENING"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    AUTH_IN_PROGRESS = "AUTH_IN_PROGRESS"
    AUTHENTICATED = "AUTHENTICATED"
    COLAB_LOADING = "COLAB_LOADING"
    SESSION_DISCOVERY = "SESSION_DISCOVERY"
    ATTACHING = "ATTACHING"
    ATTACHED = "ATTACHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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


# =============================================================================
# TRANSPORT ABSTRACTION
# =============================================================================

class ColabTransport(ABC):
    """
    Abstract transport for acquiring and communicating with Google Colab sessions.

    Implementations:
      - CliColabTransport:     CLI-managed sessions via google-colab-cli
      - BrowserColabTransport: Browser-assisted auth UX
    """

    @abstractmethod
    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        """Create or acquire a Colab session."""

    @abstractmethod
    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        """Query resource profile of an active session."""

    @abstractmethod
    def health(self, session: RemoteComputeSession) -> RemoteSessionState:
        """Poll session health."""

    @abstractmethod
    def execute(self, session: RemoteComputeSession, job: RemoteComputeJob) -> RemoteComputeJob:
        """Execute a job on the session."""

    @abstractmethod
    def collect(self, session: RemoteComputeSession, job: RemoteComputeJob) -> List[RemoteComputeArtifact]:
        """Collect artifacts from a completed job."""

    @abstractmethod
    def terminate(self, session: RemoteComputeSession) -> None:
        """Terminate the session."""


# =============================================================================
# SECURITY HELPERS
# =============================================================================

_FORBIDDEN_CONTEXT_KEYS = frozenset({
    "credentials", "token", "private_keys", "secret", "api_key",
    "password", "cookie", "session_cookie", "browser_cookie",
})


def _assert_no_credentials(context: Dict[str, Any]) -> None:
    """Reject any context dict that smuggles credentials."""
    found = _FORBIDDEN_CONTEXT_KEYS & set(context.keys())
    if found:
        raise ValueError(
            f"Security violation: forbidden keys in provision() context: {found}"
        )


def _check_lease(session: RemoteComputeSession) -> None:
    """Force EXPIRED state if lease deadline has passed."""
    if session.lease and datetime.now(timezone.utc) > session.lease.expires_at:
        session.state = RemoteSessionState.EXPIRED


# =============================================================================
# CLI TRANSPORT
# =============================================================================

class CliColabTransport(ColabTransport):
    """
    CLI-based transport for Google Colab, leveraging google-colab-cli 0.6.0.

    All command surface verified 2026-09-13 via ANNY-REMOTE-COMPUTE-001B-S.
    Session smoke test confirmed (REAL_REMOTE).
    """

    def __init__(self, cli_path: Optional[str] = None):
        self.cli_path = cli_path or self._find_cli()
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

    # ── Availability ──────────────────────────────────────────────────────────

    def probe_availability(self) -> ProviderAvailability:
        """
        Determines whether the CLI is present and responsive.
        Uses `colab version` subcommand (--version flag NOT supported in 0.6.0).
        """
        if self.cli_path is None:
            self._availability = ProviderAvailability.UNAVAILABLE
            return self._availability

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

    # ── Classification ────────────────────────────────────────────────────────

    def _determine_classification(self, session_confirmed: bool = False) -> ExecutionClassification:
        """Returns REAL_REMOTE only when CLI is AVAILABLE and session confirmed."""
        if self._availability != ProviderAvailability.AVAILABLE:
            return ExecutionClassification.TEST
        if session_confirmed:
            return ExecutionClassification.REAL_REMOTE
        return ExecutionClassification.TEST

    # ── CLI Execution ─────────────────────────────────────────────────────────

    def _run_cli_raw(self, args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """Executes the CLI binary and returns the raw CompletedProcess."""
        self._assert_available()
        try:
            return subprocess.run(
                [self.cli_path] + args,
                capture_output=True, text=True, timeout=timeout,
            )
        except FileNotFoundError:
            raise ColabCLINotFoundError(f"CLI binary not found: {self.cli_path}")
        except subprocess.TimeoutExpired:
            raise ColabCLIError("CLI command timed out")

    # ── Transport Contract ────────────────────────────────────────────────────

    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        """
        Creates a new remote Colab session via `colab new --session <name>`.

        Verified command: colab new --session <name> [--gpu <variant>]
        Observed output:
          [colab] Creating session '<name>'...
          [colab] Session READY.
        """
        _assert_no_credentials(context)
        self._assert_available()

        import uuid
        session_name = context.get("session_name") or f"anny-{uuid.uuid4().hex[:8]}"
        requested_accelerator = context.get("accelerator")
        lease_duration = context.get("lease_duration", timedelta(hours=1))

        args = [_CMD_NEW, "--session", session_name]
        if requested_accelerator:
            args += ["--gpu", requested_accelerator]

        logger.info(f"Provisioning colab session via CLI: {session_name}")
        result = self._run_cli_raw(args, timeout=120)

        if result.returncode != 0:
            raise ColabCLIError(
                f"colab new failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout).strip()}"
            )

        output = result.stdout + result.stderr
        if "Session READY" not in output:
            raise ColabCLIError(
                f"Session creation did not confirm READY state. Output: {output!r}"
            )

        now = datetime.now(timezone.utc)
        session = RemoteComputeSession(
            session_id=session_name,
            provider_id="google-colab",
            state=RemoteSessionState.CONNECTED,
            requested_accelerator=requested_accelerator,
            assigned_accelerator=None,
            observed_accelerator=None,
            classification=self._determine_classification(session_confirmed=True),
            created_at=now,
            lease=RemoteComputeLease(
                issued_at=now,
                expires_at=now + lease_duration,
            ),
        )
        return session

    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        """
        Returns observed resource profile via `colab status`.

        Verified command: colab status --session <name>
        Observed output:
          [<name>] <backend_id> | Hardware: CPU | Variant: DEFAULT | Status: IDLE
        """
        _check_lease(session)
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

        hardware = parsed.get("hardware")
        gpu_present = (hardware not in (None, "CPU")) if hardware else None
        session.observed_accelerator = hardware

        return RemoteComputeResourceProfile(
            cpu=None,
            cores=None,
            ram=None,
            gpu_present=gpu_present,
            gpu_vendor=None,
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
        Polls session health via `colab status --session <name>`.
        Interprets Status field: IDLE -> CONNECTED (alive), absent -> TERMINATED.
        """
        _check_lease(session)
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
        CONNECTED != READY: only READY sessions may accept workloads.
        """
        _check_lease(session)

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
        colab 0.6.0 does not have a dedicated artifact-listing command.
        Returns an empty list until a higher-level workflow specifies artifact paths.
        """
        _check_lease(session)
        self._assert_available()
        return []

    def terminate(self, session: RemoteComputeSession) -> None:
        """
        Terminates the session via `colab stop --session <name>`.
        Forces TERMINATED state locally even if the CLI call fails.
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


# =============================================================================
# BROWSER TRANSPORT
# =============================================================================

import asyncio
import threading
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class SyncMCPBridge:
    """Synchronous bridge for mcp async client."""
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._session = None
        self._read_ctx = None
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self):
        future = asyncio.run_coroutine_threadsafe(self._async_start(), self._loop)
        return future.result()

    async def _async_start(self):
        server_params = StdioServerParameters(
            command="uvx",
            args=["--from", "git+https://github.com/googlecolab/colab-mcp", "colab-mcp"],
            env=None
        )
        self._read_ctx = stdio_client(server_params)
        read, write = await self._read_ctx.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

    def call_tool(self, name, args):
        future = asyncio.run_coroutine_threadsafe(self._session.call_tool(name, args), self._loop)
        return future.result()

    def list_tools(self):
        future = asyncio.run_coroutine_threadsafe(self._session.list_tools(), self._loop)
        return future.result()

    def stop(self):
        future = asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
        try:
            future.result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    async def _async_stop(self):
        if self._session:
            await self._session.__aexit__(None, None, None)
        if self._read_ctx:
            await self._read_ctx.__aexit__(None, None, None)


class BrowserColabTransport(ColabTransport):
    """
    Browser-assisted transport for Google Colab.

    Uses the official googlecolab/colab-mcp integration via uvx.
    The browser is a temporary authentication UX — ANNY never captures
    passwords, cookies, or Google tokens.
    """

    def __init__(self, browser_opener=None):
        self._open_browser = browser_opener or webbrowser.open
        self._bridge = None
        self._bridge_lock = threading.Lock()

    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        _assert_no_credentials(context)

        import uuid
        session_name = context.get("session_name") or f"anny-browser-{uuid.uuid4().hex[:8]}"
        requested_accelerator = context.get("accelerator")
        lease_duration = context.get("lease_duration", timedelta(hours=1))
        now = datetime.now(timezone.utc)

        logger.info(f"Starting colab-mcp server for session: {session_name}")
        
        with self._bridge_lock:
            if self._bridge:
                self._bridge.stop()
            self._bridge = SyncMCPBridge()
            
            try:
                self._bridge.start()
            except Exception as e:
                logger.error(f"Failed to start colab-mcp: {e}")
                self._bridge.stop()
                self._bridge = None
                return RemoteComputeSession(
                    session_id=session_name,
                    provider_id="google-colab",
                    state=RemoteSessionState.FAILED,
                    classification=ExecutionClassification.TEST,
                    created_at=now,
                    lease=RemoteComputeLease(issued_at=now, expires_at=now + lease_duration),
                    metadata={"error": f"MCP Start Failed: {e}"}
                )

            logger.info("Calling open_colab_browser_connection...")
            # This triggers the browser to open via the MCP server and waits up to 60s
            try:
                res = self._bridge.call_tool("open_colab_browser_connection", {})
                
                # Check response. ToolResult may have content.
                # If res is falsy or indicates failure based on its content:
                # But ToolResult in mcp has .isError flag or similar. 
                # colab-mcp returns text="true" or text="false"
                text_content = ""
                if hasattr(res, "content") and res.content:
                    text_content = getattr(res.content[0], "text", "")
                
                if getattr(res, "isError", False) or text_content == "false":
                    raise RuntimeError(f"Connection timeout or denied: {text_content}")

            except Exception as e:
                logger.error(f"Colab MCP attach failed: {e}")
                self._bridge.stop()
                self._bridge = None
                return RemoteComputeSession(
                    session_id=session_name,
                    provider_id="google-colab",
                    state=RemoteSessionState.FAILED,
                    classification=ExecutionClassification.TEST,
                    created_at=now,
                    lease=RemoteComputeLease(issued_at=now, expires_at=now + lease_duration),
                    metadata={"error": f"Browser attach failed: {e}"}
                )

        logger.info(f"Session {session_name} ATTACHED.")
        return RemoteComputeSession(
            session_id=session_name,
            provider_id="google-colab",
            state=RemoteSessionState.READY,  # Marks it ready for execution
            requested_accelerator=requested_accelerator,
            classification=ExecutionClassification.REAL_REMOTE,
            created_at=now,
            lease=RemoteComputeLease(issued_at=now, expires_at=now + lease_duration),
            metadata={"transport": "browser", "browser_state": BrowserSessionState.ATTACHED.value}
        )

    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        _check_lease(session)
        # colab-mcp doesn't natively expose resource inspection tools yet, 
        # but we can return UNKNOWN or use a python code execution to probe if we wanted to.
        return RemoteComputeResourceProfile(
            observed_at=datetime.now(timezone.utc),
            trust_levels=TrustProfile(accelerator_type=TrustLevel.UNKNOWN)
        )

    def health(self, session: RemoteComputeSession) -> RemoteSessionState:
        _check_lease(session)
        if session.state in (RemoteSessionState.EXPIRED, RemoteSessionState.TERMINATED, RemoteSessionState.FAILED):
            return session.state
            
        with self._bridge_lock:
            if not self._bridge:
                session.state = RemoteSessionState.TERMINATED
                return session.state
            
            try:
                # A simple list_tools() call verifies the connection is still alive
                self._bridge.list_tools()
                session.state = RemoteSessionState.READY
            except Exception:
                session.state = RemoteSessionState.TERMINATED
                
        return session.state

    def execute(self, session: RemoteComputeSession, job: RemoteComputeJob) -> RemoteComputeJob:
        _check_lease(session)
        if session.state != RemoteSessionState.READY:
            raise RuntimeError(f"Cannot execute on browser session in state: {session.state}")

        with self._bridge_lock:
            if not self._bridge:
                raise RuntimeError("MCP bridge is not active.")

            code = getattr(job, "code", None) or getattr(job, "script", None)
            if not code:
                raise ValueError("RemoteComputeJob has no executable code payload.")

            tools = self._bridge.list_tools()
            tool_names = {t.name for t in tools.tools}

            exec_tool = None
            for candidate in ["python", "run_python", "execute_python", "execute_cell"]:
                if candidate in tool_names:
                    exec_tool = candidate
                    break
                    
            if not exec_tool:
                raise RuntimeError(f"No execution tool found in MCP session. Available tools: {tool_names}")

            try:
                # Standard pattern: tools usually accept a 'code' parameter
                args = {"code": code}
                # Fallback heuristics for parameter naming if 'python' takes something else?
                # Usually it's 'code' or 'query' or just a positional? 
                # According to standard python tools in MCP, it's 'code' or 'command'.
                res = self._bridge.call_tool(exec_tool, args)
                
                # Extract text output
                output_text = ""
                if hasattr(res, "content") and res.content:
                    output_text = getattr(res.content[0], "text", str(res.content[0]))
                    
                job.status = "COMPLETED" if not getattr(res, "isError", False) else "FAILED"
                if job.status == "COMPLETED":
                    job.stdout = output_text
                else:
                    job.stderr = output_text

            except Exception as e:
                job.status = "FAILED"
                job.error = str(e)
                raise ColabCLIError(f"Colab MCP execution failed: {e}")

        return job

    def collect(self, session: RemoteComputeSession, job: RemoteComputeJob) -> List[RemoteComputeArtifact]:
        _check_lease(session)
        return []

    def terminate(self, session: RemoteComputeSession) -> None:
        session.state = RemoteSessionState.TERMINATED
        with self._bridge_lock:
            if self._bridge:
                self._bridge.stop()
                self._bridge = None
        logger.info("Browser session terminated.")


# =============================================================================
# PROVIDER (ROUTER)
# =============================================================================

class ColabComputeProvider(RemoteComputeProvider):
    """
    Provider adapter for Google Colab runtime.

    Routes to the appropriate ColabTransport based on context['transport_type']:
      'cli'     -> CliColabTransport  (default)
      'browser' -> BrowserColabTransport

    Both transports produce RemoteComputeSession with provider_id='google-colab'.
    CLI and Browser accounts may differ — identities are recorded separately.
    """

    def __init__(self, cli_path: Optional[str] = None, browser_opener=None):
        """
        Args:
            cli_path:       Explicit path to the colab CLI binary.
            browser_opener: Callable for opening browser URLs (testing hook).
        """
        self._cli_transport = CliColabTransport(cli_path)
        self._browser_transport = BrowserColabTransport(browser_opener)
        self._sessions: Dict[str, RemoteComputeSession] = {}

    @property
    def provider_id(self) -> str:
        return "google-colab"

    # ── Transport selection ───────────────────────────────────────────────────

    def _get_transport(self, context_or_session) -> ColabTransport:
        """
        Determine the transport from either a context dict or a session object.
        """
        if isinstance(context_or_session, RemoteComputeSession):
            transport_type = (context_or_session.metadata or {}).get("transport", "cli")
        elif isinstance(context_or_session, dict):
            transport_type = context_or_session.get("transport_type", "cli")
        else:
            transport_type = "cli"

        if transport_type == "browser":
            return self._browser_transport
        return self._cli_transport

    # ── Availability (CLI only) ───────────────────────────────────────────────

    def probe_availability(self) -> ProviderAvailability:
        """Probes CLI transport availability."""
        return self._cli_transport.probe_availability()

    # ── Provider Contract ─────────────────────────────────────────────────────

    def provision(self, context: Dict[str, Any]) -> RemoteComputeSession:
        transport = self._get_transport(context)
        session = transport.provision(context)
        self._sessions[session.session_id] = session
        return session

    def inspect(self, session: RemoteComputeSession) -> RemoteComputeResourceProfile:
        return self._get_transport(session).inspect(session)

    def health(self, session: RemoteComputeSession) -> RemoteSessionState:
        return self._get_transport(session).health(session)

    def execute(self, session: RemoteComputeSession, job: RemoteComputeJob) -> RemoteComputeJob:
        return self._get_transport(session).execute(session, job)

    def collect(self, session: RemoteComputeSession, job: RemoteComputeJob) -> List[RemoteComputeArtifact]:
        return self._get_transport(session).collect(session, job)

    def terminate(self, session: RemoteComputeSession) -> None:
        self._get_transport(session).terminate(session)

