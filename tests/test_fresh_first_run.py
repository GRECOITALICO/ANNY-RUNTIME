"""Test fresh first run flow."""
import os
import shutil
import tempfile
import unittest
import urllib.parse
from unittest.mock import MagicMock
from runtime.admin.server import AdminServer
from runtime.admin.auth import AdminSessionManager
from runtime.github.client import GitHubClient, GitHubAuthError

class MockGitHubManager:
    def __init__(self, token=None):
        self.token = token
        
    def has_token(self):
        return bool(self.token)
        
    def get_status(self):
        status = MagicMock()
        status.auth_status = "AUTHORIZED" if self.token else "UNAUTHORIZED"
        status.to_dict.return_value = {"auth_status": status.auth_status}
        return status


class TestFreshFirstRun(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
            
    def tearDown(self):
        shutil.rmtree(self.data_dir)
        
    def test_first_run_flow(self):
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        audit_mgr = MagicMock()
        gh_mgr = MockGitHubManager(token=None)
        
        server = AdminServer(
            host="127.0.0.1",
            port=0,
            auth_manager=auth_mgr,
            audit_manager=audit_mgr,
            github_manager=gh_mgr
        )
        
        # Run middleware
        context = {}
        server.middleware.process_request("GET", "/", {}, context)
        
        # Dispatch to dashboard
        handler_mock = MagicMock()
        server.router.context = context
        server.router.dispatch_get("/", handler_mock)
        
        # Run middleware response processing
        server.middleware.process_response(context)
        
        # It should send the first-run page and set a session cookie
        self.assertTrue(handler_mock.send_response.called)
        
        cookies_set = context.get('set_cookies', [])
        self.assertTrue(any("admin_session_id" in c for c in cookies_set))
        
        # Scope should be ONBOARDING_ONLY
        self.assertEqual(len(auth_mgr._sessions), 1)
        session = list(auth_mgr._sessions.values())[0]
        self.assertEqual(session.scope, "ONBOARDING_ONLY")
        
    def test_local_http_first_run_cookie(self):
        """P0-A: local HTTP onboarding cookie should not have Secure flag."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), MockGitHubManager(None))
        context = {}
        server.middleware.process_request("GET", "/", {'Host': '127.0.0.1:3643'}, context)
        server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        self.assertTrue(any("admin_session_id" in c for c in cookies))
        # No Secure flag
        self.assertFalse(any("secure" in c.lower() for c in cookies))
        
    def test_https_production_cookie(self):
        """P0-A: HTTPS production onboarding cookie should have Secure flag."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), MockGitHubManager(None))
        context = {}
        server.middleware.process_request("GET", "/", {'Host': 'anny.cloud'}, context)
        server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        self.assertTrue(any("admin_session_id" in c for c in cookies))
        # Should have Secure flag
        self.assertTrue(any("secure" in c.lower() for c in cookies))
        
    def test_onboarding_session_revocation(self):
        """P0-G: Onboarding session should be revoked upon successful GitHub connection."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), MockGitHubManager(None))
        context = {}
        server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        server.middleware.process_response(context)
        
        session = list(auth_mgr._sessions.values())[0]
        
        # Simulate GitHub Validate
        server.middleware.revoke_onboarding_session(context)
        server.middleware.process_response(context)
        
        cookies = context.get('set_cookies', [])
        self.assertTrue(any("max-age=0" in c.lower() for c in cookies))
        self.assertEqual(len(auth_mgr._sessions), 0)

    def test_loopback_ipv6_cookie(self):
        """P0-2: IPv6 loopback [::1] should not have Secure flag."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), MockGitHubManager(None))
        context = {}
        server.middleware.process_request("GET", "/", {'Host': '[::1]:3643'}, context)
        server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        self.assertTrue(any("admin_session_id" in c for c in cookies))
        self.assertFalse(any("secure" in c.lower() for c in cookies))

    def test_lookalike_host_rejected(self):
        """P0-2: Lookalike hosts like localhost.evil.example should have Secure flag."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), MockGitHubManager(None))
        context = {}
        server.middleware.process_request("GET", "/", {'Host': 'localhost.evil.example'}, context)
        server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        self.assertTrue(any("admin_session_id" in c for c in cookies))
        self.assertTrue(any("secure" in c.lower() for c in cookies))

    def test_session_survives_http_boundary(self):
        """P0-3: Validate that a cookie created in request 1 survives into request 2."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), MockGitHubManager(None))
        
        # Request 1
        context1 = {}
        server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context1)
        server.middleware.process_response(context1)
        cookies = context1.get('set_cookies', [])
        
        # Extract cookie value
        cookie_val = ""
        for c in cookies:
            if "admin_session_id=" in c:
                cookie_val = c.split(';')[0].split('=')[1]
                break
        self.assertTrue(cookie_val)
        
        # Request 2
        context2 = {}
        server.middleware.process_request("GET", "/", {'Host': '127.0.0.1', 'Cookie': f'admin_session_id={cookie_val}'}, context2)
        
        # Verify session is recognized
        self.assertIn('admin_session', context2)
        self.assertEqual(context2['admin_session'].admin_session_id, cookie_val)

    def test_cookie_attributes(self):
        """P0-3: Validate cookie attributes (HttpOnly, SameSite=Strict, Path=/)."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), MockGitHubManager(None))
        context = {}
        server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        
        found = False
        for c in cookies:
            if "admin_session_id=" in c:
                found = True
                c_lower = c.lower()
                self.assertIn("httponly", c_lower)
                self.assertIn("samesite=strict", c_lower)
                self.assertIn("path=/", c_lower)
        self.assertTrue(found)

    def test_onboarding_session_revoked_on_github_connect(self):
        """P0-F: Onboarding session revoked upon successful GitHub connection."""
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        gh_mgr = MockGitHubManager(None)
        server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), gh_mgr, bootstrap_snapshot={})
        
        # 1. Create onboarding session
        context1 = {}
        server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context1)
        server.middleware.process_response(context1)
        cookies = context1.get('set_cookies', [])
        cookie_val = ""
        for c in cookies:
            if "admin_session_id=" in c:
                cookie_val = c.split(';')[0].split('=')[1]
                break
        self.assertTrue(cookie_val)
        
        # 2. Simulate POST to /github/validate
        gh_mgr.validate = MagicMock(return_value=True) # Success
        context2 = {}
        # Pre-process middleware
        server.middleware.process_request("POST", "/github/validate", {'Host': '127.0.0.1', 'Cookie': f'admin_session_id={cookie_val}'}, context2)
        # Inject into context manually as the router would
        server.router.context['admin_session'] = context2.get('admin_session')
        server.router.context['auth_manager'] = auth_mgr
        
        server.router.handle_github_validate({})
        
        # Session should be destroyed
        self.assertTrue(server.router.context.get('destroy_session'))
        self.assertNotIn(cookie_val, auth_mgr._sessions)

    def test_admin_server_single_bootstrap(self):
        """P0-A, P0-B, P0-E: AdminServer receives snapshot and exposes UNKNOWN for missing dependencies."""
        mock_result = MagicMock()
        mock_result.status.value = "CONSISTENT"
        mock_result.canonical_state.repository_name = "test/repo"
        mock_result.canonical_state.current_mission.id = "M-1"
        mock_result.canonical_state.current_task.name = "Task"
        mock_result.canonical_state.next_action.action = "Action"
        mock_result.canonical_state.blockers = []
        mock_result.canonical_state.l2_workers = []
        mock_result.canonical_state.revision = "REV"
        
        server = AdminServer(
            host="127.0.0.1", port=0,
            auth_manager=MagicMock(), audit_manager=MagicMock(), github_manager=MagicMock(),
            bootstrap_snapshot={'result': mock_result, 'discovered_repos': []}
        )
        
        # Verify context mapping
        self.assertEqual(server.admin_context['event_bus'], "UNKNOWN")
        self.assertEqual(server.admin_context['runtime_engine'], "UNKNOWN")
        self.assertIn('bootstrap_snapshot', server.admin_context)
        
        # Verify routes uses the snapshot
        dto = server.router._get_continuity_dto()
        self.assertEqual(dto.status, "CONSISTENT")
        self.assertEqual(dto.current_mission, "M-1")

if __name__ == "__main__":
    unittest.main()
