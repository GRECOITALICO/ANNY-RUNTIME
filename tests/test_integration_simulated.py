"""Integration tests for Customer Zero bootstrap flow."""
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


class TestCustomerZeroIntegrationSimulated(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.op_dir = os.path.join(self.data_dir, "ANNY-OPERATIONAL")
        os.makedirs(os.path.join(self.op_dir, "state"), exist_ok=True)
        os.makedirs(os.path.join(self.op_dir, "constitution"), exist_ok=True)
        os.makedirs(os.path.join(self.op_dir, "os"), exist_ok=True)
        
        with open(os.path.join(self.op_dir, "BOOTSTRAP.md"), "w") as f:
            f.write("# BOOTSTRAP")
        with open(os.path.join(self.op_dir, "state", "CURRENT_STATE.yaml"), "w") as f:
            f.write("schema_version: '1.0'")
        with open(os.path.join(self.op_dir, "state", "CURRENT_MISSION.yaml"), "w") as f:
            f.write("mission_id: M-1\nstatus: ACTIVE")
        with open(os.path.join(self.op_dir, "state", "NEXT_ACTION.yaml"), "w") as f:
            f.write("action: Execute")
            
    def tearDown(self):
        shutil.rmtree(self.data_dir)
        
    def test_full_bootstrap_integration(self):
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        audit_mgr = MagicMock()
        gh_mgr = MockGitHubManager(token="fake-token")
        
        server = AdminServer(
            host="127.0.0.1",
            port=0,
            auth_manager=auth_mgr,
            audit_manager=audit_mgr,
            github_manager=gh_mgr,
            local_operational_path=self.op_dir
        )
        
        dto = server.router._get_continuity_dto()
        self.assertEqual(dto.status, "CONSISTENT")
        self.assertEqual(dto.current_mission, "M-1")
        
if __name__ == "__main__":
    unittest.main()
