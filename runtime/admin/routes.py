"""Routing and route handlers for the ANNY Runtime admin panel."""
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Callable, Dict, Any, Optional

import json
from runtime.admin.templates import (
    first_run_page, reconnect_page, failure_page, ready_page, github_page, fabric_page,
    fabric_setup_page, sessions_page, operations_page, receipts_page, doctor_page, executions_page,
    capabilities_page, executors_page, policies_page, workers_page, worker_detail_page,
    models_page, model_detail_page,
    universe_accounts_page, universe_account_detail_page,
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
from runtime.core.version import __version__
from runtime.bootstrap.conrrad import (
    not_configured_dependency_matrix,
    REQUIRED_CONRRAD_SERVICES,
    registry_is_complete,
)

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
            '/universe/accounts': self.handle_universe_accounts,
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
            '/api/status': self.handle_api_status,
            '/api/v1/continuity/bootstrap': self.handle_bootstrap_api,
            '/telemetry/live': self.handle_telemetry_live,
            '/telemetry/timeline': self.handle_telemetry_timeline,
            '/api/processing/matrix': self.handle_processing_matrix,
            '/api/processing/events': self.handle_processing_events,
            '/browser': self.handle_browser_dashboard,
        }
        self._post_routes = {
            '/logout': self.handle_logout,
            '/github/token': self.handle_github_token,
            '/github/device/init': self.handle_github_device_init,
            '/github/disconnect': self.handle_github_disconnect,
            '/fabric/setup': self.handle_fabric_setup,
            '/admin/restart': self.handle_admin_restart,
            '/admin/diagnostics': self.handle_admin_diagnostics,
            '/admin/update-check': self.handle_admin_update_check,
            '/api/bootstrap/verify': self.handle_verify_bootstrap,
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

        if parsed.path == '/health/live':
            self._send_json(handler, {"status": "alive"})
            return

        if parsed.path == '/health/ready':
            engine = self.context.get('runtime_engine')
            if not engine:
                self._send_json(handler, {"status": "not_ready", "reason": "No runtime engine"}, status=503)
                return
            state_name = getattr(engine.state, 'name', str(engine.state))
            report = getattr(engine, 'bootstrap_report', None)
            anny_ready = getattr(report, 'anny_ready', False) if report else False

            if anny_ready and state_name in ('READY', 'WAITING_FOR_SESSION'):
                self._send_json(handler, {"status": "ready"})
            else:
                self._send_json(handler, {"status": "not_ready", "reason": f"State={state_name}, ready={anny_ready}"}, status=503)
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

        if parsed.path.startswith('/universe/accounts/') and len(parsed.path) > len('/universe/accounts/'):
            html = self.handle_universe_account_detail(parsed)
            self._send_html(handler, html)
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
            # Check if handler set a direct HTML or JSON response
            direct_html = self.context.get('direct_html_response')
            direct_json = self.context.get('direct_json_response')
            if direct_json is not None:
                self._send_json(handler, direct_json)
                del self.context['direct_json_response']
            elif direct_html is not None:
                self._send_html(handler, direct_html)
                del self.context['direct_html_response']
            else:
                logger.info(f"POST {path} handler completed, redirecting to {redirect_to}")
                self._redirect(handler, redirect_to)
        except Exception as e:
            logger.error(f"Error handling POST {path}: {e}", exc_info=True)
            self._send_html(handler, "500 Internal Server Error", status=500)

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

    def _send_html(self, handler: BaseHTTPRequestHandler, html: str, status: int = 200) -> None:
        body = html.encode('utf-8')
        handler.send_response(status)
        handler.send_header('Content-Type', 'text/html; charset=utf-8')
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

    def handle_processing_matrix(self, parsed) -> str:
        aggregator = self.context.get('telemetry_aggregator')
        if not aggregator:
            self.context['direct_json_response'] = {"error": "Aggregator unavailable"}
            return '/'
        
        query_params = urllib.parse.parse_qs(parsed.query)
        filters = {k: v[0] for k, v in query_params.items()}
        matrix = aggregator.get_matrix(filters)
        self.context['direct_json_response'] = matrix
        return '/'

    def handle_processing_events(self, parsed) -> str:
        aggregator = self.context.get('telemetry_aggregator')
        if not aggregator:
            self.context['direct_json_response'] = {"error": "Aggregator unavailable"}
            return '/'
            
        query_params = urllib.parse.parse_qs(parsed.query)
        filters = {k: v[0] for k, v in query_params.items() if k != 'limit'}
        limit = int(query_params.get('limit', ['100'])[0])
        events = aggregator.get_events(filters, limit=limit)
        self.context['direct_json_response'] = events
        return '/'

    def handle_api_status(self, parsed) -> str:
        """Returns the live status of the runtime and bootstrap sequence."""
        engine = self.context.get('runtime_engine')
        if not engine:
            self.context['direct_json_response'] = {
                "anny_ready": False,
                "runtime_state": "STOPPED",
                "error": "No runtime engine"
            }
            return '/'

        state_name = getattr(engine.state, 'name', str(engine.state))
        
        # Fabric
        fabric_org = getattr(engine.config, 'fabric_org', None) if engine.config else None
        fabric_repo = getattr(engine.config, 'fabric_repo', None) if engine.config else None
        
        # GitHub
        gh_mgr = self.context.get('github_manager')
        gh_status = gh_mgr.get_status().auth_status if gh_mgr else "UNAUTHORIZED"
        
        # Identity/Health
        auth_mgr = self.context.get('auth_manager')
        runtime_id = getattr(auth_mgr, 'runtime_id', "UNKNOWN") if auth_mgr else "UNKNOWN"
        
        report = getattr(engine, 'bootstrap_report', None)
        anny_ready = getattr(report, 'anny_ready', False) if report else False
        
        if state_name in ('ERROR', 'STOPPED'):
            runtime_health = "NOT_HEALTHY"
        elif state_name in ('STARTING', 'VERIFYING', 'ADMIN_MODE', 'DRAINING'):
            runtime_health = "DEGRADED"
        elif state_name in ('READY', 'WAITING_FOR_SESSION'):
            runtime_health = "HEALTHY" if anny_ready else "DEGRADED"
        else:
            runtime_health = "UNKNOWN"
        
        report = getattr(engine, 'bootstrap_report', None)
        gates_list = []
        fabric_node = "UNKNOWN"
        timestamp = None
        dependencies = not_configured_dependency_matrix("No authoritative CONRRAD dependency registry has been observed")
        bootstrap_state = "UNKNOWN"
        if report:
            fabric_node = getattr(report, 'fabric_node', "UNKNOWN")
            timestamp = getattr(report, 'timestamp', None)
            observed_dependencies = getattr(report, 'conrrad_dependencies', None)
            if isinstance(observed_dependencies, list) and observed_dependencies:
                dependencies = observed_dependencies
            observed_bootstrap_state = getattr(report, 'bootstrap_state', "UNKNOWN")
            if isinstance(observed_bootstrap_state, str):
                bootstrap_state = observed_bootstrap_state
            
            for g in getattr(report, 'gates', []):
                name = getattr(g.gate, 'name', str(g.gate)) if hasattr(g, 'gate') else 'UNKNOWN'
                passed = getattr(g, 'passed', False)
                evidence = getattr(g, 'evidence', '')
                status_str = "PASS" if passed else ("BLOCKED" if evidence == 'STUB' else "FAIL")
                
                gates_list.append({
                    "phase": name.split('_')[0] if '_' in name else 'CORE',
                    "gate": name,
                    "status": status_str,
                    "detail": getattr(g, 'detail', ''),
                    "evidence": evidence
                })
            
        def _report_status(attribute: str, allowed: set) -> str:
            value = getattr(report, attribute, None) if report else None
            if isinstance(value, str) and value in allowed and value != "UNKNOWN":
                return value
            return "BLOCKED" if bootstrap_state == "BLOCKED" else "UNKNOWN"

        def _report_value(attribute: str) -> str:
            value = getattr(report, attribute, None) if report else None
            return value if isinstance(value, str) and value else "UNKNOWN"

        def _inventory(attribute: str):
            inventory = getattr(report, attribute, None) if report else None
            declared = getattr(inventory, 'declared', None)
            return declared if isinstance(declared, list) and declared else "UNKNOWN"

        repository_fabric = next(
            (item for item in dependencies if item.get("service_name") == "CONRRAD.REPOSITORY_FABRIC"),
            None,
        )
        fabric_status = repository_fabric.get("online_status", "UNKNOWN") if repository_fabric else "UNKNOWN"
        admission_status = _report_status("admission_status", {"ADMITTED", "BLOCKED", "UNKNOWN"})
        reconciliation_status = _report_status("reconciliation_status", {"COHERENT", "INCOHERENT", "BLOCKED", "UNKNOWN"})
        conrrad_complete = registry_is_complete(dependencies)
        conrrad_online_verified_count = sum(
            1 for item in dependencies
            if item.get("online_status") == "ONLINE_VERIFIED"
        )
        conrrad_trust_verified_count = sum(
            1 for item in dependencies
            if item.get("trust_status") == "VERIFIED"
        )

        data = {
            "anny_ready": anny_ready,
            "bootstrap_state": bootstrap_state,
            "runtime_state": state_name,
            "runtime_health": runtime_health,
            "github_status": gh_status,
            "fabric_status": fabric_status,
            "conrrad_gate_status": "ONLINE_VERIFIED" if conrrad_complete else "BLOCKED",
            "conrrad_required_service_count": len(REQUIRED_CONRRAD_SERVICES),
            "conrrad_observed_service_count": len({
                item.get("service_name")
                for item in dependencies
                if item.get("service_name")
            }),
            "conrrad_online_verified_count": conrrad_online_verified_count,
            "conrrad_trust_verified_count": conrrad_trust_verified_count,
            "admission_status": admission_status,
            "reconciliation_status": reconciliation_status,
            "timestamp": timestamp,
            
            "runtime_id": runtime_id,
            "runtime_version": __version__,
            # GitHub authentication does not establish an organization identity.
            "github_org": "UNKNOWN",
            "fabric_org": fabric_org,
            "fabric_repo": fabric_repo,
            "fabric_node": fabric_node,
            "tenant": "UNKNOWN",
            "policy_revision": _report_value("policy_revision"),
            "contract_revision": "UNKNOWN",
            
            "gates": gates_list,
            "capabilities": _inventory("capabilities"),
            "health": {"engine": state_name, "github": gh_status, "conrrad_dependencies": dependencies},
            "conrrad_dependencies": dependencies,
            "access": "UNKNOWN",
            "tools": _inventory("tools"),
            "models": _inventory("models"),
            "workers": _inventory("workers"),
            "connectors": _inventory("connectors"),
            "continuity": {
                "mission": "UNKNOWN",
                "task": "UNKNOWN",
                "step": "UNKNOWN",
                "action": "UNKNOWN",
                "blockers": "BLOCKED" if bootstrap_state == "BLOCKED" else "UNKNOWN",
                "status": "BLOCKED" if bootstrap_state == "BLOCKED" else "UNKNOWN",
            }
        }
        
        self.context['direct_json_response'] = data
        return '/'


    def _get_fabric_client(self):
        """Build a GitHubFabricAdapter using dynamic config — not hardcoded constants."""
        gh_mgr = self.context.get('github_manager')
        secret_backend = self.context.get('secret_backend')
        if not gh_mgr or not gh_mgr.has_token():