"""Middleware for the ANNY Runtime admin panel.

Handles Authentication, CSRF validation, and Session Cookies.
"""
import logging
import urllib.parse
from http.cookies import SimpleCookie
from typing import Dict, Any, Callable

from runtime.admin.auth import AdminSessionManager
from runtime.admin.csrf import validate_csrf_token

logger = logging.getLogger(__name__)

# Routes explicitly permitted during onboarding (first-run session)
ONBOARDING_ROUTES = {
    '/',                 # Dashboard (renders first-run page when no token)
    '/github/token',     # POST: submit GitHub token
}

class AdminMiddleware:
    
    def __init__(self, auth_manager: AdminSessionManager, github_manager: Any = None):
        self.auth_manager = auth_manager
        self.github_manager = github_manager
        # Paths that bypass auth entirely
        self.public_paths = set()

    def process_request(self, method: str, path: str, headers, context: Dict[str, Any]) -> bool:
        """
        Process incoming request headers.
        Returns True if request should proceed, False if it should be rejected/redirected.
        """
        parsed = urllib.parse.urlparse(path)
        is_public = parsed.path in self.public_paths or parsed.path.startswith('/api/v1/bridge/')
        # 1. Determine Transport Security (P0-A First-Run Cookie Transport)
        host = headers.get('Host', '')
        if host.startswith('['):
            host_no_port = host.split(']')[0] + ']'
        else:
            host_no_port = host.split(':')[0]
        is_local = host_no_port in ('127.0.0.1', 'localhost', '::1', '[::1]')
        context['secure_cookie'] = not is_local

        # 2. Authenticate Session
        session_id = None
        if 'Cookie' in headers:
            cookie = SimpleCookie(headers['Cookie'])
            if 'admin_session_id' in cookie:
                session_id = cookie['admin_session_id'].value

        session = None
        if session_id:
            session = self.auth_manager.validate(session_id)

        # Store session in context for route handlers
        context['admin_session'] = session
        context['set_cookies'] = []

        is_first_run = self.github_manager and not self.github_manager.has_token()

        if is_first_run and not session:
            # Only create onboarding session for onboarding routes
            if parsed.path in ONBOARDING_ROUTES:
                session = self.auth_manager.create_first_run_session()
                context['admin_session'] = session
                context['new_session_id'] = session.admin_session_id
            else:
                # Non-onboarding route during first run with no session: redirect to dashboard
                context['redirect_to'] = '/'
                return False

        # Enforce scope: ONBOARDING_ONLY sessions cannot access non-onboarding routes
        if session and session.scope == "ONBOARDING_ONLY":
            if parsed.path not in ONBOARDING_ROUTES:
                context['redirect_to'] = '/'
                return False

        if not is_first_run and not session and is_local:
            session = self.auth_manager.create_session("local-admin")
            context['admin_session'] = session
            context['new_session_id'] = session.admin_session_id

        # Enforce Auth
        if not session and not is_public:
            context['redirect_to'] = '/'
            return False

        return True

    def revoke_onboarding_session(self, context: Dict[str, Any]) -> None:
        """Revoke the onboarding session after successful GitHub connection.
        
        Called by route handlers when onboarding completes successfully.
        """
        session = context.get('admin_session')
        if session and session.scope == "ONBOARDING_ONLY":
            self.auth_manager.destroy(session.admin_session_id)
            context['destroy_session'] = True
            context['admin_session'] = None
            logger.info(f"Onboarding session revoked: {session.admin_session_id}")

    def process_post_body(self, path: str, form_data: Dict[str, list], context: Dict[str, Any]) -> bool:
        """Validate CSRF on mutating requests."""
        parsed = urllib.parse.urlparse(path)
        if parsed.path in self.public_paths or parsed.path.startswith('/api/v1/bridge/'):
            return True # No CSRF on public routes

        session = context.get('admin_session')
        if not session:
            return False

        # Extract CSRF token from form data
        request_token = form_data.get('csrf_token', [''])[0]
        
        if not validate_csrf_token(session.csrf_token, request_token):
            logger.warning(f"CSRF validation failed for {path}")
            context['redirect_to'] = '/'
            return False
            
        return True

    def process_response(self, context: Dict[str, Any]) -> None:
        """Set or clear cookies based on context flags set by handlers."""
        cookies = context.get('set_cookies', [])
        secure_cookie = context.get('secure_cookie', True)
        
        if context.get('new_session_id'):
            c = SimpleCookie()
            c['admin_session_id'] = context['new_session_id']
            c['admin_session_id']['httponly'] = True
            c['admin_session_id']['samesite'] = 'Strict'
            c['admin_session_id']['path'] = '/'
            c['admin_session_id']['max-age'] = self.auth_manager.ttl_seconds
            if secure_cookie:
                c['admin_session_id']['secure'] = True
            cookies.append(c['admin_session_id'].OutputString())
            
        if context.get('destroy_session'):
            c = SimpleCookie()
            c['admin_session_id'] = ''
            c['admin_session_id']['httponly'] = True
            c['admin_session_id']['samesite'] = 'Strict'
            c['admin_session_id']['path'] = '/'
            c['admin_session_id']['max-age'] = 0
            if secure_cookie:
                c['admin_session_id']['secure'] = True
            cookies.append(c['admin_session_id'].OutputString())
            
        context['set_cookies'] = cookies

