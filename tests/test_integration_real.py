"""Real Integration tests for Customer Zero bootstrap flow."""
import os
import shutil
import tempfile
import unittest
from runtime.admin.server import AdminServer
from runtime.admin.auth import AdminSessionManager
from runtime.admin.github import GitHubAuthManager

# This test requires real GitHub credentials to pass the GitHubClient integration
# It is an explicit controlled GitHub test endpoint/provider, and is integration-test infrastructure,
# NOT a physical production proof.

class TestCustomerZeroIntegrationReal(unittest.TestCase):
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
        
    @unittest.skipIf(not os.environ.get("GITHUB_TEST_TOKEN"), "Skipping real integration test without token")
    def test_full_bootstrap_integration_real(self):
        auth_mgr = AdminSessionManager(self.data_dir, "rt-123")
        
        class MockAuditManager:
            pass
        audit_mgr = MockAuditManager()
        
        class MockSecretBackend:
            def retrieve(self, key):
                if key == "github-access-token":
                    return os.environ.get("GITHUB_TEST_TOKEN").encode('utf-8')
                return None
                
        backend = MockSecretBackend()
        gh_mgr = GitHubAuthManager(secret_backend=backend)
        
        server = AdminServer(
            host="127.0.0.1",
            port=0,
            auth_manager=auth_mgr,
            audit_manager=audit_mgr,
            github_manager=gh_mgr,
            local_operational_path=self.op_dir
        )
        
        dto = server.router._get_continuity_dto()
        self.assertIsNotNone(dto)
        # Note: If token is valid, status should be CONSISTENT or DEGRADED depending on repo contents
        # Since we use local_operational_path override, it should resolve local and be CONSISTENT
        self.assertEqual(dto.status, "CONSISTENT")
        self.assertEqual(dto.current_mission, "M-1")
        
if __name__ == "__main__":
    unittest.main()
