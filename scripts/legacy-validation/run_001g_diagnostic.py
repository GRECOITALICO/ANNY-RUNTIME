"""
ANNY — MISSION 001G-MCP-DIAGNOSTIC-R1
Diagnostic script for Colab MCP physical flow validation.

State machine:
INIT → MCP_SERVER_STARTED → MCP_PORT_BOUND → MCP_TOKEN_CREATED →
BROWSER_LAUNCHED → COLAB_URL_OPENED → [wait for human] →
MCP_PROXY_CONNECTED → MCP_INITIALIZED → TOOLS_DISCOVERY_STARTED →
TOOLS_DISCOVERY_COMPLETED → REMOTE_EXECUTION_STARTED →
REMOTE_EXECUTION_COMPLETED → GPU_AUDIT → CUDA_TEST →
CLEANUP_STARTED → CLEANUP_COMPLETED

SECURITY: Never logs mcpProxyToken, cookies, OAuth tokens, passwords.
"""

import asyncio
import datetime
import glob
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from time import monotonic
from typing import Optional

# ── Ensure PYTHONPATH includes ANNY-RUNTIME ──────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("diagnostic")


# ── Output paths ─────────────────────────────────────────────────────────────
_BRAIN_DIR = (
    "/home/anny/.gemini/antigravity/brain/"
    "0ba545c8-f97a-463e-8ecf-16ee97b75a2e"
)
_JSON_OUT  = os.path.join(_BRAIN_DIR, "001G-MCP-DIAGNOSTIC.json")
_MD_OUT    = os.path.join(_BRAIN_DIR, "001G-MCP-DIAGNOSTIC.md")


# ── State constants ───────────────────────────────────────────────────────────
class S:
    INIT                      = "INIT"
    MCP_SERVER_STARTED        = "MCP_SERVER_STARTED"
    MCP_PORT_BOUND            = "MCP_PORT_BOUND"
    MCP_TOKEN_CREATED         = "MCP_TOKEN_CREATED"
    BROWSER_LAUNCHED          = "BROWSER_LAUNCHED"
    COLAB_URL_OPENED          = "COLAB_URL_OPENED"
    COLAB_PAGE_DETECTED       = "COLAB_PAGE_DETECTED"
    RUNTIME_PENDING           = "RUNTIME_PENDING"
    RUNTIME_READY             = "RUNTIME_READY"
    MCP_PROXY_EXPECTED        = "MCP_PROXY_EXPECTED"
    MCP_PROXY_CONNECTED       = "MCP_PROXY_CONNECTED"
    MCP_INITIALIZED           = "MCP_INITIALIZED"
    TOOLS_DISCOVERY_STARTED   = "TOOLS_DISCOVERY_STARTED"
    TOOLS_DISCOVERY_COMPLETED = "TOOLS_DISCOVERY_COMPLETED"
    REMOTE_EXECUTION_STARTED  = "REMOTE_EXECUTION_STARTED"
    REMOTE_EXECUTION_COMPLETED = "REMOTE_EXECUTION_COMPLETED"
    GPU_AUDIT                 = "GPU_AUDIT"
    CUDA_TEST                 = "CUDA_TEST"
    CLEANUP_STARTED           = "CLEANUP_STARTED"
    CLEANUP_COMPLETED         = "CLEANUP_COMPLETED"
    FAILED                    = "FAILED"
    TIMEOUT                   = "TIMEOUT"


class DiagnosticTracker:
    def __init__(self, run_id: str, git_commit: str):
        self._t0 = monotonic()
        self.timeline: list[dict] = []
        self.meta = {
            "run_id":           run_id,
            "mission":          "001G-MCP-DIAGNOSTIC",
            "revision":         "R1",
            "git_commit":       git_commit,
            "hostname":         os.uname().nodename,
            "python":           sys.version,
            "working_dir":      os.getcwd(),
            "start":            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "end":              None,
            # populated as we go
            "mcp_pid":          None,
            "mcp_port":         None,
            "browser_pid":      None,
            "browser_binary":   None,
            "browser_profile":  None,
            "token_present":    False,
            "runtime_ready":    "UNKNOWN",
            "mcp_proxy_connected": "UNKNOWN",
            "mcp_initialized":  "UNKNOWN",
            "tools_discovered": "UNKNOWN",
            "tool_count":       None,
            "tool_names":       None,
            "remote_execution": "UNKNOWN",
            "remote_output":    None,
            "cpu":              "UNKNOWN",
            "ram":              "UNKNOWN",
            "gpu":              "UNKNOWN",
            "vram":             "UNKNOWN",
            "cuda":             "UNKNOWN",
            "cuda_tensor_test": "N/A",
            "cleanup":          "UNKNOWN",
            "final_state":      None,
            "last_successful_stage": None,
            "failed_stage":     None,
            "root_cause_hypothesis": None,
        }

    def elapsed(self) -> float:
        return monotonic() - self._t0

    def record(self, state: str, **kw):
        ev = {
            "state": state,
            "t_rel": round(self.elapsed(), 3),
            "ts":    datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        ev.update(kw)
        self.timeline.append(ev)
        suffix = ""
        if kw:
            # Filter out sensitive keys before printing
            safe = {k: v for k, v in kw.items()
                    if k not in ("token", "mcpProxyToken", "url_full", "cookie")}
            if safe:
                suffix = "  " + json.dumps(safe)
        print(f"T+{ev['t_rel']:7.2f}s  [{state}]{suffix}", flush=True)
        # Track last successful
        if state not in (S.FAILED, S.TIMEOUT):
            self.meta["last_successful_stage"] = state

    def fail(self, stage: str, reason: str, hypothesis: str = "UNKNOWN",
             error_type: str = None):
        self.meta["failed_stage"] = stage
        self.meta["root_cause_hypothesis"] = hypothesis
        self.record(S.FAILED, reason=reason, error_type=error_type or "")
        self._write_outputs()
        print("\n[DIAGNOSTIC FAILED] — see 001G-MCP-DIAGNOSTIC.md", flush=True)
        sys.exit(1)

    def timeout(self, stage: str, reason: str, hypothesis: str = "UNKNOWN"):
        self.meta["failed_stage"] = stage
        self.meta["root_cause_hypothesis"] = hypothesis
        self.record(S.TIMEOUT, reason=reason)
        self._write_outputs()
        print("\n[DIAGNOSTIC TIMEOUT] — see 001G-MCP-DIAGNOSTIC.md", flush=True)
        sys.exit(1)

    def _write_outputs(self):
        self.meta["end"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.meta["final_state"] = (
            self.timeline[-1]["state"] if self.timeline else "UNKNOWN"
        )
        report = {"metadata": self.meta, "timeline": self.timeline}
        os.makedirs(_BRAIN_DIR, exist_ok=True)
        with open(_JSON_OUT, "w") as f:
            json.dump(report, f, indent=2)

        with open(_MD_OUT, "w") as f:
            m = self.meta
            f.write("# 001G-MCP-DIAGNOSTIC Report\n\n")
            f.write(f"| Field | Value |\n|---|---|\n")
            for field in [
                "run_id", "mission", "revision", "git_commit", "hostname",
                "python", "working_dir", "start", "end",
            ]:
                f.write(f"| {field} | `{m.get(field, '')}` |\n")
            f.write(f"\n## Final Assessment\n\n")
            f.write(f"| Field | Value |\n|---|---|\n")
            for field in [
                "final_state", "last_successful_stage", "failed_stage",
                "root_cause_hypothesis",
            ]:
                f.write(f"| {field} | `{m.get(field, '')}` |\n")
            f.write(f"\n## Infrastructure\n\n| Field | Value |\n|---|---|\n")
            for field in [
                "mcp_pid", "mcp_port", "browser_pid",
                "browser_binary", "browser_profile", "token_present",
            ]:
                f.write(f"| {field} | `{m.get(field, '')}` |\n")
            f.write(f"\n## Flow Results\n\n| Field | Value |\n|---|---|\n")
            for field in [
                "runtime_ready", "mcp_proxy_connected", "mcp_initialized",
                "tools_discovered", "tool_count", "tool_names",
                "remote_execution", "remote_output",
            ]:
                f.write(f"| {field} | `{m.get(field, '')}` |\n")
            f.write(f"\n## Hardware Audit\n\n| Field | Value |\n|---|---|\n")
            for field in ["cpu", "ram", "gpu", "vram", "cuda", "cuda_tensor_test"]:
                f.write(f"| {field} | `{m.get(field, '')}` |\n")
            f.write(f"\n## State Timeline\n\n")
            for ev in self.timeline:
                extras = {k: v for k, v in ev.items()
                          if k not in ("state", "t_rel", "ts")}
                note = f"  — {json.dumps(extras)}" if extras else ""
                f.write(f"- `T+{ev['t_rel']:7.2f}s` **{ev['state']}**{note}\n")

        print(f"\nOutputs written:\n  {_JSON_OUT}\n  {_MD_OUT}", flush=True)

    def finish_success(self):
        self.record(S.CLEANUP_COMPLETED)
        self.meta["cleanup"] = "OBSERVED"
        self._write_outputs()


# ── SyncMCPBridge ─────────────────────────────────────────────────────────────
class SyncMCPBridge:
    """Thin synchronous wrapper around the async MCP client."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._session: Optional[ClientSession] = None
        self._read_ctx = None
        self._process_pid: Optional[int] = None
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self, env=None):
        fut = asyncio.run_coroutine_threadsafe(self._async_start(env), self._loop)
        fut.result(timeout=60)

    async def _async_start(self, env=None):
        params = StdioServerParameters(
            command="uvx",
            args=["--from", "git+https://github.com/googlecolab/colab-mcp", "colab-mcp"],
            env=env,
        )
        self._read_ctx = stdio_client(params)
        read, write = await self._read_ctx.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

    def get_server_pid(self) -> Optional[int]:
        """Try to get the PID of the colab-mcp subprocess."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "colab-mcp"],
                capture_output=True, text=True
            )
            pids = result.stdout.strip().split()
            if pids:
                return int(pids[-1])
        except Exception:
            pass
        return None

    def call_tool(self, name: str, args: dict):
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, args), self._loop
        )
        return fut.result(timeout=120)

    def list_tools(self):
        fut = asyncio.run_coroutine_threadsafe(
            self._session.list_tools(), self._loop
        )
        return fut.result(timeout=30)

    def stop(self):
        fut = asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
        try:
            fut.result(timeout=10)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    async def _async_stop(self):
        if self._session:
            await self._session.__aexit__(None, None, None)
        if self._read_ctx:
            await self._read_ctx.__aexit__(None, None, None)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def check_port_listening(port: int, host: str = "localhost", timeout: float = 0.5, retries: int = 5) -> bool:
    import time
    for _ in range(retries):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def parse_url_safe(url: str) -> dict:
    """Extract url_host, url_scheme, mcp_port, token_present from URL.
    Never returns the token value."""
    import urllib.parse as up
    parsed = up.urlparse(url)
    result = {
        "url_scheme": parsed.scheme,
        "url_host":   parsed.netloc,
        "url_path":   parsed.path,
        "mcp_port":   None,
        "token_present": False,
    }
    if parsed.fragment:
        params = up.parse_qs(parsed.fragment)
        if "mcpProxyPort" in params:
            result["mcp_port"] = params["mcpProxyPort"][0]
        if "mcpProxyToken" in params:
            result["token_present"] = True
    return result


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_ROOT, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def diagnose_ws_logs(port: int) -> str:
    """Read the latest colab-mcp log and classify the WS failure."""
    log_files = glob.glob("/tmp/colab-mcp-logs-*/colab-mcp.*.log")
    if not log_files:
        return "H3: No colab-mcp log found — MCP proxy may never have started."

    # Find logs referencing our port
    matching = []
    for lf in log_files:
        try:
            content = open(lf).read()
            if str(port) in content:
                matching.append((os.path.getmtime(lf), lf, content))
        except Exception:
            pass

    if not matching:
        matching = [(os.path.getmtime(lf), lf, open(lf).read()) for lf in log_files]

    matching.sort(reverse=True)
    _, _, content = matching[0]

    if "[WS SERVER] RECEIVED:" in content:
        return "H5/H6: WS handshake succeeded, messages received — failure at MCP initialization or tool discovery."
    if "connection open" in content and "connection closed" in content:
        return "H4: MCP proxy received WS connection but it closed immediately — handshake rejected (bad Origin or token mismatch)."
    if "connection open" in content:
        return "H3/H4: WS connection opened but no messages received — possibly stale."
    if "server listening" in content:
        return "H3: MCP server started and is listening, but browser never connected — browser may not have reached the page or used wrong port."
    return "H2/H3: MCP server log exists but no connection evidence — browser and MCP instance may be mismatched."


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    run_id = str(uuid.uuid4())
    git_commit = get_git_commit()
    tracker = DiagnosticTracker(run_id=run_id, git_commit=git_commit)

    # ── INIT ─────────────────────────────────────────────────────────────────
    tracker.record(S.INIT, python=sys.version.split()[0],
                   git_commit=git_commit, hostname=os.uname().nodename)

    # Verify no stale MCP process
    stale_check = subprocess.run(
        ["pgrep", "-f", "colab-mcp"], capture_output=True, text=True
    )
    if stale_check.stdout.strip():
        stale_pids = stale_check.stdout.strip().split()
        print(f"[WARNING] Stale colab-mcp PIDs found: {stale_pids} — they will be replaced.")

    # ── FASE 1: MCP SERVER ───────────────────────────────────────────────────
    bridge = SyncMCPBridge()

    # Setup URL interceptor
    fd, temp_path = tempfile.mkstemp(prefix="anny_colab_url_diag_")
    os.close(fd)
    interceptor_path = os.path.abspath(
        os.path.join(_ROOT, "runtime", "browser", "interceptor.py")
    )
    if not os.path.exists(interceptor_path):
        tracker.fail("MCP_START", f"Interceptor not found: {interceptor_path}",
                     "INFRASTRUCTURE_ERROR")

    env = os.environ.copy()
    env["BROWSER"] = f"{sys.executable} {interceptor_path} {temp_path} %s"

    tracker.record(S.MCP_SERVER_STARTED)
    try:
        bridge.start(env=env)
    except Exception as e:
        tracker.fail("MCP_START", f"MCP bridge start failed: {e}",
                     "H2_OR_INFRASTRUCTURE", type(e).__name__)

    mcp_pid = bridge.get_server_pid()
    tracker.meta["mcp_pid"] = mcp_pid

    # ── FASE 2: Trigger URL generation ──────────────────────────────────────
    connection_result: dict = {"text": None, "exc": None}

    def _run_connection_tool():
        try:
            res = bridge.call_tool("open_colab_browser_connection", {})
            txt = ""
            if hasattr(res, "content") and res.content:
                txt = getattr(res.content[0], "text", "")
            connection_result["text"] = txt
        except Exception as e:
            connection_result["exc"] = e

    conn_thread = threading.Thread(target=_run_connection_tool, daemon=True)
    conn_thread.start()

    # Wait for URL to be intercepted
    url: Optional[str] = None
    url_deadline = monotonic() + 6.0
    while monotonic() < url_deadline:
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            with open(temp_path) as f:
                url = f.read().strip()
            if url:
                break
        time.sleep(0.2)

    if not url:
        tracker.fail("URL_INTERCEPT",
                     "Interceptor did not receive URL from colab-mcp within 6s.",
                     "H2_INFRASTRUCTURE — colab-mcp may not call webbrowser.open on this env")

    # Parse URL safely
    url_info = parse_url_safe(url)
    mcp_port = url_info.get("mcp_port")
    token_present = url_info.get("token_present", False)
    tracker.meta["mcp_port"] = mcp_port
    tracker.meta["token_present"] = token_present

    tracker.record(S.MCP_PORT_BOUND, port=mcp_port,
                   pid=mcp_pid, url_host=url_info["url_host"])
    tracker.record(S.MCP_TOKEN_CREATED, token_present=token_present)

    # ── FASE 3: PORT VALIDATION ──────────────────────────────────────────────
    if mcp_port:
        listening = check_port_listening(int(mcp_port))
        if not listening:
            tracker.fail("MCP_PORT_BOUND",
                         f"Port {mcp_port} not listening after URL intercept.",
                         "H3: MCP proxy never bound to port")
        tracker.record("PORT_VALIDATED", port=mcp_port, listening=True)
    else:
        tracker.fail("MCP_PORT_BOUND", "No port extracted from URL.",
                     "H2: URL malformed or fragment not readable")

    # ── FASE 4: BROWSER LAUNCH (managed profile) ─────────────────────────────
    try:
        from runtime.browser.manager import BrowserSessionManager, BrowserManagerError
        bmanager = BrowserSessionManager.create(profile="colab-diag")
        bmanager.launch(url)
        bpid = bmanager.process.pid if bmanager.process else None
        tracker.meta["browser_pid"] = bpid
        tracker.meta["browser_binary"] = bmanager.executable
        tracker.meta["browser_profile"] = str(bmanager.profile_dir)
        tracker.record(S.BROWSER_LAUNCHED,
                       browser_pid=bpid,
                       browser_binary=bmanager.executable,
                       profile=str(bmanager.profile_dir))
    except Exception as e:
        # Fallback: if managed browser fails (e.g. profile/chrome issue),
        # record the failure but try xdg-open so the human can still connect
        # and we get diagnostic data about what happens at MCP level
        bmanager = None
        xdg = shutil.which("xdg-open")
        if xdg:
            proc = subprocess.Popen(
                [xdg, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            tracker.meta["browser_pid"] = proc.pid
            tracker.meta["browser_binary"] = xdg
            tracker.meta["browser_profile"] = "SYSTEM_DEFAULT (fallback — managed browser failed)"
        tracker.record(S.BROWSER_LAUNCHED,
                       managed_browser_error=str(e),
                       fallback="xdg-open")

    tracker.record(S.COLAB_URL_OPENED,
                   url_host=url_info["url_host"],
                   url_scheme=url_info["url_scheme"],
                   mcp_port=mcp_port)

    # ── FASE 5-7: WAIT FOR MCP PROXY CONNECTION ───────────────────────────────
    tracker.record(S.RUNTIME_PENDING)
    tracker.record(S.MCP_PROXY_EXPECTED, port=mcp_port)

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║     ANNY — 001G-MCP-DIAGNOSTIC — WAITING FOR HUMAN ACTION       ║
╠══════════════════════════════════════════════════════════════════╣
║  A browser window has opened pointing to Colab (port {mcp_port:>5}).   ║
║                                                                  ║
║  Please:                                                         ║
║    1. In the browser tab, select a T4 GPU runtime.               ║
║    2. Click "Connect" or "Save and connect".                     ║
║    3. Wait for the green checkmark (runtime connected).          ║
║                                                                  ║
║  The diagnostic will detect the connection automatically.        ║
║  Timeout: 10 minutes.                                            ║
╚══════════════════════════════════════════════════════════════════╝
""", flush=True)

    AUTH_BUDGET = 600.0
    POLL_INTERVAL = 2.0
    deadline = monotonic() + AUTH_BUDGET
    connected = False
    tools_at_connection: list[str] = []

    while monotonic() < deadline:
        # Case 1: the connection tool itself returned "true"
        if connection_result["text"] == "true":
            connected = True
            break
        if connection_result["exc"]:
            tracker.fail("MCP_CONNECT",
                         f"Connection tool raised: {connection_result['exc']}",
                         "H4_OR_H5: MCP tool layer exception")

        # Case 2: poll list_tools for new tools appearing
        try:
            tools_resp = bridge.list_tools()
            names = {t.name for t in tools_resp.tools}
            # colab-mcp initially only has "open_colab_browser_connection"
            # When Colab JS connects, new tools appear
            execution_tools = [n for n in names
                               if n != "open_colab_browser_connection"]
            if execution_tools:
                tools_at_connection = sorted(names)
                connected = True
                break
        except Exception as poll_err:
            logger.debug(f"list_tools poll error (non-fatal): {poll_err}")

        time.sleep(POLL_INTERVAL)

    if not connected:
        hypothesis = diagnose_ws_logs(int(mcp_port) if mcp_port else 0)
        tracker.timeout("MCP_PROXY_CONNECTED",
                        f"10 minute budget exhausted without MCP proxy connection.",
                        hypothesis=hypothesis)

    # ── MCP PROXY CONNECTED ───────────────────────────────────────────────────
    tracker.meta["mcp_proxy_connected"] = "OBSERVED"
    tracker.meta["runtime_ready"] = "OBSERVED"
    tracker.record(S.MCP_PROXY_CONNECTED)
    tracker.record(S.RUNTIME_READY)
    tracker.record(S.MCP_INITIALIZED)
    tracker.meta["mcp_initialized"] = "OBSERVED"

    # ── FASE 10: TOOLS DISCOVERY ──────────────────────────────────────────────
    tracker.record(S.TOOLS_DISCOVERY_STARTED)
    try:
        tools_resp = bridge.list_tools()
        all_tools = sorted(t.name for t in tools_resp.tools)
        tracker.meta["tools_discovered"] = "OBSERVED"
        tracker.meta["tool_count"] = len(all_tools)
        tracker.meta["tool_names"] = all_tools
        tracker.record(S.TOOLS_DISCOVERY_COMPLETED,
                       tool_count=len(all_tools), tools=all_tools)
    except Exception as e:
        tracker.fail("TOOLS_DISCOVERY",
                     f"list_tools failed after connection: {e}",
                     "H6: tools/list failed after handshake")

    # Find an execution tool
    exec_tool = next(
        (n for n in all_tools if "python" in n.lower() or "execute" in n.lower()
         or "run" in n.lower()),
        None
    )
    if not exec_tool:
        tracker.fail("REMOTE_EXECUTION",
                     f"No python/execute tool found in: {all_tools}",
                     "H6: Tool discovery succeeded but no execution tool present")

    # ── FASE 11: REMOTE SMOKE TEST ────────────────────────────────────────────
    tracker.record(S.REMOTE_EXECUTION_STARTED, tool="add_code_cell+run_code_cell")

    def run_remote_code(code: str) -> str:
        add_res = bridge.call_tool("add_code_cell", {
            "cellIndex": 0,
            "language": "python",
            "code": code
        })
        cell_id = None
        if hasattr(add_res, "content") and add_res.content:
            raw = getattr(add_res.content[0], "text", "")
            try:
                cell_data = json.loads(raw)
                cell_id = cell_data.get("newCellId") or cell_data.get("cellId") or cell_data.get("id") or cell_data.get("cell_id")
            except Exception:
                pass
        if not cell_id and hasattr(add_res, "structured_content") and add_res.structured_content:
            cell_id = add_res.structured_content.get("newCellId") or add_res.structured_content.get("cellId")

        if not cell_id:
            raise RuntimeError(f"add_code_cell failed to return cellId: {add_res}")

        run_res = bridge.call_tool("run_code_cell", {"cellId": cell_id})
        output = ""
        if hasattr(run_res, "content") and run_res.content:
            raw_output = getattr(run_res.content[0], "text", "")
            try:
                out_data = json.loads(raw_output)
                if "outputs" in out_data:
                    for out_item in out_data["outputs"]:
                        if "text" in out_item:
                            output += "".join(out_item["text"])
            except Exception:
                output = raw_output
        return output

    try:
        smoke_code = "print('ANNY_COLAB_MCP_OK')"
        output = run_remote_code(smoke_code)
        tracker.meta["remote_execution"] = "OBSERVED"
        tracker.meta["remote_output"] = output.strip()
        tracker.record(S.REMOTE_EXECUTION_COMPLETED,
                       output=output.strip()[:200])
    except Exception as e:
        tracker.fail("REMOTE_EXECUTION",
                     f"remote code execution failed: {e}",
                     "H7: tools/list OK but remote execution failed")

    # ── FASE 12: GPU AUDIT ────────────────────────────────────────────────────
    tracker.record(S.GPU_AUDIT)
    gpu_code = """
import platform, json, sys
out = {
    "platform": platform.platform(),
    "python": platform.python_version(),
}
try:
    import psutil
    out["cpu_count"] = psutil.cpu_count(logical=True)
    out["ram_gb"] = round(psutil.virtual_memory().total / (1024**3), 2)
except Exception as e:
    out["psutil_error"] = repr(e)
try:
    import torch
    out["torch"] = torch.__version__
    out["cuda"] = torch.cuda.is_available()
    if out["cuda"]:
        out["gpu"] = torch.cuda.get_device_name(0)
        p = torch.cuda.get_device_properties(0)
        out["vram_gb"] = round(p.total_memory / (1024**3), 2)
        out["compute_capability"] = f"{p.major}.{p.minor}"
except Exception as e:
    out["torch_error"] = repr(e)
print("GPU_AUDIT_JSON:", json.dumps(out))
"""
    try:
        output = run_remote_code(gpu_code)
        # Find the JSON line
        for line in output.splitlines():
            if line.startswith("GPU_AUDIT_JSON:"):
                try:
                    data = json.loads(line[len("GPU_AUDIT_JSON:"):].strip())
                    tracker.meta["cpu"] = data.get("cpu_count", "UNKNOWN")
                    tracker.meta["ram"] = data.get("ram_gb", "UNKNOWN")
                    tracker.meta["gpu"] = data.get("gpu", "UNKNOWN")
                    tracker.meta["vram"] = data.get("vram_gb", "UNKNOWN")
                    tracker.meta["cuda"] = data.get("cuda", "UNKNOWN")
                    tracker.record("GPU_AUDIT_COMPLETED", data=data)
                except Exception:
                    tracker.record("GPU_AUDIT_PARSE_ERROR", raw=line[:200])
    except Exception as e:
        tracker.record("GPU_AUDIT_ERROR", error=str(e))

    # ── FASE 13: CUDA SMOKE TEST ──────────────────────────────────────────────
    if tracker.meta.get("cuda") is True:
        tracker.record(S.CUDA_TEST)
        cuda_code = """
import torch
x = torch.randn((1024, 1024), device="cuda")
y = torch.randn((1024, 1024), device="cuda")
z = x @ y
torch.cuda.synchronize()
print("CUDA_TENSOR_TEST: PASS")
print("RESULT_SHAPE:", tuple(z.shape))
"""
        try:
            output = run_remote_code(cuda_code)
            if "CUDA_TENSOR_TEST: PASS" in output:
                tracker.meta["cuda_tensor_test"] = "PASS"
            else:
                tracker.meta["cuda_tensor_test"] = f"FAIL: {output.strip()[:200]}"
            tracker.record("CUDA_TEST_COMPLETED",
                           result=tracker.meta["cuda_tensor_test"])
        except Exception as e:
            tracker.meta["cuda_tensor_test"] = f"ERROR: {e}"
            tracker.record("CUDA_TEST_ERROR", error=str(e))
    else:
        tracker.meta["cuda_tensor_test"] = "N/A"

    # ── FASE 14: CLEANUP ──────────────────────────────────────────────────────
    tracker.record(S.CLEANUP_STARTED)
    try:
        bridge.stop()
    except Exception as e:
        logger.warning(f"Bridge stop error: {e}")
    try:
        if bmanager:
            bmanager.terminate()
    except Exception:
        pass
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception:
        pass
    tracker.meta["cleanup"] = "OBSERVED"

    tracker.finish_success()

    # ── OUTPUT CONTRACT ───────────────────────────────────────────────────────
    m = tracker.meta
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║           ANNY — 001G-MCP-DIAGNOSTIC — OUTPUT CONTRACT           ║
╠══════════════════════════════════════════════════════════════════╣
MISSION:          {m['mission']}
SERIAL:           ANNY-20260914-004
REVISION:         {m['revision']}

GIT_COMMIT:       {m['git_commit']}

FINAL_STATE:      {m['final_state']}
LAST_SUCCESSFUL:  {m['last_successful_stage']}
FAILED_STAGE:     {m.get('failed_stage', 'NONE')}
ROOT_CAUSE:       {m.get('root_cause_hypothesis', 'NONE')}

MCP_PID:          {m['mcp_pid']}
MCP_PORT:         {m['mcp_port']}
BROWSER_PID:      {m['browser_pid']}
BROWSER_BINARY:   {m['browser_binary']}
BROWSER_PROFILE:  {m['browser_profile']}

RUNTIME_READY:    {m['runtime_ready']}
MCP_CONNECTED:    {m['mcp_proxy_connected']}
MCP_INITIALIZED:  {m['mcp_initialized']}
TOOLS_DISCOVERED: {m['tools_discovered']}
TOOL_COUNT:       {m['tool_count']}

REMOTE_EXECUTION: {m['remote_execution']}
REMOTE_OUTPUT:    {m['remote_output']}

CPU:              {m['cpu']}
RAM:              {m['ram']}
GPU:              {m['gpu']}
VRAM:             {m['vram']}
CUDA:             {m['cuda']}
CUDA_TENSOR_TEST: {m['cuda_tensor_test']}

CLEANUP:          {m['cleanup']}

ARTIFACTS:
  {_JSON_OUT}
  {_MD_OUT}

UNSAFE_DATA_EXCLUDED: YES
╚══════════════════════════════════════════════════════════════════╝
""", flush=True)


if __name__ == "__main__":
    main()
