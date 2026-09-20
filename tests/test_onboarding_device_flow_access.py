import re
import tempfile
import unittest
from unittest.mock import MagicMock
from urllib.parse import urlparse

from runtime.admin.auth import AdminSessionManager
from runtime.admin.middleware import AdminMiddleware
from runtime.admin.routes import AdminRouter


class DeviceFlowManager:
    def __init__(self):
        self.authorized = False
        self.initiated = False

    def has_token(self):
        return self.authorized

    def initiate_device_flow(self):
        self.initiated = True
        return type("DeviceFlow", (), {
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://github.com/login/device",
        })()

    def poll_device_flow(self):
        return {"status": "AUTHORIZED" if self.authorized else "PENDING"}


class OnboardingDeviceFlowAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.auth = AdminSessionManager(self.temp_dir.name, "rt-test")
        self.github = DeviceFlowManager()
        self.middleware = AdminMiddleware(self.auth, github_manager=self.github)
        self.router = AdminRouter({
            "auth_manager": self.auth,
            "github_manager": self.github,
            "audit_manager": MagicMock(),
        })

    def tearDown(self):
        self.temp_dir.cleanup()

    def _onboarding_context(self):
        context = {}
        self.assertTrue(self.middleware.process_request("GET", "/", {"Host": "127.0.0.1"}, context))
        session = context["admin_session"]
        self.assertEqual(session.scope, "ONBOARDING_ONLY")
        return context, session

    def test_first_run_page_includes_the_live_session_csrf_token(self):
        context, session = self._onboarding_context()
        self.router.context = {"auth_manager": self.auth, "github_manager": self.github, **context}
        html = self.router.handle_dashboard(urlparse("/"))
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), session.csrf_token)

    def test_device_flow_init_allows_valid_onboarding_post_only(self):
        context, session = self._onboarding_context()
        headers = {"Host": "127.0.0.1", "Cookie": f"admin_session_id={session.admin_session_id}"}
        post_context = {}
        self.assertTrue(self.middleware.process_request("POST", "/github/device/init", headers, post_context))
        self.assertEqual(post_context["admin_session"].scope, "ONBOARDING_ONLY")
        self.assertTrue(self.middleware.process_post_body(
            "/github/device/init", {"csrf_token": [session.csrf_token]}, post_context
        ))

    def test_device_flow_init_rejects_missing_or_invalid_csrf(self):
        context, session = self._onboarding_context()
        for token in ("", "wrong-token"):
            post_context = {"admin_session": session}
            self.assertFalse(self.middleware.process_post_body(
                "/github/device/init", {"csrf_token": [token]}, post_context
            ))

    def test_device_flow_init_without_client_configuration_fails_closed(self):
        context, session = self._onboarding_context()
        unavailable_manager = MagicMock()
        unavailable_manager.initiate_device_flow.return_value = None
        self.router.context = {
            "auth_manager": self.auth,
            "github_manager": unavailable_manager,
            "admin_session": session,
        }
        redirect = self.router.handle_github_device_init({"csrf_token": [session.csrf_token]})
        self.assertEqual(redirect, "/?error=GitHub+Device+Flow+is+not+configured")
        self.assertEqual(self.auth.validate(session.admin_session_id).scope, "ONBOARDING_ONLY")

    def test_device_flow_poll_is_available_to_onboarding_session(self):
        context, session = self._onboarding_context()
        headers = {"Host": "127.0.0.1", "Cookie": f"admin_session_id={session.admin_session_id}"}
        poll_context = {}
        self.assertTrue(self.middleware.process_request("GET", "/github/device/poll", headers, poll_context))
        self.assertEqual(poll_context["admin_session"].scope, "ONBOARDING_ONLY")

    def test_unlisted_admin_route_remains_blocked_during_onboarding(self):
        context, session = self._onboarding_context()
        headers = {"Host": "127.0.0.1", "Cookie": f"admin_session_id={session.admin_session_id}"}
        blocked_context = {}
        self.assertFalse(self.middleware.process_request("GET", "/operations", headers, blocked_context))
        self.assertEqual(blocked_context["redirect_to"], "/")

    def test_successful_device_authorization_replaces_onboarding_session(self):
        context, session = self._onboarding_context()
        self.github.authorized = True
        self.router.context = {
            "auth_manager": self.auth,
            "github_manager": self.github,
            "audit_manager": MagicMock(),
            "admin_session": session,
        }
        self.router.handle_github_device_poll(urlparse("/github/device/poll"))
        self.assertTrue(self.router.context["destroy_session"])
        new_session = self.auth.validate(self.router.context["new_session_id"])
        self.assertIsNotNone(new_session)
        self.assertEqual(new_session.scope, "ADMIN")

    def test_failed_device_authorization_keeps_onboarding_session(self):
        context, session = self._onboarding_context()
        self.router.context = {
            "auth_manager": self.auth,
            "github_manager": self.github,
            "audit_manager": MagicMock(),
            "admin_session": session,
        }
        self.router.handle_github_device_poll(urlparse("/github/device/poll"))
        self.assertEqual(self.auth.validate(session.admin_session_id).scope, "ONBOARDING_ONLY")
        self.assertNotIn("destroy_session", self.router.context)


if __name__ == "__main__":
    unittest.main()
