import os
import json
import socket
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class BrowserManagerError(Exception):
    pass

class BrowserSessionManager:
    """
    Manages a dedicated ANNY browser profile by communicating with the external
    Browser Broker via IPC. All decisions (binary, profile, flags) are made
    inside the broker. This class only sends validated commands.
    """
    def __init__(self, profile: str = "colab"):
        self.profile = profile
        self.socket_path = Path.home() / ".anny" / "browser-broker.sock"
        if not self.socket_path.exists():
            logger.warning(
                f"Browser Broker socket not found at {self.socket_path}. "
                "Is the service running?"
            )

    @classmethod
    def create(cls, profile: str = "colab") -> "BrowserSessionManager":
        return cls(profile)

    def _send_ipc(self, command: str, **kwargs) -> dict:
        if not self.socket_path.exists():
            logger.error("Browser broker socket is missing.")
            return {"status": "error", "message": "Broker unavailable"}

        payload = {"command": command}
        payload.update(kwargs)

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(15.0)
                s.connect(str(self.socket_path))
                s.sendall((json.dumps(payload) + "\n").encode("utf-8"))

                data = s.recv(4096)
                if not data:
                    return {"status": "error", "message": "Empty response from broker"}

                return json.loads(data.decode("utf-8").strip())
        except Exception as e:
            logger.error(f"IPC Error communicating with Browser Broker: {e}")
            return {"status": "error", "message": str(e)}

    def launch(self, url: str) -> None:
        """Requests the Broker to launch the browser, navigating directly to the URL."""
        logger.info(f"Requesting managed browser launch for profile {self.profile} via IPC")
        res = self._send_ipc("START_BROWSER", url=url)
        if res.get("status") != "ok":
            logger.error(f"Broker failed to launch browser: {res.get('message')}")

    def hide(self) -> dict:
        """
        Requests the Broker to hide (minimize) the governed browser window via xdotool.
        Returns broker response dict. Check 'status': 'unavailable' = xdotool absent.
        The Chrome process stays alive — RemoteComputeSession is unaffected.
        """
        logger.info("Requesting managed browser hide via IPC")
        return self._send_ipc("HIDE_BROWSER")

    def navigate(self, url: str) -> dict:
        """
        Requests the Broker to navigate the governed browser to a validated URL.
        Scheme must be http, https, or about — enforced by the broker.
        """
        logger.info(f"Requesting managed browser navigate to {url!r} via IPC")
        return self._send_ipc("NAVIGATE", url=url)

    def restart(self) -> dict:
        """Requests the Broker to restart the governed browser (STOP then START last URL)."""
        logger.info("Requesting managed browser restart via IPC")
        return self._send_ipc("RESTART_BROWSER")

    def is_running(self) -> bool:
        res = self._send_ipc("STATUS")
        return res.get("status") == "ok" and res.get("running") is True

    def get_status(self) -> dict:
        """Return the full broker STATUS response dict."""
        return self._send_ipc("STATUS")

    def terminate(self):
        """Requests the Broker to close the browser session."""
        logger.info("Requesting managed browser termination via IPC")
        self._send_ipc("STOP_BROWSER")

    def navigate_action(self, action: str) -> dict:
        """
        Requests the Broker to perform a navigation action via CDP (back, forward, reload).
        """
        logger.info(f"Requesting managed browser navigate action: {action} via IPC")
        return self._send_ipc("NAVIGATE_ACTION", action=action)

    def observe(self) -> dict:
        """
        Requests the Broker to observe the active page via CDP.
        """
        logger.info("Requesting managed browser observation via IPC")
        return self._send_ipc("OBSERVE")

    def find(self, query: dict) -> dict:
        """
        Requests the Broker to find matching elements on the active page.
        Query dimensions: text, role, tag.
        Returns bounded list of BrowserTarget candidates with Broker-generated target_ids.
        """
        logger.info(f"Requesting managed browser find with query={query} via IPC")
        return self._send_ipc("FIND", query=query)

    def click(self, target_id: str) -> dict:
        """
        Requests the Broker to click a previously discovered target.
        The target_id must have been returned by a prior find() call
        on the same page state. Returns action result + post-action observation.
        """
        logger.info(f"Requesting managed browser click on target_id={target_id} via IPC")
        return self._send_ipc("CLICK", target_id=target_id)

    def type(self, target_id: str, text: str) -> dict:
        """
        Requests the Broker to type text into a previously discovered target.
        """
        logger.info(f"Requesting managed browser type on target_id={target_id} via IPC")
        return self._send_ipc("TYPE", target_id=target_id, text=text)

    def fill(self, target_id: str, text: str) -> dict:
        """
        Requests the Broker to fill text into a previously discovered target.
        """
        logger.info(f"Requesting managed browser fill on target_id={target_id} via IPC")
        return self._send_ipc("FILL", target_id=target_id, text=text)

    def clear(self, target_id: str) -> dict:
        """
        Requests the Broker to clear text from a previously discovered target.
        """
        logger.info(f"Requesting managed browser clear on target_id={target_id} via IPC")
        return self._send_ipc("CLEAR", target_id=target_id)

    def select(self, target_id: str, option_identity: str) -> dict:
        """
        Requests the Broker to select an option in a select target.
        """
        logger.info(f"Requesting managed browser select on target_id={target_id} via IPC")
        return self._send_ipc("SELECT", target_id=target_id, option_identity=option_identity)

    def check(self, target_id: str) -> dict:
        """
        Requests the Broker to check a checkbox or radio target.
        """
        logger.info(f"Requesting managed browser check on target_id={target_id} via IPC")
        return self._send_ipc("CHECK", target_id=target_id)

    def uncheck(self, target_id: str) -> dict:
        """
        Requests the Broker to uncheck a checkbox target.
        """
        logger.info(f"Requesting managed browser uncheck on target_id={target_id} via IPC")
        return self._send_ipc("UNCHECK", target_id=target_id)

    def issue_authorization(self, target_id: str, session_id: str, expires_in: int = 300) -> dict:
        """
        Requests the Broker to issue an opaque authorization token for a form submission.
        """
        logger.info(f"Requesting managed browser to issue auth for target_id={target_id} via IPC")
        return self._send_ipc("ISSUE_AUTH", target_id=target_id, session_id=session_id, expires_in=expires_in)

    def submit(self, target_id: str, auth_id: str) -> dict:
        """
        Requests the Broker to submit a target form.
        """
        logger.info(f"Requesting managed browser submit on target_id={target_id} via IPC")
        return self._send_ipc("SUBMIT", target_id=target_id, auth_id=auth_id)
