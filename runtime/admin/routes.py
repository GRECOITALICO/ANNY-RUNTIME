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
from runtime.admin.projections import DEFAULT_PROJECTION_REGISTRY, VALID_PRIORITIES
from runtime.bootstrap.conrrad import project_dependency_matrix, registry_is_complete, REQUIRED_CONRRAD_SERVICES

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
            '/api/control-center/projections': self.handle_control_center_projections,
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
        handler.send_header('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline'; font-src 'self'; script-src 'unsafe-inline'; connect-src 'self';")


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

    def handle_control_center_projections(self, parsed) -> str:
        """Return the canonical, read-only Control Center projection registry."""
        query = urllib.parse.parse_qs(parsed.query)
        priority = query.get('priority', [None])[0]
        section = query.get('section', [None])[0]
        implementation_status = query.get('implementation_status', [None])[0]
        truth_class = query.get('truth_class', [None])[0]
        freshness = query.get('freshness', [None])[0]
        tag = query.get('tag', [None])[0]
        q = query.get('q', [None])[0]
        projection_id = query.get('projection_id', [None])[0]

        def _int_query(name, default):
            raw = query.get(name, [None])[0]
            if raw in (None, ''):
                return default
            try:
                return int(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{name} must be an integer")

        try:
            limit = _int_query('limit', 100)
            offset = _int_query('offset', 0)
            if priority and priority not in VALID_PRIORITIES:
                raise ValueError("invalid priority")
            payload = DEFAULT_PROJECTION_REGISTRY.to_api_dict(
                priority=priority,
                section=section,
                implementation_status=implementation_status,
                truth_class=truth_class,
                freshness=freshness,
                tag=tag,
                q=q,
                projection_id=projection_id,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            if priority and priority not in VALID_PRIORITIES:
                self.context['direct_json_response'] = {
                    "error": "INVALID_PRIORITY",
                    "status": "BLOCKED",
                }
            else:
                self.context['direct_json_response'] = {
                    "error": "INVALID_PROJECTION_QUERY",
                    "status": "BLOCKED",
                    "detail": str(exc),
                }
            return '/'
        self.context['direct_json_response'] = payload
        return '/'


    def handle_api_status(self, parsed) -> str:
        """Project Runtime status without manufacturing external authority."""
        engine = self.context.get('runtime_engine')
        if not engine:
            self.context['direct_json_response'] = {
                "anny_ready": False, "bootstrap_state": "BLOCKED", "runtime_state": "STOPPED",
                "runtime_health": "NOT_HEALTHY", "github_status": "UNAUTHORIZED",
                "fabric_status": "NOT_CONFIGURED", "conrrad_gate_status": "BLOCKED",
                "conrrad_required_service_count": len(REQUIRED_CONRRAD_SERVICES),
                "conrrad_observed_service_count": 0, "conrrad_online_verified_count": 0,
                "conrrad_trust_verified_count": 0, "conrrad_dependencies": project_dependency_matrix(None),
                "admission_status": "BLOCKED", "reconciliation_status": "BLOCKED",
                "timestamp": None, "runtime_id": "UNKNOWN", "runtime_version": __version__,
                "github_org": "UNKNOWN", "fabric_org": None, "fabric_repo": None,
                "fabric_node": "UNKNOWN", "tenant": "UNKNOWN", "policy_revision": "UNKNOWN",
                "contract_revision": "UNKNOWN", "gates": [], "capabilities": "UNKNOWN",
                "health": {"engine": "STOPPED", "github": "UNAUTHORIZED"},
                "access": "UNKNOWN", "tools": "UNKNOWN", "models": "UNKNOWN",
                "workers": "UNKNOWN", "connectors": "UNKNOWN",
                "continuity": {"mission": "UNKNOWN", "task": "UNKNOWN", "step": "UNKNOWN",
                               "action": "UNKNOWN", "blockers": "BLOCKED", "status": "BLOCKED"},
                "error": "No runtime engine",
            }
            return '/'

        state_name = getattr(getattr(engine, 'state', None), 'name', str(getattr(engine, 'state', 'UNKNOWN')))
        config = getattr(engine, 'config', None)
        gh_mgr = self.context.get('github_manager')
        try:
            gh_status = gh_mgr.get_status().auth_status if gh_mgr else 'UNAUTHORIZED'
        except Exception:
            gh_status = 'UNKNOWN'
        auth_mgr = self.context.get('auth_manager')
        runtime_id = getattr(auth_mgr, 'runtime_id', 'UNKNOWN') if auth_mgr else 'UNKNOWN'
        report = getattr(engine, 'bootstrap_report', None)
        dependency_matrix = project_dependency_matrix(report)
        conrrad_complete = registry_is_complete(dependency_matrix)
        conrrad_observed = sum(1 for item in dependency_matrix
                               if str(item.get("online_status", "UNKNOWN")).upper() != "NOT_CONFIGURED")
        online_verified = sum(1 for item in dependency_matrix
                              if str(item.get("online_status", "UNKNOWN")).upper() == "ONLINE_VERIFIED")
        trust_verified = sum(1 for item in dependency_matrix
                            if str(item.get("trust_status", "UNKNOWN")).upper() == "VERIFIED")
        reported_ready = bool(getattr(report, 'anny_ready', False)) if report else False
        bootstrap_state = getattr(report, 'bootstrap_state', 'UNKNOWN') if report else 'UNKNOWN'
        if bootstrap_state not in {'READY', 'BLOCKED', 'UNKNOWN'}:
            bootstrap_state = 'UNKNOWN'
        anny_ready = reported_ready and bootstrap_state == 'READY' and conrrad_complete

        health_status = 'UNKNOWN'
        health_check = getattr(engine, 'health_check', None)
        if callable(health_check):
            try:
                observed_health = health_check()
                health_status = str(observed_health.get('status', 'UNKNOWN')).upper()
            except Exception:
                health_status = 'UNKNOWN'
        if state_name in ('ERROR', 'STOPPED'):
            runtime_health = 'NOT_HEALTHY'
        elif health_status == 'OK':
            runtime_health = 'HEALTHY' if anny_ready else 'DEGRADED'
        elif state_name in ('STARTING', 'VERIFYING', 'ADMIN_MODE', 'DRAINING'):
            runtime_health = 'DEGRADED'
        elif state_name in ('READY', 'WAITING_FOR_SESSION'):
            runtime_health = 'HEALTHY' if anny_ready else 'DEGRADED'
        else:
            runtime_health = 'UNKNOWN'

        gates_list = []
        timestamp = None
        fabric_node = 'UNKNOWN'
        if report:
            fabric_node = getattr(report, 'fabric_node', 'UNKNOWN') or 'UNKNOWN'
            timestamp = getattr(report, 'completed_at', None) or getattr(report, 'started_at', None)
            for gate_result in getattr(report, 'gates', []):
                gate_obj = getattr(gate_result, 'gate', None)
                name = getattr(gate_obj, 'name', str(gate_obj)) if gate_obj is not None else 'UNKNOWN'
                passed = bool(getattr(gate_result, 'passed', False))
                evidence = getattr(gate_result, 'evidence', '')
                status_str = 'PASS' if passed else ('BLOCKED' if evidence == 'STUB' else 'FAIL')
                gates_list.append({'phase': name.split('_')[0] if '_' in name else 'CORE',
                                   'gate': name, 'status': status_str,
                                   'detail': getattr(gate_result, 'detail', ''), 'evidence': evidence})

        def _report_status(attribute: str, allowed: set[str]) -> str:
            value = getattr(report, attribute, None) if report else None
            if isinstance(value, str) and value in allowed and value != 'UNKNOWN':
                return value
            return 'BLOCKED' if bootstrap_state == 'BLOCKED' else 'UNKNOWN'

        def _inventory(attribute: str):
            inventory = getattr(report, attribute, None) if report else None
            declared = getattr(inventory, 'declared', None)
            return declared if isinstance(declared, list) and declared else 'UNKNOWN'

        repository_fabric = next((item for item in dependency_matrix
                                 if item.get("service_name") == "CONRRAD.REPOSITORY_FABRIC"), None)
        fabric_status = str(repository_fabric.get('online_status', 'UNKNOWN')) if repository_fabric else 'UNKNOWN'

        data = {
            'anny_ready': anny_ready, 'bootstrap_state': bootstrap_state,
            'runtime_state': state_name, 'runtime_health': runtime_health,
            'github_status': gh_status, 'fabric_status': fabric_status,
            'conrrad_gate_status': 'ONLINE_VERIFIED' if conrrad_complete else 'BLOCKED',
            'conrrad_required_service_count': len(REQUIRED_CONRRAD_SERVICES),
            'conrrad_observed_service_count': conrrad_observed,
            'conrrad_online_verified_count': online_verified,
            'conrrad_trust_verified_count': trust_verified,
            'conrrad_dependencies': dependency_matrix,
            'admission_status': _report_status('admission_status', {'ADMITTED', 'BLOCKED', 'UNKNOWN'}),
            'reconciliation_status': _report_status('reconciliation_status', {'COHERENT', 'INCOHERENT', 'BLOCKED', 'UNKNOWN'}),
            'timestamp': timestamp,
            'runtime_id': runtime_id, 'runtime_version': __version__, 'github_org': 'UNKNOWN',
            'fabric_org': getattr(config, 'fabric_org', None) if config else None,
            'fabric_repo': getattr(config, 'fabric_repo', None) if config else None,
            'fabric_node': fabric_node, 'tenant': 'UNKNOWN',
            'policy_revision': getattr(report, 'policy_revision', 'UNKNOWN') if report else 'UNKNOWN',
            'contract_revision': 'UNKNOWN', 'gates': gates_list,
            'capabilities': _inventory('capabilities'),
            'health': {'engine': state_name, 'runtime': runtime_health, 'github': gh_status,
                       'conrrad_dependencies': dependency_matrix},
            'access': 'UNKNOWN', 'tools': _inventory('tools'), 'models': _inventory('models'),
            'workers': _inventory('workers'), 'connectors': _inventory('connectors'),
            'continuity': {'mission': 'UNKNOWN', 'task': 'UNKNOWN', 'step': 'UNKNOWN',
                           'action': 'UNKNOWN',
                           'blockers': 'BLOCKED' if bootstrap_state == 'BLOCKED' else 'UNKNOWN',
                           'status': 'BLOCKED' if bootstrap_state == 'BLOCKED' else 'UNKNOWN'},
        }
        self.context['direct_json_response'] = data
        return '/'

    def _get_fabric_client(self):
        """Build a GitHubFabricAdapter using dynamic config — not hardcoded constants."""
        gh_mgr = self.context.get('github_manager')
        secret_backend = self.context.get('secret_backend')
        if not gh_mgr or not gh_mgr.has_token():
            return None
        try:
            from runtime.github.client import GitHubClient
            from runtime.fabric.github_adapter import GitHubFabricAdapter
            gh_client = GitHubClient(secret_backend=secret_backend)
            engine = self.context.get('runtime_engine')
            config = engine.config if engine else None
            return GitHubFabricAdapter(github_client=gh_client, config=config)
        except Exception as e:
            logger.warning(f"Could not create GitHubFabricAdapter: {e}")
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

        # Determine runtime status from observable state
        runtime_engine = self.context.get('runtime_engine')
        rt_status = "UNKNOWN"
        if runtime_engine and hasattr(runtime_engine, 'get_health_status'):
            rt_status = runtime_engine.get_health_status()

        repo_dtos = [RepositoryDTO(full_name=r.full_name, name=r.name, owner=r.owner, visibility=r.visibility, archived=r.archived, default_branch=r.default_branch) for r in disc_repos_raw]

        # Adapt result to ContinuityDTO — two possible result types may be present:
        #   1. runtime.bootstrap.report.BootstrapReport  (ThreePlaneBootstrap output)
        #   2. runtime.continuity.state.BootstrapResult  (CustomerZeroBootstrapResolver output)
        from runtime.bootstrap.report import BootstrapReport as ThreePlaneReport
        if isinstance(result, ThreePlaneReport):
            # Three-plane bootstrap result
            status_val = "READY" if result.anny_ready else "BLOCKED"
            recon_status = "COHERENT" if result.anny_ready else "INCOHERENT"
            fabric_node = result.fabric_node

            engine = self.context.get('runtime_engine')
            config = getattr(engine, 'config', None) if engine else None
            fabric_org = getattr(config, 'fabric_org', None) if config else None
            fabric_repo = getattr(config, 'fabric_repo', None) if config else None
            canonical_src = f"{fabric_org}/{fabric_repo}" if (fabric_org and fabric_repo) else "NOT_CONFIGURED"
            current_mission = None
            next_action = None
            blockers = []
        elif hasattr(result, 'status') and hasattr(result, 'canonical_state') and not hasattr(result, 'anny_ready'):
            # Continuity BootstrapResult (runtime.continuity.state.BootstrapResult)
            from runtime.continuity.state import ContinuityStatus
            cs = result.status
            if cs == ContinuityStatus.CONSISTENT:
                status_val = "CONSISTENT"
                recon_status = "COHERENT"
            elif cs == ContinuityStatus.BLOCKED:
                status_val = "BLOCKED"
                recon_status = "INCOHERENT"
            elif isinstance(cs, str):
                status_val = cs
                recon_status = "COHERENT" if cs == "CONSISTENT" else "UNKNOWN"
            else:
                status_val = getattr(cs, 'value', str(cs))
                recon_status = "UNKNOWN"
            fabric_node = None
            canonical_src = "NOT_CONFIGURED"
            canonical_state = result.canonical_state
            current_mission = None
            next_action = None
            if canonical_state:
                cm = canonical_state.current_mission
                current_mission = cm.id if cm else None
                na = canonical_state.next_action
                next_action = na.action if na else None
            blockers = [
                {"id": getattr(b, 'id', ''), "description": getattr(b, 'description', '')}
                for b in getattr(result, 'blockers', [])
            ]
        else:
            # Unknown/mock result type — safe defaults
            anny_ready = getattr(result, 'anny_ready', False)
            status_val = "READY" if anny_ready else "BLOCKED"
            recon_status = "COHERENT" if anny_ready else "INCOHERENT"
            fabric_node = getattr(result, 'fabric_node', None)
            canonical_src = "NOT_CONFIGURED"
            current_mission = None
            next_action = None
            blockers = []

        engine = self.context.get('runtime_engine')
        config = getattr(engine, 'config', None) if engine else None
        fabric_org = getattr(config, 'fabric_org', None) if config else None
        fabric_repo = getattr(config, 'fabric_repo', None) if config else None
        if fabric_org and fabric_repo and canonical_src == "NOT_CONFIGURED":
            canonical_src = f"{fabric_org}/{fabric_repo}"

        return ContinuityDTO(
            status=status_val,
            canonical_source=canonical_src,
            canonical_revision=None,
            current_mission=current_mission,
            current_task=None,
            next_action=next_action,
            blocker_count=len(blockers),
            reconciliation_status=recon_status,
            github_status=gh_status_str,
            runtime_status=rt_status,
            fabric_status="CONNECTED" if fabric_node else "NOT_CONFIGURED",
            organizations=[],
            repositories=repo_dtos,
            blockers=[],
            l2_worker_summary=L2WorkerSummaryDTO(count=0, registered_workers=[])
        )

    # --- GET Handlers ---

    def handle_dashboard(self, parsed) -> str:
        gh_mgr = self.context.get('github_manager')
        session = self.context.get('admin_session')
        is_first_run = gh_mgr and not gh_mgr.has_token()
        
        query_params = urllib.parse.parse_qs(parsed.query)
        error = query_params.get('error', [''])[0] or None

        if is_first_run or (session and getattr(session, 'scope', '') == "ONBOARDING_ONLY"):
            from runtime.admin.templates import first_run_page
            device_flow_available = bool(getattr(gh_mgr, 'client_id', ''))
            return first_run_page(
                csrf_token=self._get_csrf(),
                error=error,
                device_flow_available=device_flow_available,
            )

        try:
            from runtime.admin.templates_cc import control_center_page
            return control_center_page(self._get_csrf())
        except ImportError:
            # Fallback if templates_cc.py is missing
            return "<html><body><h1>ANNY CONTROL CENTER (Loading...)</h1></body></html>"


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
        """Report live Repository Fabric status through the canonical config-driven adapter."""
        status = FabricStatusDTO(False, None, None, None, None, None).to_dict()
        fabric_client = self._get_fabric_client()
        if fabric_client is None:
            status["fabric_status"] = "NOT_CONFIGURED"
            return fabric_page(status, self._get_csrf())

        try:
            health = fabric_client.probe_health()
            status["fabric_status"] = "CONNECTED" if health.reachable else "DEGRADED"
            status["node_id"] = health.node_id
            status["latency_ms"] = health.latency_ms

            if health.reachable:
                try:
                    node = fabric_client.read_node_config()
                    status["node_id"] = node.node_id
                    status["runtime_registration"] = "REGISTERED"
                except Exception:
                    status["runtime_registration"] = "UNKNOWN"

            return fabric_page(status, self._get_csrf())
        except Exception as exc:
            logger.warning("Repository Fabric status check failed: %s", type(exc).__name__)
            status["fabric_status"] = "ERROR"
            status["error"] = type(exc).__name__
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
                    
                    engine = self.context.get('runtime_engine')
                    if engine:
                        engine.startup(github_client=github_client, fabric_client=self._get_fabric_client())
                        self.context['bootstrap_snapshot'] = {
                            'result': engine.bootstrap_report,
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
                    
                    engine = self.context.get('runtime_engine')
                    if engine:
                        engine.startup(github_client=github_client, fabric_client=self._get_fabric_client())
                        self.context['bootstrap_snapshot'] = {
                            'result': engine.bootstrap_report,
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

    def handle_verify_bootstrap(self, form_data) -> str:
        engine = self.context.get('runtime_engine')
        if engine:
            gh_mgr = self.context.get('github_manager')
            github_client = None
            if gh_mgr and gh_mgr.has_token():
                try:
                    from runtime.github.client import GitHubClient
                    github_client = GitHubClient(secret_backend=gh_mgr.secret_backend)
                except Exception:
                    pass
            import threading
            t = threading.Thread(target=engine.verify, kwargs={
                'github_client': github_client, 
                'fabric_client': self._get_fabric_client()
            }, daemon=True)
            t.start()
            self.context['direct_json_response'] = {"status": "started"}
        else:
            self.context['direct_json_response'] = {"status": "error", "message": "No engine"}
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

    def handle_fabric_setup(self, form_data) -> str:
        fabric_org = form_data.get('fabric_org', [''])[0]
        fabric_repo = form_data.get('fabric_repo', [''])[0]
        
        if not fabric_org or not fabric_repo:
            return '/?error=Both+Organization+and+Repository+are+required'
            
        engine = self.context.get('runtime_engine')
        if engine and engine.config:
            engine.config.fabric_org = fabric_org
            engine.config.fabric_repo = fabric_repo
            engine.config.save()
            self._audit("FABRIC_SETUP", "SUCCESS", f"{fabric_org}/{fabric_repo}")
            
            # Restart engine startup to re-run bootstrap with new config
            try:
                gh_mgr = self.context.get('github_manager')
                github_client = GitHubClient(secret_backend=gh_mgr.secret_backend)
                engine.startup(github_client=github_client, fabric_client=self._get_fabric_client())
                self.context['bootstrap_snapshot']['result'] = engine.bootstrap_report
            except Exception as e:
                logger.error(f"Failed to re-bootstrap after fabric setup: {e}")
                
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

    def handle_universe_accounts(self, parsed) -> str:
        accounts = []
        registry = self.context.get('account_registry')
        if registry:
            accounts = registry.list_accounts()
        return universe_accounts_page(accounts, self._get_csrf())
        
    def handle_universe_account_detail(self, parsed) -> str:
        account_id = parsed.path.split('/')[-1]
        registry = self.context.get('account_registry')
        if not registry:
            return generic_placeholder_page("Account Registry Not Available", self._get_csrf())
        account = registry.get_account(account_id)
        if not account:
            return generic_placeholder_page(f"Account {account_id} not found", self._get_csrf())
        return universe_account_detail_page(account, self._get_csrf())

    def handle_universe_projects(self, parsed) -> str:
        projects = []
        registry = self.context.get('project_registry')
        if registry:
            projects = registry.list_projects()
        return universe_projects_page(projects, self._get_csrf())

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
        if audit_mgr:
            if hasattr(audit_mgr, 'read_recent'):
                try:
                    events = audit_mgr.read_recent(limit=50)
                except Exception:
                    pass
            elif hasattr(audit_mgr, 'get_events'):
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


