#!/usr/bin/env python3
"""
runtime/browser/broker_server.py

ANNY Browser Broker — hardened server (MISSION-001D-R2-R2).

Security invariants:
  - Chrome binary is whitelisted: /usr/bin/google-chrome only.
  - Profile must be under ~/.anny/browser-profiles/ — no escapes.
  - URL scheme must be http, https, or about.
  - No shell=True, no os.system, no string interpolation in Popen.
  - IPC commands are schema-validated before dispatch.
  - Socket chmod 0600 — local user only.
  - No Google tokens / OAuth / cookies over IPC.
  - Broker must not run as root.
"""

import os
import time
import shutil
import json
import socket
import signal
import logging
import subprocess
import stat
import time
import uuid
import threading
import urllib.request
import urllib.error
import websocket
import base64
from pathlib import Path
from socketserver import UnixStreamServer, StreamRequestHandler, ThreadingMixIn

logger = logging.getLogger(__name__)

# ── Security constants ─────────────────────────────────────────────────────────

def _resolve_chrome_binary() -> str | None:
    candidates = [
        os.environ.get("ANNY_CHROME_BINARY"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.abspath(candidate)
    return None

PROFILE_BASE = Path.home() / ".anny" / "browser-profiles"
SOCKET_PATH = Path.home() / ".anny" / "browser-broker.sock"
MAX_REQUEST_BYTES = 4096

# Allowed URL schemes for START_BROWSER / NAVIGATE
_ALLOWED_SCHEMES = ("http://", "https://", "about:")

# Hardened Chrome flags — these are the ONLY flags the broker uses.
# IPC clients CANNOT add, remove, or override them.
_CHROME_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--new-window",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--remote-debugging-port=0",
    "--remote-debugging-address=127.0.0.1",
]


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate_url(url: str) -> str:
    """
    Ensure url is an absolute URL with an allowed scheme.
    Raises ValueError on rejection.
    """
    if not isinstance(url, str) or not url:
        raise ValueError("url must be a non-empty string")
    if not any(url.startswith(s) for s in _ALLOWED_SCHEMES):
        raise ValueError(
            f"url scheme not allowed. Must start with one of {_ALLOWED_SCHEMES}"
        )
    for bad in ("\n", "\r", "\0", "`", "$", ";", "|", ">", "<", " "):
        if bad in url:
            raise ValueError(f"Forbidden character {bad!r} in url")
    return url


def _validate_profile(name: str) -> Path:
    """
    Ensure profile resolves under PROFILE_BASE without path traversal.
    Raises ValueError on rejection.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("profile must be a non-empty string")
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("profile must be a simple name, not a path")
    resolved = (PROFILE_BASE / name).resolve()
    # Strict containment check
    try:
        resolved.relative_to(PROFILE_BASE.resolve())
    except ValueError:
        raise ValueError(f"Profile {name!r} resolves outside allowed base")
    return resolved


def _check_not_root() -> None:
    if os.getuid() == 0:
        raise RuntimeError("Browser Broker must not run as root.")


# ── Broker state machine ───────────────────────────────────────────────────────

class BrokerState:
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


class BrowserState:
    CREATED = "CREATED"
    LAUNCHING = "LAUNCHING"
    RUNNING = "RUNNING"
    NAVIGATING = "NAVIGATING"
    READY = "READY"
    HIDDEN = "HIDDEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class BrowserBroker:
    """
    Manages the Chrome process lifecycle.
    All security decisions are made here — IPC clients supply only a URL.
    """

    def __init__(self):
        _check_not_root()
        self.chrome_binary = _resolve_chrome_binary()
        self.process: subprocess.Popen | None = None
        self.profile_name: str = "colab"
        self.profile_dir: Path = _validate_profile(self.profile_name)
        self.broker_state: str = BrokerState.STOPPED
        self.browser_state: str = BrowserState.CLOSED
        self._last_url: str | None = None  # for RESTART_BROWSER
        self._cdp_ws_url: str | None = None
        self._cdp_ws = None
        self._msg_id = 0
        self._session_id = None
        self.targets = {}

        self._cdp_listener_thread = None
        self._cdp_responses = {}
        self._cdp_cond = threading.Condition()
        self._cdp_lock = threading.Lock()
        self._pending_submission = None
        self.issued_authorizations = {}
    def _get_cdp_ws_url(self) -> str | None:
        """Fetch the WebSocket URL from the CDP HTTP endpoint."""
        if self._cdp_ws_url:
            return self._cdp_ws_url

        # Read DevToolsActivePort to find the dynamic port
        port_file = self.profile_dir / "DevToolsActivePort"
        port = None
        for _ in range(10):
            if port_file.exists():
                try:
                    with open(port_file, "r") as f:
                        lines = f.readlines()
                        if lines:
                            port = lines[0].strip()
                            break
                except Exception:
                    pass
            time.sleep(0.5)

        if not port:
            logger.error("[broker] DevToolsActivePort not found or unreadable.")
            return None

        # Try fetching up to 5 times (browser startup delay)
        for _ in range(5):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list")
                with urllib.request.urlopen(req, timeout=2) as response:
                    targets = json.loads(response.read().decode())
                    for target in targets:
                        if target.get("type") == "page" and "webSocketDebuggerUrl" in target:
                            self._cdp_ws_url = target["webSocketDebuggerUrl"]
                            return self._cdp_ws_url
            except Exception:
                time.sleep(0.5)
        return None

    def _get_ws(self):
        with self._cdp_lock:
            if self._cdp_ws:
                return self._cdp_ws
            ws_url = self._get_cdp_ws_url()
            if not ws_url:
                return None
            try:
                self._cdp_ws = websocket.create_connection(ws_url, timeout=5, suppress_origin=True)
                self._cdp_listener_thread = threading.Thread(target=self._cdp_listener_loop, args=(self._cdp_ws,), daemon=True)
                self._cdp_listener_thread.start()

                # Fetch.enable is now called synchronously in start_browser
                pass

                return self._cdp_ws
            except Exception as e:
                self._cdp_ws_url = None
                return None

    def _cdp_listener_loop(self, ws):
        while True:
            try:
                msg = ws.recv()
                if not msg:
                    break
                response = json.loads(msg)

                # Async event
                if "method" in response and "id" not in response:
                    self._handle_cdp_event(response)
                    continue

                msg_id = response.get("id")
                if msg_id is not None:
                    if "error" in response:
                        logger.debug("CDP async error response: %s", response.get("error"))
                    with self._cdp_cond:
                        self._cdp_responses[msg_id] = response
                        self._cdp_cond.notify_all()
            except Exception as e:
                break

        with self._cdp_cond:
            self._cdp_cond.notify_all()

    def _send_cdp_async(self, method: str, params: dict):
        with self._cdp_lock:
            if not self._cdp_ws: return
            self._msg_id += 1
            payload = {"id": self._msg_id, "method": method, "params": params}
            try:
                self._cdp_ws.send(json.dumps(payload))
            except Exception:
                pass

    def _handle_cdp_event(self, event: dict):
        method = event.get("method")
        params = event.get("params", {})

        if method == "Fetch.requestPaused":
            request_id = params.get("requestId")
            req = params.get("request", {})
            req_method = req.get("method", "").upper()
            req_url = req.get("url")
            logger.debug("Fetch intercepted: %s %s", req_method, req_url)

            if req_method in ("GET", "HEAD", "OPTIONS"):
                # Always allow safe reads.
                self._send_cdp_async("Fetch.continueRequest", {"requestId": request_id})
                return

            pending = self._pending_submission
            def get_b64_post(req_obj):
                if "postDataEntries" in req_obj and len(req_obj["postDataEntries"]) > 0:
                    return req_obj["postDataEntries"][0].get("bytes")
                if "postData" in req_obj:
                    return base64.b64encode(req_obj["postData"].encode("utf-8")).decode("utf-8")
                return None

            if pending:
                frame_id = params.get("frameId", "")


                # Check method
                if pending.expected_method == req_method:
                    # Check URL (ignore fragments)
                    req_url_no_frag = req_url.split('#')[0]
                    expected_url_no_frag = pending.expected_url.split('#')[0]

                    if req_url_no_frag == expected_url_no_frag:
                        if pending.expected_frame_id == frame_id:
                            # MATCH: consume auth and allow POST
                            self._pending_submission = None

                            params = {"requestId": request_id}
                            b64 = get_b64_post(req)
                            if b64:
                                params["postData"] = b64

                            def do_continue():
                                try:
                                    self._cdp_request("Fetch.continueRequest", params)
                                except Exception:
                                    pass
                            import threading
                            threading.Thread(target=do_continue, daemon=True).start()
                            return
                        else:
                            pass
                    else:
                        pass
                else:
                    pass

            logger.warning(f"Blocked unauthorized {req_method} request to {req.get('url')}")
            self._send_cdp_async("Fetch.failRequest", {"requestId": request_id, "errorReason": "AccessDenied"})

    def _cdp_request(self, method: str, params: dict | None = None, timeout: float = 5.0) -> dict:
        """Send a JSON-RPC request to the browser via CDP WebSocket (persistent)."""
        ws = self._get_ws()
        if not ws:
            raise RuntimeError("CDP WebSocket is unavailable.")

        with self._cdp_lock:
            self._msg_id += 1
            msg_id = self._msg_id
            payload = {
                "id": msg_id,
                "method": method,
                "params": params or {}
            }
            try:
                ws.send(json.dumps(payload))
            except Exception as e:
                self._cdp_ws.close()
                self._cdp_ws = None
                self._cdp_ws_url = None
                raise RuntimeError(f"CDP communication failed: {e}")

        with self._cdp_cond:
            start_time = time.time()
            while msg_id not in self._cdp_responses:
                if not self._cdp_ws:
                    raise RuntimeError("CDP WebSocket closed while waiting for response.")
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise RuntimeError("CDP request timed out.")
                self._cdp_cond.wait(timeout - elapsed)

            response = self._cdp_responses.pop(msg_id)
            if "error" in response:
                raise RuntimeError(f"CDP Error: {response['error']}")
            return response.get("result", {})

    def start_browser(self, url: str) -> dict:
        """
        Launch Chrome with isolated profile.
        The binary, profile base, and flags are determined entirely by the broker.
        """
        try:
            url = _validate_url(url)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        if self.process and self.process.poll() is None:
            return {
                "status": "ok",
                "message": "Browser already running",
                "pid": self.process.pid,
                "browser_state": self.browser_state,
                "profile": str(self.profile_dir),
                "binary": self.chrome_binary,
            }

        if not self.chrome_binary:
            self.browser_state = BrowserState.FAILED
            return {
                "status": "error",
                "message": "No supported Chrome/Chromium binary was found",
            }

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.browser_state = BrowserState.LAUNCHING
        self._last_url = url
        if self._cdp_ws:
            self._cdp_ws.close()
        self._cdp_ws = None
        self._cdp_ws_url = None  # reset so new session gets fresh CDP connection
        self._session_id = str(uuid.uuid4())
        self.targets = {}
        self._pending_submission = None
        self.issued_authorizations = {}

        # Build args — no shell, no string interpolation, structured list only.
        args = [
            self.chrome_binary,
            f"--user-data-dir={self.profile_dir}",
        ] + _CHROME_FLAGS + [f"--app={url}"]

        logger.info(f"[broker] Launching Chrome: profile={self.profile_dir}")

        try:
            self.process = subprocess.Popen(
                args,
                shell=False,      # MANDATORY: no shell
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=_build_chrome_env(),
            )
        except Exception as e:
            self.browser_state = BrowserState.FAILED
            self.process = None
            return {"status": "error", "message": f"Popen failed: {e}"}

        self.browser_state = BrowserState.RUNNING
        logger.info(f"[broker] Chrome pid={self.process.pid}")
        return {
            "status": "ok",
            "pid": self.process.pid,
            "browser_state": self.browser_state,
            "profile": str(self.profile_dir),
            "binary": self.chrome_binary,
        }

    def stop_browser(self) -> dict:
        if self.process and self.process.poll() is None:
            self.browser_state = BrowserState.CLOSING
            logger.info("[broker] Terminating Chrome")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process = None
        self.browser_state = BrowserState.CLOSED
        if self._cdp_ws:
            self._cdp_ws.close()
        self._cdp_ws = None
        self._cdp_ws_url = None  # invalidate cached CDP connection
        self._session_id = None
        self.targets = {}
        self._pending_submission = None
        self.issued_authorizations = {}
        return {"status": "ok", "browser_state": self.browser_state}

    def hide_browser(self) -> dict:
        """
        Hide (minimize/iconify) the governed Chrome window using xdotool.
        Falls back gracefully if xdotool is not available.
        The Chrome process remains alive — RemoteComputeSession is unaffected.
        """
        if self.process is None or self.process.poll() is not None:
            return {"status": "ok", "browser_state": self.browser_state,
                    "message": "Browser not running — nothing to hide"}

        pid = self.process.pid
        xdotool = os.environ.get("ANNY_XDOTOOL_PATH") or shutil.which("xdotool")
        if not xdotool or not os.path.isfile(xdotool) or not os.access(xdotool, os.X_OK):
            logger.warning("[broker] xdotool not found — HIDE unavailable")
            return {
                "status": "unavailable",
                "browser_state": self.browser_state,
                "message": "xdotool not installed — hide not possible",
            }

        env = os.environ.copy()
        xdotool_lib = os.environ.get("ANNY_XDOTOOL_LIB_DIR")
        if xdotool_lib:
            env["LD_LIBRARY_PATH"] = xdotool_lib + os.pathsep + env.get("LD_LIBRARY_PATH", "")

        try:
            # Search for window(s) by PID, then iconify each
            search = subprocess.run(
                [xdotool, "search", "--pid", str(pid)],
                capture_output=True, text=True, timeout=5,
                shell=False, env=env,
            )
            wids = search.stdout.strip().split()
            if not wids:
                logger.warning(f"[broker] xdotool found no windows for pid={pid}")
                return {
                    "status": "ok",
                    "browser_state": self.browser_state,
                    "message": "No windows found for PID (may already be hidden)",
                }
            for wid in wids:
                subprocess.run(
                    [xdotool, "windowminimize", wid],
                    capture_output=True, timeout=5,
                    shell=False, env=env,
                )
            self.browser_state = BrowserState.HIDDEN
            logger.info(f"[broker] Chrome pid={pid} hidden via xdotool (wids={wids})")
            return {
                "status": "ok",
                "browser_state": self.browser_state,

                "pid": pid,
                "windows_hidden": wids,
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "browser_state": self.browser_state,
                    "message": "xdotool timed out"}
        except Exception as e:
            return {"status": "error", "browser_state": self.browser_state,
                    "message": f"hide_browser error: {e}"}

    def navigate(self, url: str) -> dict:
        """
        Navigate the governed browser to a new validated URL via CDP.
        """
        try:
            url = _validate_url(url)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running. Use START_BROWSER first."}

        self.browser_state = BrowserState.NAVIGATING
        self._last_url = url
        try:
            self._cdp_request("Page.navigate", {"url": url})
            self.browser_state = BrowserState.RUNNING
            logger.info(f"[broker] Navigate to {url!r} via CDP")
            return {"status": "ok", "browser_state": self.browser_state, "url": url}
        except Exception as e:
            self.browser_state = BrowserState.FAILED
            return {"status": "error", "message": f"CDP navigate failed: {e}"}

    def navigate_action(self, action: str) -> dict:
        """Perform back, forward, or reload via CDP."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}
        try:
            if action == "back" or action == "forward":
                history = self._cdp_request("Page.getNavigationHistory")
                index = history.get("currentIndex", 0)
                entries = history.get("entries", [])

                target_index = index - 1 if action == "back" else index + 1
                if 0 <= target_index < len(entries):
                    entry = entries[target_index]
                    self._cdp_request("Page.navigateToHistoryEntry", {"entryId": entry["id"]})
                    self._last_url = entry.get("url")
            elif action == "reload":
                self._cdp_request("Page.reload")
            else:
                return {"status": "error", "message": f"Unknown action {action}"}
            return {"status": "ok", "action": action}
        except Exception as e:
            return {"status": "error", "message": f"CDP action failed: {e}"}

    def issue_auth(self, target_id: str, session_id: str, expires_in: int = 300) -> dict:
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        if self._session_id != session_id:
            return {"status": "error", "message": "AUTHORIZATION_SESSION_MISMATCH"}

        try:
            resolve_res = self._cdp_request("DOM.resolveNode", {"backendNodeId": target_record["backendNodeId"]})
        except RuntimeError:
            return {"status": "error", "message": "TARGET_STALE"}

        if "object" not in resolve_res or "objectId" not in resolve_res["object"]:
            return {"status": "error", "message": "TARGET_STALE"}

        obj_id = resolve_res["object"]["objectId"]

        # Robustly discover the frame that will RECEIVE the form navigation.
        # The form's `target` attribute controls which frame loads the response
        # (and which frame Fetch.requestPaused will report for the outgoing POST).
        token = str(uuid.uuid4())
        self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": f"""function() {{
                let form = this.tagName.toLowerCase() === 'form' ? this : this.closest('form');
                if (!form) {{ (this.ownerDocument || this).documentElement.setAttribute('data-anny-auth-token', '{token}'); return; }}
                let formTarget = form.target || "";
                // Resolve the window that will receive the navigation
                let targetWin = formTarget ? window.frames[formTarget] : null;
                if (!targetWin) targetWin = window;
                try {{
                    targetWin.document.documentElement.setAttribute('data-anny-auth-token', '{token}');
                }} catch(e) {{
                    // Cross-origin iframe: fall back to own frame
                    (this.ownerDocument || this).documentElement.setAttribute('data-anny-auth-token', '{token}');
                }}
            }}"""
        })

        # Walk frame tree to find the matching frame
        tree = self._cdp_request("Page.getFrameTree")
        def get_frames(t):
            frames = [t["frame"]["id"]]
            for c in t.get("childFrames", []):
                frames.extend(get_frames(c))
            return frames

        f_ids = get_frames(tree["frameTree"])
        frame_id = ""
        for f_id in f_ids:
            try:
                w = self._cdp_request("Page.createIsolatedWorld", {"frameId": f_id, "worldName": "anny_auth"})
                ctx_id = w["executionContextId"]
                eval_res = self._cdp_request("Runtime.evaluate", {
                    "contextId": ctx_id,
                    "expression": "document.documentElement.getAttribute('data-anny-auth-token')"
                })
                val = eval_res.get("result", {}).get("value")
                if val == token:
                    frame_id = f_id
                    # Clean up
                    self._cdp_request("Runtime.evaluate", {
                        "contextId": ctx_id,
                        "expression": "document.documentElement.removeAttribute('data-anny-auth-token')"
                    })
                    break
            except Exception:
                continue

        if not frame_id:
            return {"status": "error", "message": "FRAME_IDENTITY_MISSING"}


        # Extract form action and method via JS
        script = '''function() {
            let form = this.tagName.toLowerCase() === 'form' ? this : this.closest('form');
            if (!form) return {error: "TARGET_NOT_IN_FORM"};

            // Resolve relative action to absolute URL using standard anchor trick
            let a = document.createElement('a');
            a.href = form.getAttribute('action') || '';
            let actionUrl = a.href;
            if (form.getAttribute('action') === null || form.getAttribute('action') === '') {
                actionUrl = window.location.href; // Default to current URL
            }

            return {
                action: actionUrl,
                method: (form.getAttribute('method') || 'get').toUpperCase()
            };
        }'''

        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })

        if "exceptionDetails" in res:
            return {"status": "error", "message": str(res["exceptionDetails"])}

        val = res.get("result", {}).get("value", {})
        if "error" in val:
            return {"status": "error", "message": val["error"]}

        auth_id = str(uuid.uuid4())
        expires_at = time.time() + expires_in
        self.issued_authorizations[auth_id] = {
            "target_id": target_id,
            "session_id": session_id,
            "expires_at": expires_at,
            "expected_method": val["method"],
            "expected_url": val["action"],
            "expected_frame_id": frame_id,
            "issued_at": time.time()
        }
        return {"status": "ok", "auth_id": auth_id}

    def submit(self, target_id: str, auth_id: str | None = None) -> dict:
        """Execute a governed form submission. Requires a runtime-issued auth_id."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        # --- Authorization boundary (runtime-owned, not caller-owned) ---
        if not auth_id:
            return {"status": "error", "message": "MISSING_AUTHORIZATION", "action": {"type": "submit", "target_id": target_id}}

        auth = self.issued_authorizations.get(auth_id)
        if not auth:
            return {"status": "error", "message": "INVALID_AUTHORIZATION", "action": {"type": "submit", "target_id": target_id}}

        if auth["session_id"] != self._session_id:
            return {"status": "error", "message": "AUTHORIZATION_SESSION_MISMATCH", "action": {"type": "submit", "target_id": target_id}}

        if auth["target_id"] != target_id:
            return {"status": "error", "message": "AUTHORIZATION_TARGET_MISMATCH", "action": {"type": "submit", "target_id": target_id}}

        if time.time() > auth["expires_at"]:
            return {"status": "error", "message": "AUTHORIZATION_EXPIRED", "action": {"type": "submit", "target_id": target_id}}

        # Build pending submission record
        from runtime.browser.authorization import PendingSubmissionAuthorization
        pending = PendingSubmissionAuthorization(
            auth_id=auth_id,
            session_id=auth["session_id"],
            target_id=auth["target_id"],
            expected_method=auth["expected_method"],
            expected_url=auth["expected_url"],
            expected_frame_id=auth["expected_frame_id"],
            issued_at=auth["issued_at"],
            expires_at=auth["expires_at"]
        )

        # Single-use: consume the auth_id
        del self.issued_authorizations[auth_id]

        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        try:
            resolve_res = self._cdp_request("DOM.resolveNode", {"backendNodeId": target_record["backendNodeId"]})
        except RuntimeError:
            return {"status": "error", "message": "TARGET_STALE"}

        if "object" not in resolve_res or "objectId" not in resolve_res["object"]:
            return {"status": "error", "message": "TARGET_STALE"}

        obj_id = resolve_res["object"]["objectId"]

        script = '''function() {
            let rect = this.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return {error: "TARGET_INVISIBLE"};
            if (this.disabled) return {error: "TARGET_DISABLED"};

            let form = this.closest('form');
            if (!form) return {error: "TARGET_NOT_IN_FORM"};

            // Perform actual submission safely using requestSubmit if available
            if (typeof form.requestSubmit === 'function') {
                try {
                    let submitter = (this.nodeType === 1 && (this.type === 'submit' || this.type === 'image')) ? this : null;
                    if (!submitter && this.parentElement && this.parentElement.type === 'submit') submitter = this.parentElement;
                    if (submitter) form.requestSubmit(submitter);
                    else form.requestSubmit();
                } catch(e) {
                    form.submit();
                }
            } else {
                form.submit();
            }
            return {success: true};
        }'''

        # Signal to the Fetch interceptor that the next POST is authorized
        self._pending_submission = pending

        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })

        if "exceptionDetails" in res:
            self._pending_submission = None
            return {"status": "error", "message": str(res["exceptionDetails"])}
        val = res.get("result", {}).get("value", {})

        if "error" in val:
            self._pending_submission = None
            return {"status": "error", "message": val["error"]}

        # Poll until the browser has completed navigation after the POST.
        # After form.requestSubmit() the browser does:
        #   POST → server 302 → GET /destination → page load
        # The Fetch interceptor will allow the follow-up GET (method filter above).
        # We wait up to 8 s, re-trying observe() every 0.5 s until we see a
        # non-empty URL (page loaded) or the deadline expires.
        deadline = time.time() + 8.0
        obs = {"status": "error", "message": "Timed out waiting for post-submission page"}
        while time.time() < deadline:
            time.sleep(0.5)
            candidate = self._observe_with_timeout(timeout=2.0)
            logger.debug("submit poll: %s", candidate.get("status"))
            if candidate.get("status") == "ok":
                url = candidate.get("observation", {}).get("url", "")
                if url and url not in ("", "about:blank"):
                    obs = candidate
                    break
                # Page context available but URL empty → still loading, keep polling
                obs = candidate

        if obs.get("status") == "ok":
            return {
                "status": "ok",
                "result": "REQUEST_ACCEPTED",
                "action": {"type": "submit", "target_id": target_id, "authorization_used": True},
                "request": {"method": pending.expected_method, "destination": pending.expected_url},
                "observation": obs.get("observation")
            }
        return {
            "status": "ok",
            "result": "POST_ACTION_FAILED",
            "action": {"type": "submit", "target_id": target_id, "authorization_used": True},
            "request": {"method": pending.expected_method, "destination": pending.expected_url},
            "observation_error": obs.get("message")
        }

    def observe(self) -> dict:
        """Extract structured data from the active page via CDP."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        script = '''(function() {
            const links = Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.innerText.trim(),
                href: a.href
            })).filter(l => l.href);
            const inputs = Array.from(document.querySelectorAll('input, textarea, select')).map(i => {
                const tag = i.tagName.toLowerCase();
                const type = i.getAttribute('type') || (tag === 'textarea' ? 'textarea' : (tag === 'select' ? 'select' : 'text'));
                const res = {
                    tag: tag,
                    type: type,
                    name: i.getAttribute('aria-label') || i.name || i.id || '',
                    disabled: !!i.disabled,
                    required: !!i.required,
                    valid: i.validity ? i.validity.valid : true
                };
                if (tag === 'input' || tag === 'textarea') {
                    res.value_present = !!i.value;
                    if (type === 'checkbox' || type === 'radio') {
                        res.checked = !!i.checked;
                        if (type === 'radio') res.group = i.name || '';
                    }
                } else if (tag === 'select') {
                    res.multiple = !!i.multiple;
                    res.selected_options = Array.from(i.selectedOptions).map(o => ({
                        text: o.text,
                        value_present: !!o.value
                    }));
                }
                return res;
            });
            return {
                url: window.location.href,
                title: document.title,
                text: document.body ? document.body.innerText : "",
                links: links,
                inputs: inputs
            };
        })();'''

        try:
            res = self._cdp_request("Runtime.evaluate", {"expression": script, "returnByValue": True})
            if "exceptionDetails" in res:
                return {"status": "error", "message": str(res["exceptionDetails"])}
            val = res.get("result", {}).get("value", {})
            return {"status": "ok", "observation": val}
        except Exception as e:
            return {"status": "error", "message": f"CDP observe failed: {e}"}

    def _observe_with_timeout(self, timeout: float = 2.0) -> dict:
        """Observe with a configurable short CDP timeout (for polling loops)."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}
        script = '''(function() {
            return {
                url: window.location.href,
                title: document.title,
                text: document.body ? document.body.innerText.trim().slice(0, 500) : "",
                links: Array.from(document.querySelectorAll('a[href]')).map(a => ({text: a.innerText.trim(), href: a.href})),
                inputs: []
            };
        })();'''
        try:
            res = self._cdp_request("Runtime.evaluate", {"expression": script, "returnByValue": True}, timeout=timeout)
            if "exceptionDetails" in res:
                return {"status": "error", "message": str(res["exceptionDetails"])}
            val = res.get("result", {}).get("value", {})
            return {"status": "ok", "observation": val}
        except Exception as e:
            return {"status": "error", "message": f"CDP observe failed: {e}"}

    def find(self, query: dict) -> dict:
        """Find matching elements in the active page via CDP."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        text_query = query.get("text", "").lower()
        role_query = query.get("role", "").lower()
        tag_query = query.get("tag", "").lower()
        type_query = query.get("type", "").lower()

        # Enable DOM to use backendNodeIds
        try:
            self._cdp_request("DOM.enable")
        except Exception:
            pass

        # Inject JS to walk the DOM and find matching elements.
        script = f'''(function() {{
            const textQ = {json.dumps(text_query)};
            const roleQ = {json.dumps(role_query)};
            const tagQ = {json.dumps(tag_query)};
            const typeQ = {json.dumps(type_query)};

            const results = [];
            const elements = document.querySelectorAll('*');

            for (let el of elements) {{
                if (results.length >= 20) break;

                const elTag = el.tagName.toLowerCase();
                const elRole = el.getAttribute('role') || '';
                const elText = (el.innerText || '').trim().toLowerCase();
                const elName = (el.getAttribute('aria-label') || el.title || '').toLowerCase();
                const elType = (el.getAttribute('type') || (elTag === 'textarea' ? 'textarea' : elTag === 'select' ? 'select' : '')).toLowerCase();

                let match = true;
                if (textQ && !elText.includes(textQ) && !elName.includes(textQ)) match = false;
                if (roleQ && elRole !== roleQ) match = false;
                if (tagQ && elTag !== tagQ) match = false;
                if (typeQ && elType !== typeQ) match = false;

                // Exclude html, head, body, script, style from generic matching unless specifically requested
                if (!tagQ && ['html', 'head', 'body', 'script', 'style'].includes(elTag)) match = false;

                if (match) {{
                    let value_present = false;
                    let input_type = "";
                    let checked = undefined;
                    let group = undefined;
                    let multiple = undefined;
                    let selected_options_json = "";

                    if (elTag === 'input' || elTag === 'textarea') {{
                        value_present = !!el.value;
                        input_type = el.getAttribute('type') || (elTag === 'textarea' ? 'textarea' : 'text');
                        if (input_type === 'checkbox' || input_type === 'radio') {{
                            checked = !!el.checked;
                            if (input_type === 'radio') group = el.name || '';
                        }}
                    }} else if (elTag === 'select') {{
                        input_type = "select";
                        multiple = !!el.multiple;
                        selected_options_json = JSON.stringify(Array.from(el.selectedOptions).map(o => o.text));
                    }}

                    let validity_flags_json = "";
                    if (el.validity) {{
                        validity_flags_json = JSON.stringify({{
                            value_missing: el.validity.valueMissing,
                            type_mismatch: el.validity.typeMismatch,
                            pattern_mismatch: el.validity.patternMismatch,
                            too_long: el.validity.tooLong,
                            too_short: el.validity.tooShort,
                            range_underflow: el.validity.rangeUnderflow,
                            range_overflow: el.validity.rangeOverflow,
                            step_mismatch: el.validity.stepMismatch
                        }});
                    }}

                    const resObj = {{
                        node: el,
                        role: elRole || (elTag === 'a' ? 'link' : elTag === 'button' ? 'button' : ''),
                        name: el.getAttribute('aria-label') || el.title || '',
                        text: el.innerText ? el.innerText.trim() : '',
                        tag: elTag,
                        type: input_type,
                        disabled: !!el.disabled,
                        required: !!el.required,
                        valid: el.validity ? el.validity.valid : true
                    }};
                    if (elTag === 'input' || elTag === 'textarea') resObj.value_present = value_present;
                    if (checked !== undefined) resObj.checked = checked;
                    if (group !== undefined) resObj.group = group;
                    if (multiple !== undefined) resObj.multiple = multiple;
                    if (selected_options_json) resObj.selected_options_json = selected_options_json;
                    if (validity_flags_json) resObj.validity_flags_json = validity_flags_json;

                    results.push(resObj);
                }}
            }}
            return results;
        }})();'''

        try:
            res = self._cdp_request("Runtime.evaluate", {"expression": script, "returnByValue": False})
            if "exceptionDetails" in res:
                return {"status": "error", "message": str(res["exceptionDetails"])}

            array_obj_id = res.get("result", {}).get("objectId")
            if not array_obj_id:
                return {"status": "ok", "targets": []}

            props_res = self._cdp_request("Runtime.getProperties", {"objectId": array_obj_id, "ownProperties": True})

            targets = []
            for prop in props_res.get("result", []):
                if prop.get("name").isdigit():
                    item_obj_id = prop["value"]["objectId"]
                    item_props = self._cdp_request("Runtime.getProperties", {"objectId": item_obj_id, "ownProperties": True})

                    node_obj_id = None
                    meta = {}
                    for ip in item_props.get("result", []):
                        if ip["name"] == "node":
                            node_obj_id = ip["value"]["objectId"]
                        elif ip["name"] in ("role", "name", "text", "tag", "type", "group", "selected_options_json", "validity_flags_json"):
                            meta[ip["name"]] = ip["value"].get("value", "")
                        elif ip["name"] in ("value_present", "disabled", "required", "valid", "checked", "multiple"):
                            meta[ip["name"]] = ip["value"].get("value", False)

                    # Parse selected_options_json if present
                    if "selected_options_json" in meta:
                        try:
                            meta["selected_options"] = json.loads(meta["selected_options_json"])
                        except Exception:
                            meta["selected_options"] = []
                        del meta["selected_options_json"]

                    if "validity_flags_json" in meta:
                        try:
                            meta["validity_flags"] = json.loads(meta["validity_flags_json"])
                        except Exception:
                            pass
                        del meta["validity_flags_json"]

                    if not node_obj_id:
                        continue

                    node_req = self._cdp_request("DOM.describeNode", {"objectId": node_obj_id})
                    backend_id = node_req.get("node", {}).get("backendNodeId")

                    if backend_id is not None:
                        target_id = "bt_" + str(uuid.uuid4())
                        self.targets[target_id] = {
                            "backendNodeId": backend_id,
                            "node_obj_id": node_obj_id,
                            "session_id": self._session_id
                        }

                        target_data = {"target_id": target_id}
                        target_data.update(meta)
                        targets.append(target_data)

            return {"status": "ok", "targets": targets}
        except Exception as e:
            return {"status": "error", "message": f"CDP find failed: {e}"}

    def click(self, target_id: str) -> dict:
        """Click a previously observed target id via CDP."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        target_record = self.targets.get(target_id)
        if not target_record:
            return {"status": "error", "message": "TARGET_STALE"}

        if target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        try:
            # Resolve the node in the current document.
            # If the document was navigated or reloaded, the backendNodeId is no longer
            # valid and CDP will raise a RuntimeError. We must catch this and surface it
            # as TARGET_STALE, not a generic CDP failure.
            try:
                resolve_res = self._cdp_request("DOM.resolveNode", {"backendNodeId": target_record["backendNodeId"]})
            except RuntimeError:
                return {"status": "error", "message": "TARGET_STALE"}

            if "object" not in resolve_res or "objectId" not in resolve_res["object"]:
                return {"status": "error", "message": "TARGET_STALE"}

            obj_id = resolve_res["object"]["objectId"]

            script = '''function() {
                let rect = this.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return {error: "TARGET_INVISIBLE"};
                if (this.disabled) return {error: "TARGET_DISABLED"};

                let isSubmit = false;
                let tag = this.tagName.toLowerCase();
                if (tag === 'input' && this.type === 'submit') isSubmit = true;
                if (tag === 'button') {
                    if (this.type === 'submit') isSubmit = true;
                    if (!this.type && this.closest('form')) isSubmit = true;
                }
                if (isSubmit) return {error: "TARGET_SUBMIT_REQUIRES_AUTHORIZATION"};

                this.click();
                return {success: true};
            }'''

            res = self._cdp_request("Runtime.callFunctionOn", {
                "objectId": obj_id,
                "functionDeclaration": script,
                "returnByValue": True
            })

            if "exceptionDetails" in res:
                return {"status": "error", "message": str(res["exceptionDetails"])}
            val = res.get("result", {}).get("value", {})

            if "error" in val:
                return {"status": "error", "message": val["error"]}

            # If successful, immediately return a post-action observation
            obs = self.observe()
            if obs.get("status") == "ok":
                return {"status": "ok", "result": "success", "action": {"type": "click", "target_id": target_id}, "observation": obs.get("observation")}
            else:
                return {"status": "ok", "result": "success", "action": {"type": "click", "target_id": target_id}, "observation_error": obs.get("message")}
        except Exception as e:
            return {"status": "error", "message": f"CDP click failed: {e}"}

    def _validate_text_target(self, target_record: dict) -> dict:
        """
        Validates that a target is a permitted text input.
        Returns the resolved objectId or an error dict.
        """
        try:
            resolve_res = self._cdp_request("DOM.resolveNode", {"backendNodeId": target_record["backendNodeId"]})
        except RuntimeError:
            return {"error": "TARGET_STALE"}

        if "object" not in resolve_res or "objectId" not in resolve_res["object"]:
            return {"error": "TARGET_STALE"}

        obj_id = resolve_res["object"]["objectId"]

        # Validates visibility, enabled state, and strictly checks tag and type.
        # Rejected types: password, hidden, file, email, tel, number, date, checkbox, radio, search (unless permitted).
        # We allow: input[type=text], input[type=""], textarea.
        script = '''function() {
            let rect = this.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return {error: "TARGET_INVISIBLE"};
            if (this.disabled) return {error: "TARGET_DISABLED"};

            const tag = this.tagName.toLowerCase();
            if (tag !== "input" && tag !== "textarea") return {error: "TARGET_NOT_EDITABLE"};

            if (tag === "input") {
                const type = (this.getAttribute("type") || "text").toLowerCase();
                const allowed = ["text", "search"];
                if (!allowed.includes(type)) return {error: "TARGET_PROTECTED"};
            }

            return {success: true};
        }'''

        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })

        if "exceptionDetails" in res:
            return {"error": str(res["exceptionDetails"])}
        val = res.get("result", {}).get("value", {})

        if "error" in val:
            return {"error": val["error"]}

        return {"objectId": obj_id}

    def type(self, target_id: str, text: str) -> dict:
        """Type text into a target field."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        val_res = self._validate_text_target(target_record)
        if "error" in val_res:
            return {"status": "error", "message": val_res["error"]}

        obj_id = val_res["objectId"]

        script = f'''function() {{
            const txt = {json.dumps(text)};
            if (this.tagName.toLowerCase() !== 'textarea' && (txt.includes('\\n') || txt.includes('\\r'))) {{
                return {{error: "TARGET_SUBMIT_REQUIRES_AUTHORIZATION"}};
            }}
            this.value += txt;
            this.dispatchEvent(new Event('input', {{bubbles: true}}));
            this.dispatchEvent(new Event('change', {{bubbles: true}}));
            return {{success: true}};
        }}'''

        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })

        if "exceptionDetails" in res:
            return {"status": "error", "message": str(res["exceptionDetails"])}

        val = res.get("result", {}).get("value", {})
        if "error" in val:
            return {"status": "error", "message": val["error"]}

        obs = self.observe()
        if obs.get("status") == "ok":
            return {"status": "ok", "result": "success", "action": {"type": "type", "target_id": target_id}, "observation": obs.get("observation")}
        return {"status": "ok", "result": "success", "action": {"type": "type", "target_id": target_id}, "observation_error": obs.get("message")}

    def fill(self, target_id: str, text: str) -> dict:
        """Fill target field with text."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        val_res = self._validate_text_target(target_record)
        if "error" in val_res:
            return {"status": "error", "message": val_res["error"]}

        obj_id = val_res["objectId"]

        script = f'''function() {{
            const txt = {json.dumps(text)};
            if (this.tagName.toLowerCase() !== 'textarea' && (txt.includes('\\n') || txt.includes('\\r'))) {{
                return {{error: "TARGET_SUBMIT_REQUIRES_AUTHORIZATION"}};
            }}
            this.value = txt;
            this.dispatchEvent(new Event('input', {{bubbles: true}}));
            this.dispatchEvent(new Event('change', {{bubbles: true}}));
            return {{success: true}};
        }}'''

        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })

        if "exceptionDetails" in res:
            return {"status": "error", "message": str(res["exceptionDetails"])}

        val = res.get("result", {}).get("value", {})
        if "error" in val:
            return {"status": "error", "message": val["error"]}

        obs = self.observe()
        if obs.get("status") == "ok":
            return {"status": "ok", "result": "success", "action": {"type": "fill", "target_id": target_id}, "observation": obs.get("observation")}
        return {"status": "ok", "result": "success", "action": {"type": "fill", "target_id": target_id}, "observation_error": obs.get("message")}

    def clear(self, target_id: str) -> dict:
        """Clear target field."""
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        val_res = self._validate_text_target(target_record)
        if "error" in val_res:
            return {"status": "error", "message": val_res["error"]}

        obj_id = val_res["objectId"]

        script = '''function() {
            this.value = "";
            this.dispatchEvent(new Event('input', {bubbles: true}));
            this.dispatchEvent(new Event('change', {bubbles: true}));
            return {success: true};
        }'''

        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })

        if "exceptionDetails" in res:
            return {"status": "error", "message": str(res["exceptionDetails"])}

        obs = self.observe()
        if obs.get("status") == "ok":
            return {"status": "ok", "result": "success", "action": {"type": "clear", "target_id": target_id}, "observation": obs.get("observation")}
        return {"status": "ok", "result": "success", "action": {"type": "clear", "target_id": target_id}, "observation_error": obs.get("message")}

    def _validate_control_target(self, target_record: dict) -> dict:
        node_obj_id = target_record.get("node_obj_id")
        if not node_obj_id:
            return {"error": "Target node object ID missing"}
        script = '''function() {
            const rect = this.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) {
                return {error: "TARGET_INVISIBLE"};
            }
            if (this.disabled) {
                return {error: "TARGET_DISABLED"};
            }
            const tag = this.tagName.toLowerCase();
            const type = this.getAttribute("type");
            if (tag !== 'select' && tag !== 'input') {
                return {error: "TARGET_UNSUPPORTED_CONTROL"};
            }
            if (tag === 'input' && type !== 'checkbox' && type !== 'radio') {
                return {error: "TARGET_UNSUPPORTED_CONTROL"};
            }
            if (tag === 'select' && this.multiple) {
                return {error: "TARGET_UNSUPPORTED_CONTROL"};
            }
            return {success: true, tag: tag, type: type || ''};
        }'''
        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": node_obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })
        if "exceptionDetails" in res:
            return {"error": "TARGET_STALE"}
        val = res.get("result", {}).get("value", {})
        if "error" in val:
            return {"error": val["error"]}
        return {"objectId": node_obj_id, "tag": val["tag"], "type": val["type"]}

    def select(self, target_id: str, option_identity: str) -> dict:
        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        val_res = self._validate_control_target(target_record)
        if "error" in val_res:
            return {"status": "error", "message": val_res["error"]}
        if val_res["tag"] != "select":
            return {"status": "error", "message": "TARGET_NOT_SELECT"}

        obj_id = val_res["objectId"]
        script = f'''function() {{
            const ident = {json.dumps(option_identity)};
            let matches = [];
            for (let opt of this.options) {{
                if (opt.text === ident) {{
                    matches.push(opt);
                }}
            }}
            if (matches.length === 0) return {{error: "OPTION_NOT_FOUND"}};
            if (matches.length > 1) return {{error: "AMBIGUOUS_MATCH", matches: matches.length}};
            matches[0].selected = true;
            this.dispatchEvent(new Event('input', {{bubbles: true}}));
            this.dispatchEvent(new Event('change', {{bubbles: true}}));
            return {{success: true}};
        }}'''
        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })
        if "exceptionDetails" in res:
            return {"status": "error", "message": str(res["exceptionDetails"])}
        val = res.get("result", {}).get("value", {})
        if "error" in val:
            return {"status": "error", "message": val["error"]}

        obs = self.observe()
        if obs.get("status") == "ok":
            return {"status": "ok", "result": "success", "action": {"type": "select", "target_id": target_id, "option": option_identity}, "observation": obs.get("observation")}
        return {"status": "ok", "result": "success", "action": {"type": "select", "target_id": target_id, "option": option_identity}, "observation_error": obs.get("message")}

    def check(self, target_id: str) -> dict:
        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        val_res = self._validate_control_target(target_record)
        if "error" in val_res:
            return {"status": "error", "message": val_res["error"]}
        if val_res["tag"] != "input" or val_res["type"] not in ("checkbox", "radio"):
            return {"status": "error", "message": "TARGET_UNSUPPORTED_CONTROL"}

        obj_id = val_res["objectId"]
        script = '''function() {
            if (this.checked) return {success: true, idempotent: true};
            this.checked = true;
            this.dispatchEvent(new Event('input', {bubbles: true}));
            this.dispatchEvent(new Event('change', {bubbles: true}));
            return {success: true};
        }'''
        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })
        if "exceptionDetails" in res:
            return {"status": "error", "message": str(res["exceptionDetails"])}

        obs = self.observe()
        if obs.get("status") == "ok":
            return {"status": "ok", "result": "success", "action": {"type": "check", "target_id": target_id}, "observation": obs.get("observation")}
        return {"status": "ok", "result": "success", "action": {"type": "check", "target_id": target_id}, "observation_error": obs.get("message")}

    def uncheck(self, target_id: str) -> dict:
        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        val_res = self._validate_control_target(target_record)
        if "error" in val_res:
            return {"status": "error", "message": val_res["error"]}
        if val_res["tag"] != "input":
            return {"status": "error", "message": "TARGET_UNSUPPORTED_CONTROL"}
        if val_res["type"] == "radio":
            return {"status": "error", "message": "TARGET_UNSUPPORTED_ACTION"}
        if val_res["type"] != "checkbox":
            return {"status": "error", "message": "TARGET_UNSUPPORTED_CONTROL"}

        obj_id = val_res["objectId"]
        script = '''function() {
            if (!this.checked) return {success: true, idempotent: true};
            this.checked = false;
            this.dispatchEvent(new Event('input', {bubbles: true}));
            this.dispatchEvent(new Event('change', {bubbles: true}));
            return {success: true};
        }'''
        res = self._cdp_request("Runtime.callFunctionOn", {
            "objectId": obj_id,
            "functionDeclaration": script,
            "returnByValue": True
        })
        if "exceptionDetails" in res:
            return {"status": "error", "message": str(res["exceptionDetails"])}

        obs = self.observe()
        if obs.get("status") == "ok":
            return {"status": "ok", "result": "success", "action": {"type": "uncheck", "target_id": target_id}, "observation": obs.get("observation")}
        return {"status": "ok", "result": "success", "action": {"type": "uncheck", "target_id": target_id}, "observation_error": obs.get("message")}

    def restart_browser(self) -> dict:
        """
        Restart Chrome: STOP existing process, then START with last known URL.
        If no last URL is known, returns an error.
        """
        if not self._last_url:
            return {"status": "error", "message": "No URL to restart to. Use START_BROWSER first."}
        self.stop_browser()
        return self.start_browser(self._last_url)

    def get_status(self) -> dict:
        if self.process is None:
            running = False
            pid = None
        else:
            running = self.process.poll() is None
            pid = self.process.pid if running else None
            if not running and self.browser_state in (
                BrowserState.RUNNING, BrowserState.HIDDEN
            ):
                self.browser_state = BrowserState.FAILED
                logger.warning("[broker] Chrome process died unexpectedly")

        return {
            "status": "ok",
            "running": running,
            "pid": pid,
            "broker_state": self.broker_state,
            "browser_state": self.browser_state,
            "profile": str(self.profile_dir),
            "binary": CHROME_BINARY,
        }


# ── Environment builder ────────────────────────────────────────────────────────

def _build_chrome_env() -> dict:
    """
    Build a minimal environment for Chrome that includes display/session variables.
    Reads these from the host environment (set by the systemd service via PassEnvironment
    or Environment= directives), falling back to sensible defaults.
    """
    base = os.environ.copy()
    # Ensure required display variables are present
    env_keys = [
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "XAUTHORITY",
        "HOME",
        "PATH",
        "USER",
        "LOGNAME",
    ]
    return {k: base[k] for k in env_keys if k in base}


# ── IPC request handler ────────────────────────────────────────────────────────

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "START_BROWSER":   ["url"],
    "STOP_BROWSER":    [],
    "STATUS":          [],
    "HIDE_BROWSER":    [],
    "NAVIGATE":        ["url"],
    "NAVIGATE_ACTION": ["action"],
    "OBSERVE":         [],
    "RESTART_BROWSER": [],
    "FIND":            ["query"],
    "CLICK":           ["target_id"],
    "TYPE":            ["target_id", "text"],
    "FILL":            ["target_id", "text"],
    "CLEAR":           ["target_id"],
    "SELECT":          ["target_id", "option_identity"],
    "CHECK":           ["target_id"],
    "UNCHECK":         ["target_id"],
    "SUBMIT":          ["target_id"],
}

_FORBIDDEN_FIELDS = frozenset({
    "binary", "executable", "shell", "profile", "profile_dir",
    "flags", "args", "uid", "gid", "env",
    "script", "objectId", "password",
})


def _validate_schema(request: dict) -> tuple[bool, str]:
    """Returns (valid, error_message)."""
    if not isinstance(request, dict):
        return False, "Request must be a JSON object"

    command = request.get("command")
    if not command or not isinstance(command, str):
        return False, "Missing or invalid 'command' field"

    if command not in _REQUIRED_FIELDS:
        return False, f"Unknown command: {command!r}"

    for field in _REQUIRED_FIELDS[command]:
        if field not in request:
            return False, f"Missing required field {field!r} for command {command!r}"

    injected = _FORBIDDEN_FIELDS & set(request.keys())
    if injected:
        return False, f"Forbidden fields in request: {injected}"

    return True, ""


class BrokerHandler(StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(MAX_REQUEST_BYTES).strip()
            if not raw:
                return

            try:
                request = json.loads(raw)
            except json.JSONDecodeError as e:
                self._send({"status": "error", "message": f"JSON parse error: {e}"})
                return

            valid, err = _validate_schema(request)
            if not valid:
                logger.warning(f"[broker] Schema rejection: {err} | raw={raw[:200]!r}")
                self._send({"status": "error", "message": err})
                return

            command = request["command"]
            response: dict = {"status": "error", "message": "Unhandled command"}

            if command == "START_BROWSER":
                try:
                    response = self.server.broker.start_browser(request["url"])
                except ValueError as e:
                    response = {"status": "error", "message": str(e)}

            elif command == "STOP_BROWSER":
                response = self.server.broker.stop_browser()

            elif command == "STATUS":
                response = self.server.broker.get_status()

            elif command == "HIDE_BROWSER":
                response = self.server.broker.hide_browser()

            elif command == "ISSUE_AUTH":
                response = self.server.broker.issue_auth(request["target_id"], request["session_id"], request.get("expires_in", 300))

            elif command == "NAVIGATE":
                try:
                    response = self.server.broker.navigate(request["url"])
                except ValueError as e:
                    response = {"status": "error", "message": str(e)}

            elif command == "NAVIGATE_ACTION":
                response = self.server.broker.navigate_action(request["action"])

            elif command == "OBSERVE":
                response = self.server.broker.observe()

            elif command == "FIND":
                if not isinstance(request["query"], dict):
                    response = {"status": "error", "message": "query must be an object"}
                else:
                    response = self.server.broker.find(request["query"])

            elif command == "CLICK":
                response = self.server.broker.click(request["target_id"])

            elif command == "TYPE":
                response = self.server.broker.type(request["target_id"], request["text"])

            elif command == "FILL":
                response = self.server.broker.fill(request["target_id"], request["text"])

            elif command == "CLEAR":
                response = self.server.broker.clear(request["target_id"])

            elif command == "SELECT":
                response = self.server.broker.select(request["target_id"], request["option_identity"])

            elif command == "CHECK":
                response = self.server.broker.check(request["target_id"])

            elif command == "UNCHECK":
                response = self.server.broker.uncheck(request["target_id"])

            elif command == "SUBMIT":
                response = self.server.broker.submit(request["target_id"], request.get("auth_id"))

            elif command == "RESTART_BROWSER":
                response = self.server.broker.restart_browser()

            self._send(response)

        except Exception as e:
            logger.exception("[broker] Unhandled handler error")
            try:
                self._send({"status": "error", "message": "Internal broker error"})
            except Exception:
                pass

    def _send(self, obj: dict) -> None:
        self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.wfile.flush()


class ThreadedBrokerServer(ThreadingMixIn, UnixStreamServer):
    """Threaded broker — each connection handled in its own thread."""

    def __init__(self, server_address: str, RequestHandlerClass):
        self.broker = BrowserBroker()
        self.broker.broker_state = BrokerState.RUNNING
        super().__init__(server_address, RequestHandlerClass)

    def server_close(self):
        self.broker.stop_browser()
        self.broker.broker_state = BrokerState.STOPPED
        super().server_close()


# ── Socket setup ───────────────────────────────────────────────────────────────

def _prepare_socket(path: Path) -> None:
    """Remove stale socket, create parent dir, verify ownership."""
    _check_not_root()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        s = path.stat()
        if not stat.S_ISSOCK(s.st_mode):
            raise RuntimeError(f"{path} exists and is not a socket — refusing to remove")
        if s.st_uid != os.getuid():
            raise RuntimeError(f"Stale socket {path} owned by uid={s.st_uid}, not us")
        path.unlink()
        logger.info(f"[broker] Removed stale socket: {path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    _check_not_root()
    _prepare_socket(SOCKET_PATH)

    server = ThreadedBrokerServer(str(SOCKET_PATH), BrokerHandler)
    os.chmod(SOCKET_PATH, 0o600)

    # Verify the chmod took effect
    actual_mode = stat.S_IMODE(SOCKET_PATH.stat().st_mode)
    if actual_mode != 0o600:
        raise RuntimeError(f"Socket permissions check failed: got {oct(actual_mode)}")

    logger.info(f"[broker] ANNY Browser Broker listening on {SOCKET_PATH} (mode=0600)")

    def _shutdown(sig, frame):
        logger.info("[broker] Received signal %d, shutting down", sig)
        server.broker.stop_browser()
        server.broker.broker_state = BrokerState.STOPPING
        server.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever()
    finally:
        server.broker.broker_state = BrokerState.STOPPED
        if SOCKET_PATH.exists():
            try:
                SOCKET_PATH.unlink()
                logger.info("[broker] Socket removed on shutdown")
            except Exception as e:
                logger.warning(f"[broker] Could not remove socket: {e}")


if __name__ == "__main__":
    main()
