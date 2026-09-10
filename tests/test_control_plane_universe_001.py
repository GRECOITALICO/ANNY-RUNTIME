import pytest
from unittest.mock import MagicMock
from runtime.admin.routes import AdminRouter
from runtime.admin.dto import ContinuityDTO
from runtime.continuity.state import ContinuityStatus

class DummyHandler:
    def __init__(self):
        self.headers = []
        self.sent_content = b""
        self.status = 200
        
    def send_response(self, status):
        self.status = status
        
    def send_header(self, key, value):
        self.headers.append((key, value))
        
    def end_headers(self):
        pass
        
    def wfile_write(self, b):
        self.sent_content += b
        
    class WFile:
        def __init__(self, parent):
            self.parent = parent
        def write(self, b):
            self.parent.wfile_write(b)
            
    @property
    def wfile(self):
        return self.WFile(self)

class ParsedUrl:
    def __init__(self, path, query=""):
        self.path = path
        self.query = query

@pytest.fixture
def mock_context():
    gh_mgr = MagicMock()
    gh_mgr.get_status().to_dict.return_value = {"auth_status": "CONNECTED", "connected": True}
    gh_mgr.get_status().connected = True
    gh_mgr.has_token.return_value = True
    
    exec_mgr = MagicMock()
    exec_mgr.model_registry.models = {"mod1": "test"}
    exec_mgr.registry.capabilities = {"cap1": "test"}
    exec_mgr.worker_manager.workers = {"wrk1": "test"}
    exec_mgr._tasks = {"tsk1": "test"}
    
    audit_mgr = MagicMock()
    audit_mgr.get_events.return_value = [("id", "time", "level", "cat", "mod", "type", "SUCCESS", "msg", "data", "inst", "rt")]

    return {
        'github_manager': gh_mgr,
        'execution_manager': exec_mgr,
        'audit_manager': audit_mgr,
        'bootstrap_snapshot': {'discovered_repos': [], 'result': MagicMock(status=ContinuityStatus.CONSISTENT, canonical_source="test", l2_worker_summary={}, organizations=[], repositories=[], missions=[])},
        'admin_session': MagicMock(admin_session_id="test", principal="test")
    }

def test_control_plane_universe_routing(mock_context):
    router = AdminRouter(mock_context)
    
    endpoints = [
        "/universe/organization",
        "/universe/projects",
        "/universe/repositories",
        "/universe/resources",
        "/execution/missions",
        "/execution/tasks",
        "/execution/workers",
        "/execution/executions",
        "/execution/workspaces",
        "/intelligence/capabilities",
        "/intelligence/executors",
        "/intelligence/performance",
        "/infrastructure/runtime",
        "/continuity/timeline",
        "/audit/events",
        "/audit/provenance",
        "/audit/evidence",
        "/search"
    ]
    
    for ep in endpoints:
        assert ep in router._get_routes, f"Endpoint {ep} is missing in AdminRouter"
        
def test_control_plane_universe_handlers(mock_context):
    router = AdminRouter(mock_context)
    
    # Test Org
    html = router.handle_universe_organization(ParsedUrl("/universe/organization"))
    assert "Organization Map" in html
    assert "ghp_" not in html
    
    # Test Dashboard (Overview)
    html = router.handle_dashboard(ParsedUrl("/"))
    assert "ANNY Control Plane" in html
    
    # Test Topology
    html = router.handle_infrastructure_topology(ParsedUrl("/infrastructure/runtime"))
    assert "Infrastructure Topology" in html
    assert "GitHub" in html
    
    # Test Audit Events
    html = router.handle_audit_events(ParsedUrl("/audit/events"))
    assert "msg" in html
    
    # Test Empty / Error states
    html = router.handle_audit_provenance(ParsedUrl("/audit/provenance"))
    assert "No provenance data selected or available" in html

    # Test Search
    html = router.handle_search(ParsedUrl("/search", "q=test"))
    assert "Results for: test" in html
