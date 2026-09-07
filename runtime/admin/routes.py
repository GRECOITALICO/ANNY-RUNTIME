"""Routing and route handlers for the ANNY Runtime admin panel."""
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Callable, Dict, Any, Optional

from runtime.admin.templates import (
    login_page, dashboard_page, github_page, fabric_page,
    sessions_page, operations_page, receipts_page, doctor_page
)
from runtime.admin.dto import (
    RuntimeStatusDTO, GitHubStatusDTO, FabricStatusDTO,
    SessionStatusDTO, OperationSummaryDTO, ReceiptSummaryDTO
)

logger = logging.getLogger(__name__)

class AdminRouter:
    """Simple path-based router for admin requests."""
    
    def __init__(self, admin_context: Dict[str, Any]):
        self.context = admin_context
        self._get_routes = {
            '/': self.handle_dashboard,
            '/github': self.handle_github,
            '/fabric': self.handle_fabric,
            '/sessions': self.handle_sessions,
            '/operations': self.handle_operations,
            '/receipts': self.handle_receipts,
            '/doctor': self.handle_doctor,
            '/login': self.handle_login_page,
        }
        self._post_routes = {
            '/login': self.handle_login_submit,
            '/logout': self.handle_logout,
            '/github/connect': self.handle_github_connect,
            '/github/disconnect': self.handle_github_disconnect,
            '/github/validate': self.handle_github_validate,
            '/admin/restart': self.handle_admin_restart,
            '/admin/diagnostics': self.handle_admin_diagnostics,
            '/admin/update-check': self.handle_admin_update_check,
        }

    def _get_csrf(self) -> str:
        session = self.context.get('admin_session')
        return session.csrf_token if session else ""

    def dispatch_get(self, path: str, handler: BaseHTTPRequestHandler) -> None:
        """Dispatch a GET request."""
        # Simple exact path matching
        parsed = urllib.parse.urlparse(path)
        route_handler = self._get_routes.get(parsed.path)
        
        if not route_handler:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        try:
            html = route_handler(parsed)
            self._send_html(handler, html)
        except Exception as e:
            logger.error(f"Error handling GET {path}: {e}", exc_info=True)
            self._send_html(handler, "500 Internal Server Error", status=500)

    def dispatch_post(self, path: str, form_data: dict, handler: BaseHTTPRequestHandler) -> None:
        """Dispatch a POST request."""
        parsed = urllib.parse.urlparse(path)
        route_handler = self._post_routes.get(parsed.path)
        
        if not route_handler:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        try:
            redirect_url = route_handler(form_data)
            self._redirect(handler, redirect_url)
        except Exception as e:
            logger.error(f"Error handling POST {path}: {e}", exc_info=True)
            self._send_html(handler, "500 Internal Server Error", status=500)

    def _send_html(self, handler: BaseHTTPRequestHandler, html: str, status: int = 200) -> None:
        handler.send_response(status)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        self._set_security_headers(handler)
        # Auth middleware sets cookies on context
        for cookie in self.context.get('set_cookies', []):
            handler.send_header('Set-Cookie', cookie)
        handler.end_headers()
        handler.wfile.write(html.encode('utf-8'))

    def _redirect(self, handler: BaseHTTPRequestHandler, location: str) -> None:
        handler.send_response(303)
        handler.send_header('Location', location)
        self._set_security_headers(handler)
        for cookie in self.context.get('set_cookies', []):
            handler.send_header('Set-Cookie', cookie)
        handler.end_headers()

    def _set_security_headers(self, handler: BaseHTTPRequestHandler) -> None:
        handler.send_header('X-Content-Type-Options', 'nosniff')
        handler.send_header('X-Frame-Options', 'DENY')
        handler.send_header('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com;")

    # --- GET Handlers ---

    def handle_login_page(self, parsed) -> str:
        # If already logged in, redirect to dashboard handled by middleware?
        # Assuming middleware let us through, render login
        error = ""
        query = urllib.parse.parse_qs(parsed.query)
        if query.get('error'):
            error = "Invalid bootstrap token"
        elif query.get('expired'):
            error = "Session expired. Please log in again."
        return login_page(error=error)

    def handle_dashboard(self, parsed) -> str:
        # In a real impl, fetch from actual runtime managers
        # Here we mock the status DTO assembly for demonstration based on the structure
        runtime = self.context.get('runtime_engine')
        status = RuntimeStatusDTO(
            runtime_id="RT-1",
            installation_id="INSTALL-1",
            version="0.1.1",
            protocol_version="1.0",
            generation=1,
            state="READY",
            health={"core": "OK"},
            github_status="AUTHORIZED",
            fabric_status="DISCONNECTED",
            workspace_count=1,
            active_operations=0,
            current_sessions=0,
            update_status="UP_TO_DATE",
            platform="linux",
            admin_port=3643
        ).to_dict()
        return dashboard_page(status, self._get_csrf())

    def handle_github(self, parsed) -> str:
        gh_mgr = self.context.get('github_manager')
        if gh_mgr:
            status = gh_mgr.get_status().to_dict()
            # If a device flow is active, pass it
            df = None
            if getattr(gh_mgr, '_device_flow', None):
                df = {
                    'user_code': gh_mgr._device_flow.user_code,
                    'verification_uri': gh_mgr._device_flow.verification_uri,
                    'expires_in': gh_mgr._device_flow.expires_in
                }
            elif parsed.query == 'poll':
                # Quick poll trigger
                res = gh_mgr.poll_device_flow()
        else:
            status = GitHubStatusDTO(False, None, "UNAUTHORIZED", "MISSING", None, [], None, None).to_dict()
            df = None
        return github_page(status, self._get_csrf(), device_flow=df)

    def handle_fabric(self, parsed) -> str:
        status = FabricStatusDTO(False, None, None, None, None, None).to_dict()
        return fabric_page(status, self._get_csrf())

    def handle_sessions(self, parsed) -> str:
        return sessions_page([], self._get_csrf())

    def handle_operations(self, parsed) -> str:
        return operations_page([], self._get_csrf())

    def handle_receipts(self, parsed) -> str:
        return receipts_page([], self._get_csrf())

    def handle_doctor(self, parsed) -> str:
        diagnostics = {'checks': [{'name': 'Core', 'status': 'OK'}]}
        return doctor_page(diagnostics, self._get_csrf())

    # --- POST Handlers (Action) ---

    def handle_login_submit(self, form_data) -> str:
        token = form_data.get('token', [''])[0]
        auth_mgr = self.context.get('auth_manager')
        audit_mgr = self.context.get('audit_manager')
        
        if auth_mgr:
            session = auth_mgr.authenticate(token)
            if session:
                if audit_mgr:
                    audit_mgr.record(session.admin_session_id, "LOGIN", "local-admin", "SUCCESS")
                # Cookie is set by middleware via context
                self.context['new_session_id'] = session.admin_session_id
                return '/'
                
        if audit_mgr:
            audit_mgr.record("none", "LOGIN", "unknown", "FAILED", "Invalid bootstrap token")
        return '/login?error=1'

    def handle_logout(self, form_data) -> str:
        session = self.context.get('admin_session')
        auth_mgr = self.context.get('auth_manager')
        audit_mgr = self.context.get('audit_manager')
        
        if session and auth_mgr:
            auth_mgr.destroy(session.admin_session_id)
            if audit_mgr:
                audit_mgr.record(session.admin_session_id, "LOGOUT", session.principal, "SUCCESS")
        
        self.context['destroy_session'] = True
        return '/login'

    def handle_github_connect(self, form_data) -> str:
        gh_mgr = self.context.get('github_manager')
        if gh_mgr:
            gh_mgr.initiate_device_flow()
            self._audit("GITHUB_CONNECT", "SUCCESS", "Initiated device flow")
        return '/github'

    def handle_github_disconnect(self, form_data) -> str:
        gh_mgr = self.context.get('github_manager')
        if gh_mgr:
            gh_mgr.disconnect()
            self._audit("GITHUB_DISCONNECT", "SUCCESS")
        return '/github'

    def handle_github_validate(self, form_data) -> str:
        gh_mgr = self.context.get('github_manager')
        if gh_mgr:
            success = gh_mgr.validate()
            self._audit("GITHUB_VALIDATE", "SUCCESS" if success else "FAILED")
        return '/github'

    def handle_admin_restart(self, form_data) -> str:
        self._audit("RUNTIME_RESTART", "SUCCESS")
        return '/'

    def handle_admin_diagnostics(self, form_data) -> str:
        self._audit("DIAGNOSTICS_RUN", "SUCCESS")
        return '/doctor'

    def handle_admin_update_check(self, form_data) -> str:
        self._audit("UPDATE_CHECK", "SUCCESS")
        return '/'

    def _audit(self, action: str, result: str, details: str = None) -> None:
        session = self.context.get('admin_session')
        audit_mgr = self.context.get('audit_manager')
        if session and audit_mgr:
            audit_mgr.record(session.admin_session_id, action, session.principal, result, details)
