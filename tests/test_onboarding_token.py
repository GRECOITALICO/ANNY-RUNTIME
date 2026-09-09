import unittest
from unittest.mock import MagicMock, patch
import json
import tempfile
import shutil
import urllib.error
from runtime.admin.server import AdminServer
from runtime.admin.auth import AdminSessionManager
from runtime.admin.github import GitHubAuthManager
from runtime.secrets.backend import FileSecretBackend
from runtime.admin.routes import AdminRouter

class TestOnboardingToken(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.secret_backend = FileSecretBackend(self.data_dir, b"0"*32)
        self.gh_mgr = GitHubAuthManager(self.secret_backend)
        self.auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        self.server = AdminServer("127.0.0.1", 0, self.auth_mgr, MagicMock(), self.gh_mgr, secret_backend=self.secret_backend, bootstrap_snapshot={})
        
    def tearDown(self):
        shutil.rmtree(self.data_dir)

    def test_first_run_shows_only_github_token_input(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_dashboard(urllib.parse.urlparse("/"))
        self.assertIn('name="github_token"', html)
        self.assertIn('type="password"', html)
        self.assertNotIn('bootstrap_token', html)

    def test_no_device_flow_ui(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_dashboard(urllib.parse.urlparse("/"))
        self.assertNotIn('>Device Flow<', html)
        self.assertNotIn('name="device_code"', html)

    @patch('urllib.request.urlopen')
    def test_valid_github_token_succeeds(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = self.gh_mgr.store_and_validate_token("ghp_valid_token")
        self.assertTrue(result['success'])
        self.assertEqual(result['principal'], "testuser")
        self.assertEqual(result['scopes'], ["repo", "read:org"])

    def test_empty_token_fails(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        # Fake an ONBOARDING_ONLY session
        context['admin_session'] = MagicMock(scope="ONBOARDING_ONLY")
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_github_token({'github_token': ['']})
        self.assertIn("GitHub+Access+Token+is+required", html)

    @patch('urllib.request.urlopen')
    def test_invalid_token_fails_safely(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        result = self.gh_mgr.store_and_validate_token("ghp_invalid_token")
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "GitHub connection failed. Token may be invalid or expired.")
        self.assertNotIn("ghp_invalid_token", result['error'])

    @patch('urllib.request.urlopen')
    def test_insufficient_permissions_fails(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo" # missing read:org
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = self.gh_mgr.store_and_validate_token("ghp_valid_token")
        self.assertFalse(result['success'])
        self.assertIn("GITHUB_AUTHORIZATION_INSUFFICIENT", result['error'])

    @patch('urllib.request.urlopen')
    def test_token_stored_only_in_secret_backend(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.gh_mgr.store_and_validate_token("ghp_secret_token")
        stored = self.secret_backend.retrieve(self.gh_mgr.GITHUB_TOKEN_REF)
        self.assertEqual(stored, b"ghp_secret_token")
        self.assertNotIn("ghp_secret_token", self.gh_mgr.state.__dict__.values())

    @patch('urllib.request.urlopen')
    def test_token_absent_from_dto(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.gh_mgr.store_and_validate_token("ghp_secret_token")
        dto = self.gh_mgr.get_status().to_dict()
        self.assertNotIn("ghp_secret_token", str(dto))

    def test_token_absent_from_html(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_dashboard(urllib.parse.urlparse("/"))
        self.assertNotIn("ghp_", html)

    @patch('urllib.request.urlopen')
    def test_token_absent_from_logs(self, mock_urlopen):
        import logging
        import io
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        logger = logging.getLogger("runtime.admin.github")
        logger.addHandler(handler)
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.gh_mgr.store_and_validate_token("ghp_secret_token")
        
        log_output = log_stream.getvalue()
        self.assertNotIn("ghp_secret_token", log_output)
        logger.removeHandler(handler)

    @patch('urllib.request.urlopen')
    def test_principal_discovery(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "discovered_user"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.gh_mgr.store_and_validate_token("ghp_secret_token")
        self.assertEqual(self.gh_mgr.state.principal, "discovered_user")

    @patch('runtime.github.client.GitHubClient.list_organizations')
    def test_organization_discovery(self, mock_list_orgs):
        mock_list_orgs.return_value = [{"login": "org1"}, {"login": "org2"}]
        from runtime.github.discovery import OrganizationDiscoveryService
        from runtime.github.client import GitHubClient
        client = GitHubClient(secret_backend=self.secret_backend)
        disc = OrganizationDiscoveryService(client)
        orgs = disc.discover_organizations()
        self.assertEqual(len(orgs), 2)

    @patch('runtime.github.client.GitHubClient.list_repositories')
    def test_repository_discovery(self, mock_list_repos):
        mock_list_repos.return_value = [{"full_name": "org1/repo1"}]
        from runtime.github.discovery import OrganizationDiscoveryService
        from runtime.github.client import GitHubClient
        client = GitHubClient(secret_backend=self.secret_backend)
        disc = OrganizationDiscoveryService(client)
        repos = disc.discover_repositories()
        self.assertEqual(len(repos), 1)

    def test_no_hardcoded_grecoitalico(self):
        import subprocess
        result = subprocess.run(['grep', '-rn', 'GRECOITALICO', '../runtime/'], capture_output=True, text=True)
        self.assertEqual(result.stdout, "")

    def test_no_hardcoded_conrrad(self):
        import subprocess
        result = subprocess.run(['grep', '-rn', 'CONRRAD', '../runtime/'], capture_output=True, text=True)
        self.assertEqual(result.stdout, "")

    def test_no_hardcoded_mission_id(self):
        import subprocess
        result = subprocess.run(['grep', '-rn', 'OP-GRECO-', '../runtime/'], capture_output=True, text=True)
        self.assertEqual(result.stdout, "")

    def test_no_second_credential_requirement(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_dashboard(urllib.parse.urlparse("/"))
        self.assertNotIn("bootstrap token", html.lower())

    def test_onboarding_session_survives_boundary(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        session = context.get('admin_session')
        self.assertIsNotNone(session)
        self.assertEqual(session.scope, "ONBOARDING_ONLY")
        
        context2 = {}
        headers2 = {'Host': '127.0.0.1', 'Cookie': f'admin_session_id={session.admin_session_id}'}
        self.server.middleware.process_request("GET", "/", headers2, context2)
        session2 = context2.get('admin_session')
        self.assertIsNotNone(session2)
        self.assertEqual(session2.admin_session_id, session.admin_session_id)

    @patch('urllib.request.urlopen')
    @patch('runtime.admin.routes.OrganizationDiscoveryService')
    @patch('runtime.admin.routes.CustomerZeroBootstrapResolver')
    def test_successful_onboarding_reaches_ready_state(self, mock_resolver_cls, mock_discovery_cls, mock_urlopen):
        # 1. First run, get session
        context1 = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context1)
        self.server.middleware.process_response(context1)
        session_id = context1.get('new_session_id')
        
        # 2. Setup mocks for token validation
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        
        # 3. Setup mocks for discovery
        mock_resolver = MagicMock()
        mock_resolver_cls.return_value = mock_resolver
        mock_resolver.resolve.return_value = "CONSISTENT_MOCK"
        
        # 4. Submit token
        context2 = {'admin_session': self.auth_mgr.validate(session_id), 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr, 'audit_manager': MagicMock()}
        self.server.router.context = context2
        res = self.server.router.handle_github_token({'github_token': ['ghp_valid']})
        self.assertEqual(res, "/")
        self.assertTrue(context2.get('destroy_session'))
        self.assertIsNotNone(context2.get('new_session_id'))

    def test_fabric_remains_not_configured(self):
        context = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
        # Fake an already onboarded state by passing is_first_run=False logic
        self.gh_mgr.state.auth_status = "AUTHORIZED"
        self.gh_mgr.state.principal = "testuser"
        
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_dashboard(urllib.parse.urlparse("/"))
        self.assertIn("NOT CONFIGURED", html)

    @patch('urllib.request.urlopen')
    def test_token_absent_from_journal(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        
        audit_mgr = MagicMock()
        context2 = {'admin_session': MagicMock(scope="ONBOARDING_ONLY"), 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr, 'audit_manager': audit_mgr}
        self.server.router.context = context2
        
        # Provide a token and process it
        self.server.router.handle_github_token({'github_token': ['ghp_secret_token_123']})
        
        # Check all audit calls for leaked token
        for call in audit_mgr.log.call_args_list:
            args, kwargs = call
            self.assertNotIn("ghp_secret_token_123", str(args))
            self.assertNotIn("ghp_secret_token_123", str(kwargs))

    @patch('urllib.request.urlopen')
    @patch('runtime.admin.routes.OrganizationDiscoveryService')
    @patch('runtime.admin.routes.CustomerZeroBootstrapResolver')
    def test_onboarding_session_revoked_after_success(self, mock_resolver_cls, mock_discovery_cls, mock_urlopen):
        # 1. First run, get session
        context1 = {}
        self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context1)
        self.server.middleware.process_response(context1)
        session_id = context1.get('new_session_id')
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode('utf-8')
        mock_resp.headers.get.return_value = "repo, read:org"
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        
        mock_resolver = MagicMock()
        mock_resolver_cls.return_value = mock_resolver
        mock_resolver.resolve.return_value = "CONSISTENT_MOCK"
        
        context2 = {'admin_session': self.auth_mgr.validate(session_id), 'github_manager': self.gh_mgr, 'auth_manager': self.auth_mgr, 'audit_manager': MagicMock()}
        self.server.router.context = context2
        self.server.router.handle_github_token({'github_token': ['ghp_valid']})
        
        # Verify the onboarding session was destroyed in the AuthManager
        self.assertIsNone(self.auth_mgr.validate(session_id))
        self.assertTrue(context2.get('destroy_session'))

    def test_fresh_state_onboarding(self):
        # A fresh state should not allow any non-onboarding routes
        context = {}
        allowed = self.server.middleware.process_request("GET", "/admin/diagnostics", {'Host': '127.0.0.1'}, context)
        self.assertFalse(allowed)
        self.assertEqual(context.get('redirect_to'), '/')
        
        # It should allow onboarding routes and create ONBOARDING_ONLY session
        context2 = {}
        allowed2 = self.server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context2)
        self.assertTrue(allowed2)
        self.assertIsNotNone(context2.get('admin_session'))
        self.assertEqual(context2.get('admin_session').scope, "ONBOARDING_ONLY")

    def test_github_page_has_no_validate_form(self):
        # Fake an already onboarded state
        self.gh_mgr.state.auth_status = "AUTHORIZED"
        self.gh_mgr.state.principal = "testuser"
        context = {'admin_session': MagicMock()}
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_github(urllib.parse.urlparse("/github"))
        self.assertNotIn("/github/validate", html)

    def test_github_page_uses_token_endpoint(self):
        context = {'admin_session': MagicMock()}
        self.server.router.context = {**self.server.admin_context, **context}
        html = self.server.router.handle_github(urllib.parse.urlparse("/github"))
        self.assertIn("/github/token", html)

    def test_reconnect_uses_token_endpoint(self):
        from runtime.admin.templates import reconnect_page
        html = reconnect_page("test_csrf")
        self.assertIn("/github/token", html)
        self.assertNotIn("/github/connect", html)

    def test_failure_uses_token_endpoint(self):
        from runtime.admin.templates import failure_page
        html = failure_page("reason", "test_csrf")
        self.assertIn("/github/token", html)
        self.assertNotIn("/github/connect", html)

    def test_github_validate_route_not_required(self):
        context = {}
        # Ensure it's not in onboarding routes
        allowed = self.server.middleware.process_request("POST", "/github/validate", {'Host': '127.0.0.1'}, context)
        self.assertFalse(allowed)

    def test_github_connect_route_not_required(self):
        context = {}
        # Ensure it's not in onboarding routes
        allowed = self.server.middleware.process_request("POST", "/github/connect", {'Host': '127.0.0.1'}, context)
        self.assertFalse(allowed)

if __name__ == '__main__':
    unittest.main()
