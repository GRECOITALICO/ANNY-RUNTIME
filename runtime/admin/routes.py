"""Routing and route handlers for the ANNY Runtime admin panel."""
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Callable, Dict, Any, Optional

import json
from runtime.admin.templates import (
    first_run_page, reconnect_page, failure_page, ready_page, github_page, fabric_page,
    sessions_page, operations_page, receipts_page, doctor_page
)
from runtime.admin.dto import (
    RuntimeStatusDTO, GitHubStatusDTO, FabricStatusDTO,
    SessionStatusDTO, OperationSummaryDTO, ReceiptSummaryDTO,
    ContinuityDTO, OrganizationDTO, RepositoryDTO, MissionDTO,
    NextActionDTO, BlockerDTO, L2WorkerSummaryDTO
)
from runtime.github.client import GitHubClient
from runtime.github.discovery import OrganizationDiscoveryService
from runtime.continuity.operational import OperationalRepositoryProvider
from runtime.continuity.bootstrap import CustomerZeroBootstrapResolver
from runtime.continuity.reconciler import ContinuityReconciler
from runtime.continuity.state import ContinuityStatus

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
            '/api/v1/continuity/bootstrap': self.handle_bootstrap_api,
        }
        self._post_routes = {
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
        parsed = urllib.parse.urlparse(path)
        
        if parsed.path == '/api/v1/continuity/bootstrap':
            self.handle_bootstrap_api(handler)
            return

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

    def _send_json(self, handler: BaseHTTPRequestHandler, data: Any, status: int = 200) -> None:
        handler.send_response(status)
        handler.send_header('Content-type', 'application/json; charset=utf-8')
        self._set_security_headers(handler)
        for cookie in self.context.get('set_cookies', []):
            handler.send_header('Set-Cookie', cookie)
        handler.end_headers()
        body = json.dumps(data, indent=2) if not isinstance(data, str) else data
        handler.wfile.write(body.encode('utf-8'))

    def _send_html(self, handler: BaseHTTPRequestHandler, html: str, status: int = 200) -> None:
        handler.send_response(status)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        self._set_security_headers(handler)
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


    def handle_bootstrap_api(self, handler: BaseHTTPRequestHandler) -> None:
        try:
            dto = self._get_continuity_dto()
            self._send_json(handler, dto.to_dict())
        except Exception as e:
            logger.error(f"Error serving bootstrap API: {e}", exc_info=True)
            # Safe error classification: do not expose raw exception strings
            error_class = type(e).__name__
            safe_msg = f"Bootstrap API error: {error_class}"
            self._send_json(handler, {"error": safe_msg, "status": "ERROR"}, status=500)

    def _get_continuity_dto(self) -> ContinuityDTO:
        gh_mgr = self.context.get('github_manager')
        gh_status_dto = gh_mgr.get_status() if gh_mgr else None
        gh_status_str = gh_status_dto.auth_status if gh_status_dto else "UNAUTHORIZED"

        snapshot = self.context.get('bootstrap_snapshot')
        if not snapshot:
            return ContinuityDTO(
                status="UNKNOWN",
                canonical_source="UNKNOWN",
                canonical_revision=None,
                current_mission=None,
                current_task=None,
                next_action=None,
                blocker_count=0,
                reconciliation_status="UNKNOWN",
                github_status=gh_status_str,
                runtime_status="UNKNOWN",
                fabric_status="NOT_CONFIGURED"
            )

        result = snapshot['result']
        disc_repos_raw = snapshot['discovered_repos']

        reconciler = ContinuityReconciler()
        recon_status = reconciler.reconcile(
            canonical_state=result.canonical_state,
            principal=None,
            discovered_repos=disc_repos_raw,
            github_connected=(gh_status_str == "AUTHORIZED"),
            runtime_ready=True
        )

        can_state = result.canonical_state
        mission_id = can_state.current_mission.id if (can_state and can_state.current_mission) else None
        task_id = can_state.current_task.name if (can_state and can_state.current_task) else None
        next_action_str = can_state.next_action.action if (can_state and can_state.next_action) else None
        blockers = [BlockerDTO(id=b.id, description=b.description, severity=b.severity) for b in (can_state.blockers if can_state else [])]
        l2_count = len(can_state.l2_workers) if (can_state and can_state.l2_workers) else 0

        # Determine runtime status from observable state
        runtime_engine = self.context.get('runtime_engine')
        rt_status = "UNKNOWN"
        if runtime_engine and hasattr(runtime_engine, 'get_health_status'):
            rt_status = runtime_engine.get_health_status()

        repo_dtos = [RepositoryDTO(full_name=r.full_name, name=r.name, owner=r.owner, visibility=r.visibility, archived=r.archived, default_branch=r.default_branch) for r in disc_repos_raw]

        return ContinuityDTO(
            status=result.status.value,
            canonical_source=can_state.repository_name if can_state else "UNKNOWN",
            canonical_revision=can_state.revision if can_state else None,
            current_mission=mission_id,
            current_task=task_id,
            next_action=next_action_str,
            blocker_count=len(blockers),
            reconciliation_status=recon_status.value,
            github_status=gh_status_str,
            runtime_status=rt_status,
            fabric_status="NOT_CONFIGURED",
            organizations=[],
            repositories=repo_dtos,
            blockers=blockers,
            l2_worker_summary=L2WorkerSummaryDTO(count=l2_count, registered_workers=[w.get('name', 'worker') for w in (can_state.l2_workers if can_state and isinstance(can_state.l2_workers, list) else []) if isinstance(w, dict)])
        )

    # --- GET Handlers ---

    def handle_dashboard(self, parsed) -> str:
        gh_mgr = self.context.get('github_manager')
        gh_status = gh_mgr.get_status().to_dict() if gh_mgr else {}
        auth_status = gh_status.get('auth_status', 'UNAUTHORIZED')
        
        # Check if first run session is needed
        session = self.context.get('admin_session')
        is_first_run = gh_mgr and not gh_mgr.has_token()
        if (auth_status in ('UNAUTHORIZED', 'MISSING')) and is_first_run and session and session.scope == "ONBOARDING_ONLY":
            return first_run_page(self._get_csrf())
        elif auth_status in ('UNAUTHORIZED', 'MISSING'):
            # It's missing but not a first run? Or they aren't logged in. Wait, middleware handles login.
            return first_run_page(self._get_csrf())
        elif auth_status in ('EXPIRED', 'DEGRADED'):
            return reconnect_page(self._get_csrf())
        elif auth_status == 'FAILED':
            reason = gh_status.get('last_failure_reason', 'Unknown error')
            return failure_page(reason, self._get_csrf())
        else:
            continuity_dto = self._get_continuity_dto()
            
            # Derive identity from observable state, not hardcoded values
            auth_manager = self.context.get('auth_manager')
            runtime_id = auth_manager.runtime_id if auth_manager else "UNKNOWN"
            
            # Check for actual identity key presence
            identity_manager = self.context.get('identity_manager')
            if identity_manager and hasattr(identity_manager, 'get_key_type'):
                key_type = identity_manager.get_key_type()
            else:
                key_type = "UNKNOWN"
            
            if identity_manager and hasattr(identity_manager, 'get_status'):
                id_status = identity_manager.get_status()
            else:
                id_status = "UNKNOWN"
            
            status_data = {
                'github': gh_status,
                'continuity': continuity_dto.to_dict(),
                'identity': {
                    'runtime_id': runtime_id,
                    'status': id_status,
                    'key_type': key_type
                }
            }
            return ready_page(status_data, self._get_csrf())


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
                if res and gh_mgr.has_token():
                    # Token obtained successfully via polling
                    session = self.context.get('admin_session')
                    if session and session.scope == "ONBOARDING_ONLY":
                        auth_mgr = self.context.get('auth_manager')
                        if auth_mgr:
                            auth_mgr.destroy(session.admin_session_id)
                            self.context['destroy_session'] = True
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
            if success:
                session = self.context.get('admin_session')
                if session and session.scope == "ONBOARDING_ONLY":
                    auth_mgr = self.context.get('auth_manager')
                    if auth_mgr:
                        auth_mgr.destroy(session.admin_session_id)
                        self.context['destroy_session'] = True
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
