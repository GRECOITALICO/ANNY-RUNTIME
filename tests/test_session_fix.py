import unittest
from unittest.mock import MagicMock, patch
import json
import tempfile
import shutil
import urllib.parse
from http.cookies import SimpleCookie
from runtime.admin.server import AdminServer, AdminRequestHandler
from runtime.admin.auth import AdminSessionManager
from runtime.admin.routes import AdminRouter

class MockGitHubManager:
    def __init__(self, token=None, fail_token=False):
        self.token = token
        self.fail_token = fail_token
        self.state = MagicMock()
        self.state.auth_status = "AUTHORIZED" if self.token else "UNAUTHORIZED"
        self.state.principal = "testuser" if self.token else None
        
    def has_token(self):
        return bool(self.token)
        
    def get_status(self):
        status = MagicMock()
        status.auth_status = self.state.auth_status
        status.to_dict.return_value = {"auth_status": status.auth_status}
        return status
        
    def store_and_validate_token(self, token):
        if self.fail_token or token == "ghp_invalid":
            return {"success": False, "error": "Validation failed"}
        self.token = token
        self.state.auth_status = "AUTHORIZED"
        return {"success": True, "principal": "testuser"}


class TestSessionFix(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        self.gh_mgr = MockGitHubManager()
        self.server = AdminServer("127.0.0.1", 0, self.auth_mgr, MagicMock(), self.gh_mgr)

    def tearDown(self):
        shutil.rmtree(self.data_dir)

    def test_get_first_run_sets_cookie(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        self.server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        self.assertTrue(any('admin_session_id=' in c for c in cookies))

    def test_first_run_csrf_is_nonempty(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        self.server.router.context = dict(self.server.admin_context)
        self.server.router.context.update(context)
        csrf = self.server.router._get_csrf()
        self.assertTrue(bool(csrf))

    def test_get_and_post_share_session(self):
        # Request 1: GET
        context1 = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context1)
        self.server.middleware.process_response(context1)
        session_id = context1.get('new_session_id')
        self.assertIsNotNone(session_id)
        
        # Request 2: POST
        context2 = {}
        self.server.middleware.process_request("POST", "/github/token", {'Host': '127.0.0.1', 'Cookie': f'admin_session_id={session_id}'}, context2)
        session2 = context2.get('admin_session')
        self.assertIsNotNone(session2)
        self.assertEqual(session2.admin_session_id, session_id)

    def test_post_token_reaches_handler(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        session = context.get('admin_session')
        
        form_data = {'github_token': ['ghp_valid'], 'csrf_token': [session.csrf_token]}
        
        context_post = {'admin_session': session, 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr}
        self.server.router.context = dict(self.server.admin_context)
        self.server.router.context.update(context_post)
        
        redirect_url = self.server.router.handle_github_token(form_data)
        self.assertEqual(redirect_url, "/")
        self.assertTrue(self.gh_mgr.has_token())

    def test_dispatch_post_exists(self):
        self.assertTrue(hasattr(self.server.router, 'dispatch_post'))

    def test_valid_csrf_allows_token_handler(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        session = context.get('admin_session')
        
        form_data = {'csrf_token': [session.csrf_token]}
        is_valid = self.server.middleware.process_post_body("/github/token", form_data, context)
        self.assertTrue(is_valid)

    def test_invalid_csrf_rejects_request(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        
        form_data = {'csrf_token': ['invalid_csrf']}
        is_valid = self.server.middleware.process_post_body("/github/token", form_data, context)
        self.assertFalse(is_valid)

    @patch('runtime.admin.routes.OrganizationDiscoveryService')
    @patch('runtime.admin.routes.CustomerZeroBootstrapResolver')
    def test_success_revokes_onboarding_session(self, mock_resolver, mock_discovery):
        mock_resolver.return_value.resolve.return_value = "CONSISTENT_MOCK"
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        session_id = context.get('new_session_id')
        
        form_data = {'github_token': ['ghp_valid']}
        self.server.router.context = dict(self.server.admin_context)
        self.server.router.context.update({'admin_session': self.auth_mgr.validate(session_id), 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr})
        
        self.server.router.handle_github_token(form_data)
        
        self.assertIsNone(self.auth_mgr.validate(session_id))
        self.assertTrue(self.server.router.context.get('destroy_session'))

    @patch('runtime.admin.routes.OrganizationDiscoveryService')
    @patch('runtime.admin.routes.CustomerZeroBootstrapResolver')
    def test_success_creates_normal_session(self, mock_resolver, mock_discovery):
        mock_resolver.return_value.resolve.return_value = "CONSISTENT_MOCK"
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        
        form_data = {'github_token': ['ghp_valid']}
        self.server.router.context = dict(self.server.admin_context)
        self.server.router.context.update({'admin_session': context.get('admin_session'), 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr})
        
        self.server.router.handle_github_token(form_data)
        
        new_session_id = self.server.router.context.get('new_session_id')
        self.assertIsNotNone(new_session_id)
        new_session = self.auth_mgr.validate(new_session_id)
        self.assertIsNotNone(new_session)
        self.assertEqual(new_session.scope, "ADMIN")

    @patch('runtime.admin.routes.OrganizationDiscoveryService')
    @patch('runtime.admin.routes.CustomerZeroBootstrapResolver')
    def test_success_redirects_dashboard(self, mock_resolver, mock_discovery):
        mock_resolver.return_value.resolve.return_value = "CONSISTENT_MOCK"
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        
        form_data = {'github_token': ['ghp_valid']}
        self.server.router.context = dict(self.server.admin_context)
        self.server.router.context.update({'admin_session': context.get('admin_session'), 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr})
        
        redirect_url = self.server.router.handle_github_token(form_data)
        self.assertEqual(redirect_url, "/")

    def test_failed_github_token_does_not_revoke_onboarding(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        session_id = context.get('new_session_id')
        
        form_data = {'github_token': ['ghp_invalid']}
        self.server.router.context = dict(self.server.admin_context)
        self.server.router.context.update({'admin_session': self.auth_mgr.validate(session_id), 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr})
        
        redirect_url = self.server.router.handle_github_token(form_data)
        self.assertIn("/?error=", redirect_url)
        
        self.assertIsNotNone(self.auth_mgr.validate(session_id))
        self.assertFalse(self.server.router.context.get('destroy_session'))

    def test_cookie_attributes_loopback(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1:3643'}, context)
        self.server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        
        for c in cookies:
            c_lower = c.lower()
            if 'admin_session_id=' in c_lower:
                self.assertIn('httponly', c_lower)
                self.assertIn('samesite=strict', c_lower)
                self.assertIn('path=/', c_lower)
                self.assertNotIn('secure', c_lower)

    def test_cookie_attributes_https(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': 'anny.cloud'}, context)
        self.server.middleware.process_response(context)
        cookies = context.get('set_cookies', [])
        
        for c in cookies:
            c_lower = c.lower()
            if 'admin_session_id=' in c_lower:
                self.assertIn('httponly', c_lower)
                self.assertIn('samesite=strict', c_lower)
                self.assertIn('path=/', c_lower)
                self.assertIn('secure', c_lower)


class TestIntegrationSimulated(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        self.gh_mgr = MockGitHubManager()
        self.server = AdminServer("127.0.0.1", 0, self.auth_mgr, MagicMock(), self.gh_mgr)
        
        # Setup mock handler
        class MockHandler:
            def __init__(self, path, method, headers, wfile):
                self.path = path
                self.command = method
                self.headers = headers
                self.wfile = wfile
                self.response_status = None
                self.response_headers = []
            
            def send_response(self, status):
                self.response_status = status
                
            def send_header(self, k, v):
                self.response_headers.append((k, v))
                
            def end_headers(self):
                pass
                
        self.MockHandler = MockHandler

    def tearDown(self):
        shutil.rmtree(self.data_dir)

    @patch('runtime.admin.routes.OrganizationDiscoveryService')
    @patch('runtime.admin.routes.CustomerZeroBootstrapResolver')
    def test_full_http_integration(self, mock_resolver, mock_discovery):
        mock_resolver.return_value.resolve.return_value = "CONSISTENT_MOCK"
        
        # REQUEST 1: GET /
        wfile_get = MagicMock()
        headers_get = {'Host': '127.0.0.1'}
        handler_get = self.MockHandler("/", "GET", headers_get, wfile_get)
        handler_get.server = self.server
        
        AdminRequestHandler.do_GET(handler_get)
        
        self.assertEqual(handler_get.response_status, 200)
        
        cookie_val = None
        for k, v in handler_get.response_headers:
            if k == 'Set-Cookie' and 'admin_session_id=' in v:
                cookie_val = v.split(';')[0].split('=')[1]
                
        self.assertIsNotNone(cookie_val)
        
        html = wfile_get.write.call_args[0][0].decode('utf-8')
        self.assertIn('name="csrf_token"', html)
        
        import re
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        self.assertIsNotNone(m)
        csrf_token = m.group(1)
        self.assertTrue(bool(csrf_token))
        
        # REQUEST 2: POST /github/token
        form_data_str = urllib.parse.urlencode({'github_token': 'ghp_valid_test_token', 'csrf_token': csrf_token})
        
        wfile_post = MagicMock()
        headers_post = {
            'Host': '127.0.0.1',
            'Cookie': f'admin_session_id={cookie_val}',
            'content-type': 'application/x-www-form-urlencoded',
            'content-length': str(len(form_data_str))
        }
        handler_post = self.MockHandler("/github/token", "POST", headers_post, wfile_post)
        handler_post.server = self.server
        handler_post.rfile = MagicMock()
        handler_post.rfile.read.return_value = form_data_str.encode('utf-8')
        
        AdminRequestHandler.do_POST(handler_post)
        
        self.assertEqual(handler_post.response_status, 303)
        redirect_loc = None
        for k, v in handler_post.response_headers:
            if k == 'Location':
                redirect_loc = v
        self.assertEqual(redirect_loc, "/")
        
        self.assertTrue(self.gh_mgr.has_token())


if __name__ == '__main__':
    unittest.main()
