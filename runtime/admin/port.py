"""Port selection and conflict detection for the ANNY Runtime admin server."""
import socket
import logging

logger = logging.getLogger(__name__)

FORBIDDEN_PORTS = {3434}  # Reserved by Legacy Architecture — MUST NOT USE


def check_port_available(host: str, port: int) -> bool:
    """Check if a port is available by attempting to bind."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def select_admin_port(host: str = '127.0.0.1', preferred: int = 3643,
                      forbidden: set = None) -> int:
    """Select an available admin port, never using forbidden ports.

    Raises ValueError if the preferred port is forbidden.
    Raises RuntimeError if no available port can be found.
    """
    if forbidden is None:
        forbidden = FORBIDDEN_PORTS
    else:
        forbidden = forbidden | FORBIDDEN_PORTS

    if preferred in forbidden:
        raise ValueError(f"Preferred port {preferred} is in the forbidden list")

    if check_port_available(host, preferred):
        logger.info(f"Admin port {preferred} is available")
        return preferred

    logger.warning(f"Preferred admin port {preferred} is occupied, searching alternatives")
    candidates = [3644, 3645, 3646, 3647, 3648, 3650, 3700, 3800, 3900, 4643]
    for port in candidates:
        if port not in forbidden and check_port_available(host, port):
            logger.info(f"Selected alternative admin port: {port}")
            return port

    raise RuntimeError("No available admin port found")
