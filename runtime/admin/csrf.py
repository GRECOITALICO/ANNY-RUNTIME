"""CSRF protection for the ANNY Runtime admin panel."""
import secrets
import hmac
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def validate_csrf_token(session_token: Optional[str],
                        request_token: Optional[str]) -> bool:
    """Validate a CSRF token from a request against the session token.

    Uses constant-time comparison to prevent timing attacks.
    """
    if not session_token or not request_token:
        logger.warning("CSRF validation failed: missing token")
        return False
    return hmac.compare_digest(session_token, request_token)
