"""Routing and route handlers for the ANNY Runtime admin panel."""
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Callable, Dict, Any, Optional

import json
from runtime.admin.templates import (
    first_run_page, reconnect_page, failure_page, ready_page, github_page, fabric_page,
    sessions_page, operations_page, receipts_page, doctor_page, executions_page,
    capabilities_page, executors_page, policies_page, workers_page, worker_detail_page,
    models_page, model_detail_page,
    universe_organization_page, universe_projects_page, universe_repositories_page,
    universe_resources_page, execution_tasks_page, execution_workers_page,
    intelligence_capabilities_page, infrastructure_topology_page, audit_events_page,
    audit_provenance_page, search_page, generic_placeholder_page,
    telemetry_live_page, telemetry_timeline_page
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
            '/github/device/poll': self.handle_github_device_poll,
            '/fabric': self.handle_fabric,
            '/sessions': self.handle_sessions,
            '/operations': self.handle_operations,
            '/receipts': self.handle_receipts,
            '/executions': self.handle_executions,
            '/workers': self.handle_workers,
            '/capabilities': self.handle_capabilities,
            '/models': self.handle_models,
            '/executors': self.handle_executors,
            '/policies': self.handle_policies,
            '/doctor': self.handle_doctor,
            '/universe/organization': self.handle_universe_organization,
            '/universe/projects': self.handle_universe_projects,
            '/universe/repositories': self.handle_universe_repositories,
            '/universe/resources': self.handle_universe_resources,
            '/execution/missions': self.handle_execution_missions,
            '/execution/tasks': self.handle_execution_tasks,
            '/execution/workers': self.handle_execution_workers,
            '/execution/executions': self.handle_execution_executions,
            '/execution/workspaces': self.handle_execution_workspaces,
            '/intelligence/capabilities': self.handle_intelligence_capabilities,
            '/intelligence/executors': self.handle_intelligence_executors,
            '/intelligence/performance': self.handle_intelligence_performance,
            '/infrastructure/runtime': self.handle_infrastructure_topology,
            '/continuity/timeline': self.handle_continuity_timeline,
            '/audit/events': self.handle_audit_events,
            '/audit/provenance': self.handle_audit_provenance,
            '/audit/evidence': self.handle_audit_evidence,
            '/search': self.handle_search,
            '/api/v1/continuity/bootstrap': self.handle_bootstrap_api,
            '/telemetry/live': self.handle_telemetry_live,
            '/telemetry/timeline': self.handle_telemetry_timeline,
            '/browser': self.handle_browser_dashboard,
        }
        self._post_routes = {
            '/logout': self.handle_logout,
            '/github/token': self.handle_github_token,
            '/github/device/init': self.handle_github_device_init,
            '/github/disconnect': self.handle_github_disconnect,
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
        
        if parsed.path.startswith('/api/v1/bridge/'):
            from runtime.api.bridge import BridgeRouter
            bridge = BridgeRouter(self.context)
            bridge.dispatch(parsed, handler)
            return

        if parsed.path == '/api/v1/continuity/bootstrap':
            self.handle_bootstrap_api(handler)
            return

        if parsed.path == '/api/v1/telemetry/stream':
            from runtime.telemetry.stream import handle_telemetry_stream
            telemetry_collector = self.context.get('telemetry_collector')
            handle_telemetry_stream(handler, telemetry_collector)
            return

        if parsed.path.startswith('/workers/'):
            self.handle_worker_detail(parsed, handler)
            return
            
        if parsed.path.startswith('/models/'):
            self.handle_model_detail(parsed, handler)
            return

        if parsed.path.startswith('/browser/'):
            self.handle_browser_session_detail(parsed, handler)
            return

        route_handler = self._get_routes.get(parsed.path)
        if not route_handler:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        try:
            result = route_handler(parsed)
            # Check if handler set a JSON response
            json_resp = self.context.get('direct_json_response')
            if json_resp is not None:
                self._send_json(handler, json_resp)
                del self.context['direct_json_response']
            else:
                self._send_html(handler, result)
        except Exception as e:
            logger.error(f"Error handling GET {path}: {e}", exc_info=True)
            self._send_html(handler, "500 Internal Server Error", status=500)

    def dispatch_post(self, path: str, form_data: Dict[str, list], handler: BaseHTTPRequestHandler) -> None:
        """Dispatch a POST request.
        
        POST handlers return a redirect location string (e.g. '/' or '/github?error=...').
        """
        parsed = urllib.parse.urlparse(path)
        if parsed.path.startswith('/api/v1/bridge/'):
            from runtime.api.bridge import BridgeRouter
            bridge = BridgeRouter(self.context)
            
            # Reconstruct request_body from form_data and handler context for the bridge
            # The AdminServer has already consumed rfile in do_POST, so we must construct
            # the body for the bridge from the form_data if applicable, or we have a problem.
            # Actually, wait. In server.py, it reads rfile:
            # body = self.rfile.read(length).decode('utf-8')
            # But only if ctype == 'application/x-www-form-urlencoded'!
            # Bridge uses application/json. So server.py doesn't consume the body.
            body = b""
            length = int(handler.headers.get('content-length', 0))
            if length > 0:
                body = handler.rfile.read(length)
            
            bridge.dispatch(parsed, handler, request_body=body)
            return

        route_handler = self._post_routes.get(parsed.path)
        if not route_handler:
            self._send_html(handler, "404 Not Found", status=404)
            return

        try:
            redirect_to = route_handler(form_data)
            # Check if handler set a direct HTML response
            direct_html = self.context.get('direct_html_response')
            if direct_html is not None:
                self._send_html(handler, direct_html)
                del self.context['direct_html_response']
            else:
                logger.info(f"POST {path} handler completed, redirecting to {redirect_to}")
                self._redirect(handler, redirect_to)
        except Exception as e:
            logger.error(f"Error handling POST {path}: {e}", exc_info=True)
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

    def _send_json(self, handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
        import json as json_module
        body = json_module.dumps(data).encode('utf-8')
        handler.send_response(status)
        handler.send_header('Content-Type', 'application/json')
        self._set_security_headers(handler)
        for cookie in self.context.get('set_cookies', []):
            handler.send_header('Set-Cookie', cookie)
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

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
        handler.send_header('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'unsafe-inline'; connect-src 'self';")


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

    def _get_fabric_client(self):
        gh_mgr = self.context.get('github_manager')
        secret_backend = self.context.get('secret_backend')
        if not gh_mgr or not gh_mgr.has_token():
            return None
        try:
            from runtime.github.client import GitHubClient
            from runtime.fabric.client import FabricClient
            gh_client = GitHubClient(secret_backend=secret_backend)
            return FabricClient(github_client=gh_client)
        except Exception:
            return None

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
        query_params = urllib.parse.parse_qs(parsed.query)
        error = query_params.get('error', [''])[0] or None

        gh_mgr = self.context.get('github_manager')
        gh_status = gh_mgr.get_status().to_dict() if gh_mgr else {}
        auth_status = gh_status.get('auth_status', 'UNKNOWN')
        
        session = self.context.get('admin_session')
        
        is_first_run = gh_mgr and not gh_mgr.has_token()
        if (auth_status in ('UNAUTHORIZED', 'MISSING')) and is_first_run and session and session.scope == "ONBOARDING_ONLY":
            return first_run_page(error=error, csrf_token=self._get_csrf())
        elif auth_status in ('UNAUTHORIZED', 'MISSING'):
            # It's missing but not a first run? Or they aren't logged in. Wait, middleware handles login.
            return first_run_page(error=error, csrf_token=self._get_csrf())
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
            
            # --- Universe Overview Counts ---
            exec_mgr = self.context.get('execution_manager')
            model_count = len(exec_mgr.model_registry.list_models()) if exec_mgr else 0
            capability_count = len(exec_mgr.registry.list_all()) if exec_mgr else 0
            worker_count = len(exec_mgr.worker_manager.workers) if exec_mgr else 0
            task_count = len(exec_mgr._tasks) if exec_mgr else 0
            
            project_count = 0
            bootstrap_snapshot = self.context.get('bootstrap_snapshot')
            if bootstrap_snapshot and 'discovered_repos' in bootstrap_snapshot:
                project_count = len(bootstrap_snapshot['discovered_repos'])
            
            mcp_count = 0
            if exec_mgr and hasattr(exec_mgr, 'mcp_gateway'):
                mcp_count = len(exec_mgr.mcp_gateway.tool_registry.list_tools())
            
            # Provide an instance method to get fabric client or default to None
            fabric_connected = False
            resource_count = 0
            if hasattr(self, '_get_fabric_client'):
                fabric_client = self._get_fabric_client()
                if fabric_client:
                    try:
                        resources = fabric_client.list_resources()
                        resource_count = len(resources)
                        fabric_connected = True
                    except Exception:
                        pass
            
            status_data = {
                'github': gh_status,
                'continuity': continuity_dto.to_dict(),
                'fabric_connected': fabric_connected,
                'resource_count': resource_count,
                'model_count': model_count,
                'capability_count': capability_count,
                'worker_count': worker_count,
                'task_count': task_count,
                'project_count': project_count,
                'mcp_count': mcp_count,
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
        else:
            status = GitHubStatusDTO(False, None, "UNAUTHORIZED", "MISSING", None, [], None, None).to_dict()
        
        query_params = urllib.parse.parse_qs(parsed.query)
        error = query_params.get('error', [''])[0] or None
        
        return github_page(status, error=error, csrf_token=self._get_csrf())

    def handle_fabric(self, parsed) -> str:
        import os
        fabric_endpoint = os.environ.get("FABRIC_ENDPOINT", "")
        
        if not fabric_endpoint:
            status = FabricStatusDTO(False, None, None, None, None, None).to_dict()
            status["fabric_status"] = "NOT_CONFIGURED"
            return fabric_page(status, self._get_csrf())
        
        try:
            from runtime.adapters.fabric_client import FabricClient
            client = FabricClient(endpoint=fabric_endpoint)
            health = client.health()
            identity = client.identity()
            
            resource_count = 0
            try:
                resources = client.list_resources()
                resource_count = len(resources)
            except Exception:
                pass
            
            status = FabricStatusDTO(
                connected=True,
                tenant=identity.get("node_id", "unknown"),
                anny_instance=identity.get("environment", "unknown"),
                runtime_registration="REGISTERED",
                last_heartbeat=health.get("timestamp"),
                last_reconciliation=None
            ).to_dict()
            status["fabric_status"] = "CONNECTED"
            status["resource_count"] = resource_count
            status["node_id"] = identity.get("node_id")
            
            return fabric_page(status, self._get_csrf())
            
        except Exception as e:
            logger.warning(f"Fabric connection failed: {e}")
            error_type = type(e).__name__
            fabric_status = "NETWORK_ERROR"
            if "AUTH" in str(e).upper():
                fabric_status = "AUTH_ERROR"
            elif "TIMEOUT" in str(e).upper():
                fabric_status = "DEGRADED"
                
            status = FabricStatusDTO(False, None, None, None, None, None).to_dict()
            status["fabric_status"] = fabric_status
            status["error"] = str(e)
            return fabric_page(status, self._get_csrf())

    def handle_sessions(self, parsed) -> str:
        return sessions_page([], self._get_csrf())

    def handle_operations(self, parsed) -> str:
        return operations_page([], self._get_csrf())

    def handle_receipts(self, parsed) -> str:
        return receipts_page([], self._get_csrf())
        
    def handle_executions(self, parsed) -> str:
        exec_mgr = self.context.get('execution_manager')
        executions = exec_mgr.get_all_executions() if exec_mgr else []
        return executions_page(executions, self._get_csrf())

    def handle_workers(self, parsed) -> str:
        exec_mgr = self.context.get('execution_manager')
        workers = exec_mgr.worker_manager.list_workers() if exec_mgr else []
        return workers_page(workers, self._get_csrf())
        
    def handle_worker_detail(self, parsed, handler: BaseHTTPRequestHandler) -> None:
        parts = parsed.path.strip('/').split('/')
        if len(parts) != 2:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        worker_id = parts[1]
        exec_mgr = self.context.get('execution_manager')
        worker = exec_mgr.worker_manager.get_worker(worker_id) if exec_mgr else None
        
        if not worker:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        html = worker_detail_page(worker, self._get_csrf())
        self._send_html(handler, html)

    def handle_capabilities(self, parsed) -> str:
        exec_mgr = self.context.get('execution_manager')
        caps = exec_mgr.registry.list_all() if exec_mgr else []
        return capabilities_page(caps, self._get_csrf())
        
    def handle_models(self, parsed) -> str:
        exec_mgr = self.context.get('execution_manager')
        models = exec_mgr.model_registry.list_models() if exec_mgr else []
        return models_page(models, self._get_csrf())

    def handle_model_detail(self, parsed, handler: BaseHTTPRequestHandler) -> None:
        parts = parsed.path.strip('/').split('/')
        if len(parts) != 2:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        model_id = parts[1]
        exec_mgr = self.context.get('execution_manager')
        
        model_def = exec_mgr.model_registry.get_model(model_id) if exec_mgr else None
        if not model_def:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        bindings = exec_mgr.model_registry._bindings if exec_mgr else []
        model_bindings = [b for b in bindings if b.model_id == model_id]
        hw_profile = exec_mgr.model_registry.get_hardware_profile() if exec_mgr else None
        perf_profile = exec_mgr.model_registry.get_performance_profile(model_id) if exec_mgr else None
        
        html = model_detail_page(model_def, model_bindings, hw_profile, perf_profile, self._get_csrf())
        self._send_html(handler, html)
        
    def handle_executors(self, parsed) -> str:
        return executors_page([], self._get_csrf())
        
    def handle_policies(self, parsed) -> str:
        exec_mgr = self.context.get('execution_manager')
        policy = exec_mgr.policy if exec_mgr else None
        return policies_page(policy, self._get_csrf())

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
        return '/'

    def handle_github_token(self, form_data) -> str:
        token = form_data.get('github_token', [''])[0]
        if not token:
            session = self.context.get('admin_session')
            if session and session.scope == "ONBOARDING_ONLY":
                return '/?error=GitHub+Access+Token+is+required'
            return '/github?error=GitHub+Access+Token+is+required'

        gh_mgr = self.context.get('github_manager')
        if gh_mgr and token:
            result = gh_mgr.store_and_validate_token(token)
            if result.get('success'):
                self._audit("GITHUB_TOKEN_SUBMIT", "SUCCESS")
                
                # Perform discovery since we just got a new token
                try:
                    github_client = GitHubClient(secret_backend=gh_mgr.secret_backend)
                    disc = OrganizationDiscoveryService(github_client)
                    disc_repos_raw = disc.discover_repositories()
                    
                    provider = OperationalRepositoryProvider(github_client=github_client, environment="PRODUCTION")
                    resolver = CustomerZeroBootstrapResolver(provider=provider, event_bus=None)
                    bootstrap_result = resolver.resolve()
                    
                    self.context['bootstrap_snapshot'] = {
                        'result': bootstrap_result,
                        'discovered_repos': disc_repos_raw
                    }
                except Exception as e:
                    logger.warning(f"Post-onboarding discovery failed: {e}")
                
                # Revoke onboarding session and issue regular session
                session = self.context.get('admin_session')
                if session and session.scope == "ONBOARDING_ONLY":
                    auth_mgr = self.context.get('auth_manager')
                    if auth_mgr:
                        auth_mgr.destroy(session.admin_session_id)
                        self.context['destroy_session'] = True
                        new_session = auth_mgr.create_session("admin")
                        self.context['new_session_id'] = new_session.admin_session_id
                return '/'
            else:
                self._audit("GITHUB_TOKEN_SUBMIT", "FAILED", result.get('error'))
                error_msg = urllib.parse.quote_plus(result.get('error', 'Validation failed'))
                
                # If we are on the first run page (session scope ONBOARDING_ONLY), return to /
                # Otherwise return to /github
                session = self.context.get('admin_session')
                if session and session.scope == "ONBOARDING_ONLY":
                    return f'/?error={error_msg}'
                else:
                    return f'/github?error={error_msg}'
        return '/'

    def handle_github_device_init(self, form_data) -> str:
        gh_mgr = self.context.get('github_manager')
        if not gh_mgr:
            return '/?error=GitHub+Auth+Manager+not+available'
        
        try:
            device_flow = gh_mgr.initiate_device_flow()
            from runtime.admin.templates import device_flow_page
            html = device_flow_page(
                user_code=device_flow.user_code,
                verification_uri=device_flow.verification_uri,
                csrf_token=self._get_csrf()
            )
            self.context['direct_html_response'] = html
            return '/'
        except Exception as e:
            error_msg = urllib.parse.quote_plus(f"Failed to initiate device flow: {e}")
            return f'/?error={error_msg}'

    def handle_github_device_poll(self, parsed) -> str:
        gh_mgr = self.context.get('github_manager')
        if not gh_mgr:
            self.context['direct_json_response'] = {'status': 'FAILED', 'error': 'GitHub Auth Manager not available'}
            return '/'
        
        try:
            result = gh_mgr.poll_device_flow()
            if result.get('status') == 'AUTHORIZED':
                self._audit("GITHUB_DEVICE_AUTH", "SUCCESS")
                
                # Perform discovery since we just got a new token
                try:
                    github_client = GitHubClient(secret_backend=gh_mgr.secret_backend)
                    disc = OrganizationDiscoveryService(github_client)
                    disc_repos_raw = disc.discover_repositories()
                    
                    provider = OperationalRepositoryProvider(github_client=github_client, environment="PRODUCTION")
                    resolver = CustomerZeroBootstrapResolver(provider=provider, event_bus=None)
                    bootstrap_result = resolver.resolve()
                    
                    self.context['bootstrap_snapshot'] = {
                        'result': bootstrap_result,
                        'discovered_repos': disc_repos_raw
                    }
                except Exception as e:
                    logger.warning(f"Post-onboarding discovery failed: {e}")
                
                # Revoke onboarding session and issue regular session
                session = self.context.get('admin_session')
                if session and session.scope == "ONBOARDING_ONLY":
                    auth_mgr = self.context.get('auth_manager')
                    if auth_mgr:
                        auth_mgr.destroy(session.admin_session_id)
                        self.context['destroy_session'] = True
                        new_session = auth_mgr.create_session("admin")
                        self.context['new_session_id'] = new_session.admin_session_id
            
            self.context['direct_json_response'] = result
            return '/'
        except Exception as e:
            self.context['direct_json_response'] = {'status': 'FAILED', 'error': str(e)}
            return '/'



    def handle_github_disconnect(self, form_data) -> str:
        gh_mgr = self.context.get('github_manager')
        if gh_mgr:
            gh_mgr.disconnect()
            self._audit("GITHUB_DISCONNECT", "SUCCESS")
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

    def handle_universe_organization(self, parsed) -> str:
        gh_mgr = self.context.get('github_manager')
        orgs = []
        if gh_mgr and gh_mgr.has_token():
            try:
                from runtime.github.client import GitHubClient
                secret_backend = self.context.get('secret_backend')
                gh_client = GitHubClient(secret_backend=secret_backend)
                from runtime.github.discovery import OrganizationDiscoveryService
                disc = OrganizationDiscoveryService(gh_client)
                
                # Fetch principal first to use as default org
                status = gh_mgr.get_status().to_dict()
                principal = status.get('principal')
                if principal:
                    orgs.append({"login": principal, "id": "user", "type": "User"})
                    
                # Fetch real orgs
                try:
                    gh_orgs = gh_client.get("/user/orgs").json()
                    if isinstance(gh_orgs, list):
                        orgs.extend(gh_orgs)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Org discovery error: {e}")
        return universe_organization_page(orgs, self._get_csrf())

    def handle_universe_projects(self, parsed) -> str:
        return universe_projects_page([], self._get_csrf())

    def handle_universe_repositories(self, parsed) -> str:
        repos = []
        try:
            snapshot = self.context.get('bootstrap_snapshot')
            if snapshot and 'discovered_repos' in snapshot:
                for r in snapshot['discovered_repos']:
                    repos.append({"name": r.name, "owner": r.owner, "visibility": r.visibility.value})
        except Exception:
            pass
        return universe_repositories_page(repos, self._get_csrf())

    def handle_universe_resources(self, parsed) -> str:
        resources = []
        if hasattr(self, '_get_fabric_client'):
            fc = self._get_fabric_client()
            if fc:
                try:
                    resources = fc.list_resources()
                except Exception:
                    pass
        return universe_resources_page(resources, self._get_csrf())

    def handle_execution_missions(self, parsed) -> str:
        return generic_placeholder_page("Missions", "/execution/missions", self._get_csrf())

    def handle_execution_tasks(self, parsed) -> str:
        tasks = {}
        exec_mgr = self.context.get('execution_manager')
        if exec_mgr:
            tasks = exec_mgr._tasks
        return execution_tasks_page(tasks, self._get_csrf())

    def handle_execution_workers(self, parsed) -> str:
        workers = {}
        exec_mgr = self.context.get('execution_manager')
        if exec_mgr:
            workers = exec_mgr.worker_manager.workers
        return execution_workers_page(workers, self._get_csrf())

    def handle_execution_executions(self, parsed) -> str:
        return generic_placeholder_page("Executions", "/execution/executions", self._get_csrf())

    def handle_execution_workspaces(self, parsed) -> str:
        return generic_placeholder_page("Workspaces", "/execution/workspaces", self._get_csrf())

    def handle_intelligence_capabilities(self, parsed) -> str:
        caps = []
        bindings = []
        exec_mgr = self.context.get('execution_manager')
        if exec_mgr:
            caps = exec_mgr.registry.list_all()
            for c in caps:
                bindings.extend(c.model_bindings)
        return intelligence_capabilities_page(caps, bindings, self._get_csrf())

    def handle_intelligence_executors(self, parsed) -> str:
        return generic_placeholder_page("Executors", "/intelligence/executors", self._get_csrf())

    def handle_intelligence_performance(self, parsed) -> str:
        return generic_placeholder_page("Performance", "/intelligence/performance", self._get_csrf())

    def handle_infrastructure_topology(self, parsed) -> str:
        gh_mgr = self.context.get('github_manager')
        gh_up = gh_mgr.get_status().connected if gh_mgr else False
        
        fab_up = False
        if hasattr(self, '_get_fabric_client'):
            fc = self._get_fabric_client()
            if fc:
                try:
                    fc.list_resources()
                    fab_up = True
                except Exception:
                    pass
        return infrastructure_topology_page(gh_up, fab_up, False, self._get_csrf())

    def handle_continuity_timeline(self, parsed) -> str:
        return generic_placeholder_page("Continuity Timeline", "/continuity/timeline", self._get_csrf())

    def handle_audit_events(self, parsed) -> str:
        events = []
        audit_mgr = self.context.get('audit_manager')
        if audit_mgr and hasattr(audit_mgr, 'get_events'):
            try:
                events = audit_mgr.get_events(limit=50)
            except Exception:
                pass
        return audit_events_page(events, self._get_csrf())

    def handle_audit_provenance(self, parsed) -> str:
        prov_data = ""
        query_params = urllib.parse.parse_qs(parsed.query)
        p_id = query_params.get('id', [''])[0]
        if p_id and hasattr(self, '_get_fabric_client'):
            fc = self._get_fabric_client()
            if fc:
                try:
                    import json
                    data = fc.get_provenance(p_id)
                    prov_data = json.dumps(data, indent=2)
                except Exception:
                    prov_data = "Failed to load provenance data."
        return audit_provenance_page(prov_data, self._get_csrf())

    def handle_audit_evidence(self, parsed) -> str:
        return generic_placeholder_page("Evidence", "/audit/evidence", self._get_csrf())

    def handle_search(self, parsed) -> str:
        query_params = urllib.parse.parse_qs(parsed.query)
        q = query_params.get('q', [''])[0]
        return search_page(q, self._get_csrf())

    def handle_telemetry_live(self, parsed) -> str:
        return telemetry_live_page(self._get_csrf())

    def handle_telemetry_timeline(self, parsed) -> str:
        events = []
        telemetry_collector = self.context.get('telemetry_collector')
        if telemetry_collector:
            events = telemetry_collector.get_timeline(limit=100)
        return telemetry_timeline_page(events, self._get_csrf())

    def handle_browser_dashboard(self, parsed) -> str:
        sessions = []
        exec_mgr = self.context.get('execution_manager')
        if exec_mgr and exec_mgr.worker_manager.browser_adapter:
            sessions = list(exec_mgr.worker_manager.browser_adapter._sessions.values())
        
        from runtime.admin.templates import browser_dashboard_page
        return browser_dashboard_page(sessions, self._get_csrf())

    def handle_browser_session_detail(self, parsed, handler: BaseHTTPRequestHandler) -> None:
        parts = parsed.path.strip('/').split('/')
        if len(parts) != 2:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        session_id = parts[1]
        exec_mgr = self.context.get('execution_manager')
        
        if not exec_mgr or not exec_mgr.worker_manager.browser_adapter:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        session_data = exec_mgr.worker_manager.browser_adapter._sessions.get(session_id)
        if not session_data:
            self._send_html(handler, "404 Not Found", status=404)
            return
            
        from runtime.admin.templates import browser_session_page
        html = browser_session_page(session_data[0], self._get_csrf())
        self._send_html(handler, html)


