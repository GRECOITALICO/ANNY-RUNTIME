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

if __name__ == "__main__":
    unittest.main()
