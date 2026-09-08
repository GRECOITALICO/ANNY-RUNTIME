"""Customer Zero Bootstrap verification test suite."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from runtime.events.bus import EventBus, EventType
from runtime.github.client import (
    GitHubClient,
    GitHubAuthError,
    GitHubNotFoundError,
)
from runtime.github.discovery import (
    OrganizationDiscoveryService,
    DiscoveredPrincipal,
    DiscoveredOrganization,
    DiscoveredRepository,
)
from runtime.continuity.operational import OperationalRepositoryProvider
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


class MockGitHubClient(GitHubClient):
    """Mock GitHub Client for testing without network."""

    def __init__(self, fail_auth: bool = False, fail_not_found: bool = False):
        super().__init__()
        self.fail_auth = fail_auth
        self.fail_not_found = fail_not_found

    def get_authenticated_principal(self):
        if self.fail_auth:
            raise GitHubAuthError("Unauthorized token")
        return {"login": "test-principal", "type": "User", "id": 12345}

    def list_organizations(self):
        if self.fail_auth:
            raise GitHubAuthError("Unauthorized token")
        return [{"login": "GRECOITALICO", "description": "Greco Italico Org", "public_repos": 10}]

    def list_repositories(self, org=None):
        if self.fail_auth:
            raise GitHubAuthError("Unauthorized token")
        return [
            {"full_name": "GRECOITALICO/ANNY-OPERATIONAL", "name": "ANNY-OPERATIONAL", "owner": {"login": "GRECOITALICO"}, "private": True, "archived": False, "default_branch": "main"},
            {"full_name": "GRECOITALICO/ANNY-RUNTIME", "name": "ANNY-RUNTIME", "owner": {"login": "GRECOITALICO"}, "private": False, "archived": False, "default_branch": "main"},
            {"full_name": "GRECOITALICO/CONRRAD-CORE", "name": "CONRRAD-CORE", "owner": {"login": "GRECOITALICO"}, "private": True, "archived": False, "default_branch": "main"},
        ]

    def get_repository(self, owner, repo):
        if self.fail_not_found:
            raise GitHubNotFoundError("Not found")
        return {"full_name": f"{owner}/{repo}", "default_branch": "main"}


class TestCustomerZeroBootstrap(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = os.path.join(self.temp_dir, "state")
        os.makedirs(self.state_dir, exist_ok=True)

        # Create mock BOOTSTRAP.md
        with open(os.path.join(self.temp_dir, "BOOTSTRAP.md"), "w") as f:
            f.write("# ANNY Bootstrap\nRead order: 1. BOOTSTRAP\n")

        # Create mock state files
        with open(os.path.join(self.state_dir, "CURRENT_STATE.yaml"), "w") as f:
            f.write("""schema_version: "1.0"
timeline:
  last_state_change: REV-001
  current_mission: MISSION-058-TEST
blockers: []
next_action: MISSION-058_EXECUTION
""")

        with open(os.path.join(self.state_dir, "CURRENT_MISSION.yaml"), "w") as f:
            f.write("""schema_version: "1.0"
mission_id: MISSION-058-TEST
title: Test Mission Title
status: ACTIVE
objective: Test Objective
scope:
  - Task 1: Verify bootstrap
""")

        with open(os.path.join(self.state_dir, "NEXT_ACTION.yaml"), "w") as f:
            f.write("""schema_version: "1.0"
action:
  WHAT: Execute test verification
  OWNER: ANNY
""")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_github_discovery(self):
        client = MockGitHubClient()
        service = OrganizationDiscoveryService(client)
        
        principal = service.discover_principal()
        self.assertIsNotNone(principal)
        self.assertEqual(principal.login, "test-principal")

        orgs = service.discover_organizations()
        self.assertEqual(len(orgs), 1)
        self.assertEqual(orgs[0].login, "GRECOITALICO")

        repos = service.discover_repositories()
        self.assertEqual(len(repos), 3)
        self.assertEqual(repos[0].full_name, "GRECOITALICO/ANNY-OPERATIONAL")

    def test_operational_provider_and_bootstrap_resolver(self):
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        bus = EventBus()
        events_emitted = []
        bus.subscribe(EventType.BOOTSTRAP_COMPLETED, lambda e: events_emitted.append(e))

        resolver = CustomerZeroBootstrapResolver(provider=provider, event_bus=bus)
        result = resolver.resolve()

        self.assertIn(result.status, (ContinuityStatus.CONSISTENT, ContinuityStatus.DEGRADED))
        self.assertIsNotNone(result.canonical_state)
        self.assertEqual(result.canonical_state.current_mission.id, "MISSION-058-TEST")
        self.assertGreaterEqual(len(result.stages_completed), 14)
        self.assertEqual(len(events_emitted), 1)

    def test_reconciler_consistent(self):
        reconciler = ContinuityReconciler()
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()

        status = reconciler.reconcile(
            canonical_state=result.canonical_state,
            principal=DiscoveredPrincipal(login="test"),
            discovered_repos=[DiscoveredRepository(full_name="GRECOITALICO/ANNY-OPERATIONAL", name="ANNY-OPERATIONAL", owner="GRECOITALICO")],
            github_connected=True,
            runtime_ready=True
        )
        self.assertEqual(status, ContinuityStatus.CONSISTENT)

    def test_reconciler_conflicted(self):
        reconciler = ContinuityReconciler()
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()
        result.canonical_state.metadata["repo_type"] = "github"
        result.canonical_state.repository_name = "GRECOITALICO/NONEXISTENT"

        status = reconciler.reconcile(
            canonical_state=result.canonical_state,
            principal=DiscoveredPrincipal(login="test"),
            discovered_repos=[DiscoveredRepository(full_name="GRECOITALICO/ANNY-OPERATIONAL", name="ANNY-OPERATIONAL", owner="GRECOITALICO")],
            github_connected=True,
            runtime_ready=True
        )
        self.assertEqual(status, ContinuityStatus.CONFLICTED)

    def test_missing_state_handling(self):
        # Remove CURRENT_MISSION.yaml
        os.remove(os.path.join(self.state_dir, "CURRENT_MISSION.yaml"))
        provider = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        result = CustomerZeroBootstrapResolver(provider=provider).resolve()

        self.assertEqual(result.status, ContinuityStatus.BLOCKED)
        self.assertTrue(any("CURRENT_MISSION" in b.description for b in result.blockers))

    def test_process_death_reconstruction(self):
        """Simulate process death and restart: operational state must resolve identically."""
        provider1 = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        res1 = CustomerZeroBootstrapResolver(provider=provider1).resolve()

        # "Process Death" -> clear references, instantiate fresh provider & resolver
        provider2 = OperationalRepositoryProvider(local_path_override=self.temp_dir)
        res2 = CustomerZeroBootstrapResolver(provider=provider2).resolve()

        self.assertEqual(res1.canonical_state.current_mission.id, res2.canonical_state.current_mission.id)
        self.assertEqual(res1.canonical_state.next_action.action, res2.canonical_state.next_action.action)

    def test_dto_fabric_not_configured(self):
        dto = ContinuityDTO(
            status="CONSISTENT",
            canonical_source="GRECOITALICO/ANNY-OPERATIONAL",
            canonical_revision="REV-001",
            current_mission="MISSION-058",
            current_task="Task 1",
            next_action="Action 1",
            blocker_count=0,
            reconciliation_status="CONSISTENT",
            github_status="AUTHORIZED",
            runtime_status="HEALTHY",
            fabric_status="NOT_CONFIGURED"
        )
        dict_data = dto.to_dict()
        self.assertEqual(dict_data["fabric_status"], "NOT_CONFIGURED")
        # Ensure no secrets contained in DTO
        json_str = json.dumps(dict_data)
        self.assertNotIn("token", json_str)
        self.assertNotIn("password", json_str)
        self.assertNotIn("private_key", json_str)


if __name__ == "__main__":
    unittest.main()
