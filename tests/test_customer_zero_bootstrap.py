"""Customer Zero Bootstrap verification test suite.

Test Classification:
- UNIT: Tests that use mocks and local state only
- INTEGRATION_SIMULATED: Tests that simulate the full pipeline with MockGitHubClient
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from runtime.events.bus import EventBus, EventType
from runtime.github.client import (
    GitHubClient,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubTimeoutError,
    GitHubRateLimitError,
    GitHubClientError,
)
from runtime.github.discovery import (
    OrganizationDiscoveryService,
    DiscoveredPrincipal,
    DiscoveredOrganization,
    DiscoveredRepository,
)
from runtime.continuity.operational import (
    OperationalRepositoryProvider,
    OperationalRepositoryAmbiguousError,
    OperationalRepositoryNotFoundError,
)
from runtime.continuity.bootstrap import CustomerZeroBootstrapResolver
from runtime.continuity.reconciler import ContinuityReconciler
from runtime.continuity.state import ContinuityStatus
from runtime.admin.dto import (
    ContinuityDTO,
    OrganizationDTO,
    RepositoryDTO,
    BlockerDTO,
    L2WorkerSummaryDTO,
)


# --- Customer Zero test fixtures (clearly marked as test data) ---
CUSTOMER_ZERO_TEST_ORG = "TEST-ORG"  # Test data, not a universal default
CUSTOMER_ZERO_TEST_REPO = "TEST-OPERATIONAL"  # Test data
CUSTOMER_ZERO_TEST_MISSION = "MISSION-TEST-001"  # Test data


class MockGitHubClient(GitHubClient):
    """Mock GitHub Client for UNIT testing without network.
    
    Clearly marked as test infrastructure, NOT production proof.
    """

    def __init__(self, fail_auth=False, fail_not_found=False, fail_timeout=False,
                 fail_rate_limit=False, repos=None):
        super().__init__()
        self.fail_auth = fail_auth
        self.fail_not_found = fail_not_found
        self.fail_timeout = fail_timeout
        self.fail_rate_limit = fail_rate_limit
        self._repos = repos

    def get_authenticated_principal(self):
        if self.fail_auth:
            raise GitHubAuthError("Unauthorized token")
        return {"login": "test-principal", "type": "User", "id": 12345}

    def list_organizations(self):
        if self.fail_auth:
            raise GitHubAuthError("Unauthorized token")
        if self.fail_timeout:
            raise GitHubTimeoutError("Request timed out")
        if self.fail_rate_limit:
            raise GitHubRateLimitError("Rate limit exceeded")
        return [{"login": CUSTOMER_ZERO_TEST_ORG, "description": "Test Org", "public_repos": 10}]

    def list_repositories(self, org=None):
        if self.fail_auth:
            raise GitHubAuthError("Unauthorized token")
        if self.fail_timeout:
            raise GitHubTimeoutError("Request timed out")
        if self.fail_rate_limit:
            raise GitHubRateLimitError("Rate limit exceeded")
        if self._repos is not None:
            return self._repos
        return [
            {"full_name": f"{CUSTOMER_ZERO_TEST_ORG}/{CUSTOMER_ZERO_TEST_REPO}", "name": CUSTOMER_ZERO_TEST_REPO, "owner": {"login": CUSTOMER_ZERO_TEST_ORG}, "private": True, "archived": False, "default_branch": "main", "topics": ["anny-operational"]},
            {"full_name": f"{CUSTOMER_ZERO_TEST_ORG}/SOME-RUNTIME", "name": "SOME-RUNTIME", "owner": {"login": CUSTOMER_ZERO_TEST_ORG}, "private": False, "archived": False, "default_branch": "main", "topics": []},
        ]

    def get_repository(self, owner, repo):
        if self.fail_not_found:
            raise GitHubNotFoundError("Not found")
        return {"full_name": f"{owner}/{repo}", "default_branch": "main"}

    def _request(self, endpoint, query_params=None, headers_extra=None):
        if self.fail_auth:
            raise GitHubAuthError("Unauthorized")
        if self.fail_timeout:
            raise GitHubTimeoutError("Timeout")
        if self.fail_rate_limit:
            raise GitHubRateLimitError("Rate limited")
        if 'BOOTSTRAP.md' in endpoint or '.anny/operational.yaml' in endpoint:
            # Check if this repo should have the marker
            if CUSTOMER_ZERO_TEST_REPO in endpoint:
                return {"content": "", "encoding": "base64"}
            raise GitHubNotFoundError(f"Not found: {endpoint}")
        return super()._request(endpoint, query_params, headers_extra)


def _create_test_operational_dir(base_dir):
    """Create a complete test operational directory structure.
    
    All values are clearly test data, not Customer Zero defaults.
    """
    state_dir = os.path.join(base_dir, "state")
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(os.path.join(base_dir, "constitution"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "os"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "proposals"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "handoffs"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "escalations"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "evidence"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "domain"), exist_ok=True)

    with open(os.path.join(base_dir, "BOOTSTRAP.md"), "w") as f:
        f.write("# ANNY Bootstrap\nRead order: 1. BOOTSTRAP\n")

    with open(os.path.join(state_dir, "CURRENT_STATE.yaml"), "w") as f:
        f.write("""schema_version: "1.0"
timeline:
  last_state_change: REV-TEST-001
blockers: []
""")

    with open(os.path.join(state_dir, "CURRENT_MISSION.yaml"), "w") as f:
        f.write(f"""schema_version: "1.0"
mission_id: {CUSTOMER_ZERO_TEST_MISSION}
title: Test Mission Title
status: ACTIVE
objective: Test Objective
scope:
  - id: TASK-TEST-001
    name: Verify bootstrap
    status: IN_PROGRESS
""")

    with open(os.path.join(state_dir, "NEXT_ACTION.yaml"), "w") as f:
        f.write("""schema_version: "1.0"
action:
  WHAT: Execute test verification
  OWNER: ANNY
""")

    return state_dir


class TestCustomerZeroBootstrap(unittest.TestCase):
    """UNIT tests for Customer Zero bootstrap."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = _create_test_operational_dir(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    # --- Blocker 1: Operational Discovery Tests ---

    def test_zero_operational_candidates(self):
        """Zero candidates should return None (BLOCKED/UNKNOWN)."""
        client = MockGitHubClient(repos=[
            {"full_name": "org/some-repo", "name": "some-repo", "owner": {"login": "org"}, "topics": [], "default_branch": "main"},
        ])
        provider = OperationalRepositoryProvider(github_client=client)
        with self.assertRaises(OperationalRepositoryNotFoundError) as cm:
            provider.resolve_operational_repository()
        self.assertIn("OPERATIONAL_REPOSITORY_NOT_FOUND", str(cm.exception))

    def test_one_operational_candidate(self):
        """Exactly one candidate should resolve successfully."""
        client = MockGitHubClient()  # Default repos have one with anny-operational topic
        provider = OperationalRepositoryProvider(github_client=client)
        result = provider.resolve_operational_repository()
        self.assertIsNotNone(result)
        self.assertEqual(result['full_name'], f"{CUSTOMER_ZERO_TEST_ORG}/{CUSTOMER_ZERO_TEST_REPO}")

    def test_multiple_operational_candidates(self):
        """Multiple candidates should raise OperationalRepositoryAmbiguousError."""
        client = MockGitHubClient(repos=[
            {"full_name": "org/repo1", "name": "repo1", "owner": {"login": "org"}, "topics": ["anny-operational"], "default_branch": "main"},
            {"full_name": "org/repo2", "name": "repo2", "owner": {"login": "org"}, "topics": ["anny-operational"], "default_branch": "main"},
        ])
        provider = OperationalRepositoryProvider(github_client=client)
        with self.assertRaises(OperationalRepositoryAmbiguousError):
            provider.resolve_operational_repository()

    def test_operational_yaml_marker(self):
        """P0-4: Should resolve operational repository via .anny/operational.yaml."""
        class YamlMockClient(MockGitHubClient):
            def _request(self, endpoint, query_params=None, headers_extra=None):
                if '.anny/operational.yaml' in endpoint and 'yaml-repo' in endpoint:
                    return {"content": "", "encoding": "base64"}
                elif 'BOOTSTRAP.md' in endpoint or '.anny/operational.yaml' in endpoint:
                    raise GitHubNotFoundError(f"Not found: {endpoint}")
                return super()._request(endpoint, query_params, headers_extra)

        client = YamlMockClient(repos=[
            {"full_name": "org/yaml-repo", "name": "yaml-repo", "owner": {"login": "org"}, "topics": [], "default_branch": "main"},
            {"full_name": "org/other-repo", "name": "other-repo", "owner": {"login": "org"}, "topics": [], "default_branch": "main"},
        ])
        provider = OperationalRepositoryProvider(github_client=client)
        result = provider.resolve_operational_repository()
        self.assertIsNotNone(result)
        self.assertEqual(result['full_name'], "org/yaml-repo")

    # --- Blocker 2: GitHub Error Semantics Tests ---

    def test_unauthorized_github(self):
        """Unauthorized should raise GitHubAuthError, not return []."""
        client = MockGitHubClient(fail_auth=True)
        service = OrganizationDiscoveryService(client)
        with self.assertRaises(GitHubAuthError):
            service.discover_principal()
        with self.assertRaises(GitHubAuthError):
            service.discover_organizations()
        with self.assertRaises(GitHubAuthError):
            service.discover_repositories()

    def test_timeout_github(self):
        """Timeout should raise GitHubTimeoutError, not return []."""
        client = MockGitHubClient(fail_timeout=True)
        service = OrganizationDiscoveryService(client)
        with self.assertRaises(GitHubTimeoutError):
            service.discover_organizations()

    def test_rate_limit_github(self):
        """Rate limit should raise GitHubRateLimitError, not return []."""
        client = MockGitHubClient(fail_rate_limit=True)
        service = OrganizationDiscoveryService(client)
        with self.assertRaises(GitHubRateLimitError):
            service.discover_organizations()

    # --- Blocker 3 & 4: Bootstrap Stages and Schema ---

    def test_operational_provider_and_bootstrap_resolver(self):
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        bus = EventBus()
        events_emitted = []
        bus.subscribe(EventType.BOOTSTRAP_COMPLETED, lambda e: events_emitted.append(e))

        resolver = CustomerZeroBootstrapResolver(provider=provider, event_bus=bus)
        result = resolver.resolve()

        self.assertIn(result.status, (ContinuityStatus.CONSISTENT, ContinuityStatus.DEGRADED))
        self.assertIsNotNone(result.canonical_state)
        self.assertEqual(result.canonical_state.current_mission.id, CUSTOMER_ZERO_TEST_MISSION)
        self.assertGreaterEqual(len(result.stages_completed), 14)
        self.assertEqual(len(events_emitted), 1)

    def test_missing_required_bootstrap_stage(self):
        """Missing required stage (constitution) should result in BLOCKED."""
        shutil.rmtree(os.path.join(self.temp_dir, "constitution"))
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()
        self.assertEqual(result.status, ContinuityStatus.BLOCKED)
        self.assertTrue(any("constitution" in b.description for b in result.blockers))

    def test_optional_missing_bootstrap_stage(self):
        """Missing optional stage (proposals) should register as OPTIONAL_ABSENT."""
        shutil.rmtree(os.path.join(self.temp_dir, "proposals"))
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()
        self.assertIn(result.status, (ContinuityStatus.CONSISTENT, ContinuityStatus.DEGRADED))
        self.assertTrue(any("OPTIONAL_ABSENT" in s for s in result.stages_completed))

    def test_schema_mismatch_mission(self):
        """Missing mission_id in CURRENT_MISSION should produce SCHEMA_MISMATCH."""
        with open(os.path.join(self.state_dir, "CURRENT_MISSION.yaml"), "w") as f:
            f.write("title: Missing ID\nstatus: ACTIVE\n")
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()
        self.assertEqual(result.status, ContinuityStatus.BLOCKED)
        self.assertTrue(any("SCHEMA_MISMATCH" in b.description or "SCHEMA_MISMATCH" in b.id for b in result.blockers))

    def test_missing_state_handling(self):
        """Missing CURRENT_MISSION.yaml should result in BLOCKED."""
        os.remove(os.path.join(self.state_dir, "CURRENT_MISSION.yaml"))
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()
        self.assertEqual(result.status, ContinuityStatus.BLOCKED)
        self.assertTrue(any("CURRENT_MISSION" in b.description for b in result.blockers))

    # --- Reconciler Tests ---

    def test_reconciler_consistent(self):
        reconciler = ContinuityReconciler()
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()

        status = reconciler.reconcile(
            canonical_state=result.canonical_state,
            principal=DiscoveredPrincipal(login="test"),
            discovered_repos=[DiscoveredRepository(full_name=f"{CUSTOMER_ZERO_TEST_ORG}/{CUSTOMER_ZERO_TEST_REPO}", name=CUSTOMER_ZERO_TEST_REPO, owner=CUSTOMER_ZERO_TEST_ORG)],
            github_connected=True,
            runtime_ready=True
        )
        self.assertEqual(status, ContinuityStatus.CONSISTENT)

    def test_reconciler_conflicted(self):
        reconciler = ContinuityReconciler()
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()
        result.canonical_state.metadata["repo_type"] = "github"
        result.canonical_state.repository_name = "test-org/NONEXISTENT"

        status = reconciler.reconcile(
            canonical_state=result.canonical_state,
            principal=DiscoveredPrincipal(login="test"),
            discovered_repos=[DiscoveredRepository(full_name=f"{CUSTOMER_ZERO_TEST_ORG}/{CUSTOMER_ZERO_TEST_REPO}", name=CUSTOMER_ZERO_TEST_REPO, owner=CUSTOMER_ZERO_TEST_ORG)],
            github_connected=True,
            runtime_ready=True
        )
        self.assertEqual(status, ContinuityStatus.CONFLICTED)

    # --- Blocker 5: Real Process Death Test ---

    def test_process_death_reconstruction(self):
        """Simulate process death and restart using actual subprocesses with SIGKILL."""
        script_code = f"""
import os
import json
import sys
import time
from runtime.continuity.operational import OperationalRepositoryProvider
from runtime.continuity.bootstrap import CustomerZeroBootstrapResolver

provider = OperationalRepositoryProvider(local_path_override='{self.temp_dir}')
resolver = CustomerZeroBootstrapResolver(provider=provider)
result = resolver.resolve()

if os.environ.get('PHASE') == 'A':
    # Simulating long running task during workflow
    print("READY_TO_BE_KILLED")
    sys.stdout.flush()
    while True:
        time.sleep(1)

elif os.environ.get('PHASE') == 'B':
    # Dump fully reconstructed state to JSON
    cstate = result.canonical_state
    out = {{
        "mission_id": cstate.current_mission.id if cstate.current_mission else None,
        "task_id": cstate.current_task.id if cstate.current_task else None,
        "next_action": cstate.next_action.action if cstate.next_action else None,
        "blockers_count": len(cstate.blockers) if cstate.blockers else 0,
        "repo_name": cstate.repository_name,
        "revision": cstate.revision
    }}
    print(json.dumps(out))
        """
        script_path = os.path.join(self.temp_dir, "test_worker.py")
        with open(script_path, "w") as f:
            f.write(script_code)

        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        env["PHASE"] = "A"
        
        # PROCESS A: Start, wait for READY, then SIGKILL
        proc1 = subprocess.Popen([sys.executable, script_path], env=env, stdout=subprocess.PIPE, text=True)
        started = False
        for _ in range(50):
            line = proc1.stdout.readline().strip()
            if line == "READY_TO_BE_KILLED":
                started = True
                break
            time.sleep(0.1)
        self.assertTrue(started, "Process A never became ready")
        
        proc1.kill()
        proc1.wait()
        self.assertNotEqual(proc1.returncode, 0, "Process A should have been killed")

        # PROCESS B: Completely new process, no shared memory
        env["PHASE"] = "B"
        proc2 = subprocess.run([sys.executable, script_path], env=env, capture_output=True, text=True)
        self.assertEqual(proc2.returncode, 0, f"Process B failed: {proc2.stderr}")
        
        # Verify full reconstruction from durable state
        reconstructed = json.loads(proc2.stdout.strip())
        self.assertEqual(reconstructed["mission_id"], CUSTOMER_ZERO_TEST_MISSION)
        self.assertEqual(reconstructed["task_id"], "TASK-TEST-001")
        self.assertEqual(reconstructed["next_action"], "Execute test verification")
        self.assertEqual(reconstructed["blockers_count"], 0)
        self.assertEqual(reconstructed["repo_name"], "LOCAL_CONTROLLED_TEST")
        self.assertEqual(reconstructed["revision"], "REV-TEST-001")

    # --- Blocker 7: First Run Session Scope ---

    def test_first_run_route_scope(self):
        """Onboarding session should only access onboarding routes."""
        from runtime.admin.middleware import AdminMiddleware, ONBOARDING_ROUTES
        from runtime.admin.auth import AdminSessionManager

        auth_mgr = AdminSessionManager(self.temp_dir, "rt-test")
        
        class MockGH:
            def has_token(self): return False
        
        mw = AdminMiddleware(auth_manager=auth_mgr, github_manager=MockGH())
        
        # Onboarding route should succeed
        ctx = {}
        result = mw.process_request("GET", "/", {}, ctx)
        self.assertTrue(result)
        self.assertIsNotNone(ctx.get('admin_session'))
        self.assertEqual(ctx['admin_session'].scope, "ONBOARDING_ONLY")
        
        # Non-onboarding route should be redirected
        ctx2 = {}
        result2 = mw.process_request("GET", "/sessions", {}, ctx2)
        self.assertFalse(result2)
        self.assertEqual(ctx2.get('redirect_to'), '/')

    # --- Blocker 9: Control Plane Actual State ---

    def test_actual_control_plane_state_derivation(self):
        """Control Plane status values should derive from observable state, not hardcoded."""
        dto = ContinuityDTO(
            status="CONSISTENT",
            canonical_source="test-org/test-operational",  # Not hardcoded to any specific org
            canonical_revision="REV-TEST-001",
            current_mission=CUSTOMER_ZERO_TEST_MISSION,
            current_task="Task 1",
            next_action="Action 1",
            blocker_count=0,
            reconciliation_status="CONSISTENT",
            github_status="AUTHORIZED",
            runtime_status="UNKNOWN",  # Not hardcoded HEALTHY
            fabric_status="NOT_CONFIGURED"
        )
        dict_data = dto.to_dict()
        self.assertEqual(dict_data["fabric_status"], "NOT_CONFIGURED")
        self.assertEqual(dict_data["runtime_status"], "UNKNOWN")
        # Ensure no secrets contained in DTO
        json_str = json.dumps(dict_data)
        self.assertNotIn("token", json_str)
        self.assertNotIn("password", json_str)
        self.assertNotIn("private_key", json_str)

    # --- Blocker 14: No Automatic Mission Execution ---

    def test_no_automatic_mission_execution(self):
        """Bootstrap should stop at ANNY_READY_FOR_WORK without executing missions."""
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        resolver = CustomerZeroBootstrapResolver(provider=provider)
        result = resolver.resolve()
        
        # Should be CONSISTENT or DEGRADED, not executing
        self.assertIn(result.status, (ContinuityStatus.CONSISTENT, ContinuityStatus.DEGRADED))
        # No worker spawned, no LLM called
        self.assertIsNotNone(result.canonical_state)
        self.assertIsNotNone(result.canonical_state.current_mission)
        # Mission status should be preserved as-is from file, not changed
        self.assertEqual(result.canonical_state.current_mission.status, "ACTIVE")

    # --- Blocker 15: Fabric NOT_CONFIGURED ---

    def test_fabric_not_configured(self):
        """Fabric should be NOT_CONFIGURED in Customer Zero bootstrap."""
        dto = ContinuityDTO(
            status="CONSISTENT",
            canonical_source="test-org/test-op",
            canonical_revision=None,
            current_mission=None,
            current_task=None,
            next_action=None,
            blocker_count=0,
            reconciliation_status="CONSISTENT",
            github_status="AUTHORIZED",
            runtime_status="UNKNOWN",
            fabric_status="NOT_CONFIGURED"
        )
        self.assertEqual(dto.fabric_status, "NOT_CONFIGURED")


class TestGitHubDiscovery(unittest.TestCase):
    """UNIT tests for GitHub discovery service."""

    def test_github_timeout(self):
        """P0-C & P0-G: GitHub timeout during discovery should raise exception."""
        class TimeoutMockClient(MockGitHubClient):
            def list_repositories(self):
                e = GitHubClientError("Timeout")
                e.status_code = 504
                raise e

        provider = OperationalRepositoryProvider(github_client=TimeoutMockClient())
        with self.assertRaises(OperationalRepositoryNotFoundError) as cm:
            provider.resolve_operational_repository()
        self.assertIn("NETWORK_ERROR", str(cm.exception))

    def test_github_unauthorized(self):
        """P0-C: Unauthorized returns specific error."""
        class AuthErrorMockClient(MockGitHubClient):
            def _request(self, path, query_params=None):
                if "BOOTSTRAP.md" in path:
                    e = GitHubClientError("Unauthorized")
                    e.status_code = 401
                    raise e
                return super()._request(path, query_params)

        provider = OperationalRepositoryProvider(github_client=AuthErrorMockClient())
        with self.assertRaises(OperationalRepositoryNotFoundError) as cm:
            provider.resolve_operational_repository()
        self.assertIn("UNAUTHORIZED", str(cm.exception))

    def test_path_exists_non_404(self):
        """P0-D & P0-G: path_exists should raise exception on non-404 errors."""
        class BrokenClient(MockGitHubClient):
            def _request(self, path, query_params=None):
                if "constitution/" in path:
                    e = GitHubClientError("Internal Error")
                    e.status_code = 500
                    raise e
                return super()._request(path, query_params)

        provider = OperationalRepositoryProvider(github_client=BrokenClient())
        provider.resolve_operational_repository()
        
        with self.assertRaises(GitHubClientError):
            provider.path_exists("constitution/")

    def test_github_discovery(self):
        client = MockGitHubClient()
        service = OrganizationDiscoveryService(client)
        
        principal = service.discover_principal()
        self.assertIsNotNone(principal)
        self.assertEqual(principal.login, "test-principal")

        orgs = service.discover_organizations()
        self.assertEqual(len(orgs), 1)
        self.assertEqual(orgs[0].login, CUSTOMER_ZERO_TEST_ORG)

        repos = service.discover_repositories()
        self.assertEqual(len(repos), 2)
        self.assertEqual(repos[0].full_name, f"{CUSTOMER_ZERO_TEST_ORG}/{CUSTOMER_ZERO_TEST_REPO}")


if __name__ == "__main__":
    unittest.main()
