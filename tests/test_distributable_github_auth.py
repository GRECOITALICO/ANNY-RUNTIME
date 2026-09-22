import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from runtime.admin.github import GitHubAuthManager
from runtime.admin.server import build_github_auth_manager
from runtime.core.config import RuntimeConfig
from runtime.github.client import GitHubClient
from runtime.secrets.backend import FileSecretBackend


class TestDistributableGithubAuth(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.backend = FileSecretBackend(self.data_dir, b"0" * 32)

    def tearDown(self):
        shutil.rmtree(self.data_dir)

    def test_config_reads_public_client_id_from_environment(self):
        with patch.dict(os.environ, {"ANNY_GITHUB_CLIENT_ID": "Iv1.public-test"}, clear=False):
            config = RuntimeConfig.load()
        self.assertEqual(config.github_client_id, "Iv1.public-test")

    def test_server_auth_manager_receives_configured_client_id(self):
        config = RuntimeConfig(github_client_id="Iv1.public-test")
        manager = build_github_auth_manager(self.backend, config)
        self.assertEqual(manager.client_id, "Iv1.public-test")

    @patch("urllib.request.urlopen")
    def test_device_flow_rejects_insufficient_scopes(self, mock_urlopen):
        manager = GitHubAuthManager(self.backend, client_id="Iv1.public-test")
        manager._device_flow = MagicMock(
            device_code="device",
            started_at=time.time(),
            expires_in=900,
        )
        manager._device_flow.user_code = "USER-CODE"
        manager._device_flow.verification_uri = "https://github.com/login/device"
        manager._device_flow.interval = 5

        token_response = MagicMock()
        token_response.read.return_value = json.dumps({"access_token": "gho_test"}).encode()
        token_response.getcode.return_value = 200

        user_response = MagicMock()
        user_response.read.return_value = json.dumps({"login": "testuser"}).encode()
        user_response.headers.get.return_value = "repo"

        mock_urlopen.side_effect = [
            MagicMock(__enter__=MagicMock(return_value=token_response)),
            MagicMock(__enter__=MagicMock(return_value=user_response)),
        ]

        result = manager.poll_device_flow()

        self.assertEqual(result["status"], "ERROR")
        self.assertFalse(manager.has_token())
        self.assertEqual(manager.state.token_status, "INSUFFICIENT_SCOPE")
        self.assertEqual(manager.state.auth_status, "DEGRADED")

    @patch("urllib.request.urlopen")
    def test_device_flow_accepts_required_scopes(self, mock_urlopen):
        manager = GitHubAuthManager(self.backend, client_id="Iv1.public-test")
        manager._device_flow = MagicMock(
            device_code="device",
            started_at=0.0,
            expires_in=900,
        )
        manager._device_flow.user_code = "USER-CODE"
        manager._device_flow.verification_uri = "https://github.com/login/device"
        manager._device_flow.interval = 5

        token_response = MagicMock()
        token_response.read.return_value = json.dumps({"access_token": "gho_test"}).encode()
        token_response.getcode.return_value = 200

        user_response = MagicMock()
        user_response.read.return_value = json.dumps({"login": "testuser"}).encode()
        user_response.headers.get.return_value = "repo, read:org"

        mock_urlopen.side_effect = [
            MagicMock(__enter__=MagicMock(return_value=token_response)),
            MagicMock(__enter__=MagicMock(return_value=user_response)),
        ]

        result = manager.poll_device_flow()

        self.assertEqual(result["status"], "AUTHORIZED")
        self.assertTrue(manager.has_token())
        self.assertEqual(manager.state.auth_status, "AUTHORIZED")
        self.assertEqual(manager.state.scopes, ["repo", "read:org"])

    @patch("urllib.request.urlopen")
    def test_github_client_uses_provider_neutral_runtime_user_agent(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "testuser"}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        client = GitHubClient(token="gho_test")
        client.get_authenticated_principal()

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer gho_test")
        self.assertEqual(request.headers["User-agent"], "ANNY-Runtime/1.0")
        self.assertNotIn("CustomerZero", request.headers["User-agent"])


if __name__ == "__main__":
    unittest.main()
