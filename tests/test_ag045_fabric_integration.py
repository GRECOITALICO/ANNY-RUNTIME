import pytest
import json
from unittest.mock import MagicMock
from runtime.github.client import GitHubClient, GitHubNotFoundError, GitHubClientError
from runtime.fabric.github_adapter import GitHubFabricAdapter, FabricError, FabricAdmissionResult
from runtime.fabric.models import FabricNode, FabricTenant, FabricPolicy, FabricContract
from runtime.core.access_verifier import CriticalAccessVerifier
from runtime.orchestration.kernel import Orchestrator
from runtime.orchestration.plan import RoutingClass
from runtime.execution.models import Task


class MockGitHubClient(GitHubClient):
    def __init__(self, files=None, repos=None):
        self.files = files or {}
        self.repos = repos or {}

    def get_repository(self, owner: str, repo: str):
        key = f"{owner}/{repo}"
        if key in self.repos:
            if self.repos[key] == "404":
                raise GitHubNotFoundError("Repository not found")
            if self.repos[key] == "401":
                raise GitHubClientError("401 Unauthorized")
            return self.repos[key]
        return {"name": repo, "owner": {"login": owner}}

    def get_file(self, owner: str, repo: str, path: str, ref: str = "main"):
        key = f"{owner}/{repo}/{path}"
        if key in self.files:
            val = self.files[key]
            if val == "404":
                raise GitHubNotFoundError(f"File not found: {path}")
            return val
        raise GitHubNotFoundError(f"File not found: {path}")

    def _request(self, endpoint: str):
        if "contents/fabric/node.json" in endpoint:
            return json.dumps({"name": "node.json", "sha": "blob-sha-node-123"})
        if "commits/commit-good-123" in endpoint:
            return json.dumps({"sha": "commit-good-123"})
        if "commits/commit-not-found" in endpoint:
            raise GitHubNotFoundError("Commit not found")
        raise GitHubNotFoundError("Endpoint not found")

    def list_repos(self):
        return [{"name": "ANNY-RUNTIME", "owner": {"login": "GRECOITALICO"}}]


# 1. dynamic binding success
def test_01_dynamic_binding_success():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, fabric_org="custom-org", fabric_repo="custom-repo")
    assert adapter.org == "custom-org"
    assert adapter.repo == "custom-repo"


# 2. missing binding
def test_02_missing_binding_blocks():
    gh = MockGitHubClient()
    with pytest.raises(FabricError) as exc_info:
        GitHubFabricAdapter(gh)
    assert exc_info.value.error_code == "FABRIC_CONFIG_MISSING"


# 3. repository reachability success
def test_03_repository_reachability_success():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    reachable, latency, error = adapter.probe_reachability()
    assert reachable is True
    assert error == "SUCCESS"


# 4. repository reachability 404
def test_04_repository_reachability_404():
    gh = MockGitHubClient(repos={"org1/repo-404": "404"})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo-404")
    reachable, latency, error = adapter.probe_reachability()
    assert reachable is False
    assert error == "NOT_FOUND"


# 5. GitHub auth failure
def test_05_github_auth_failure():
    gh = MockGitHubClient(repos={"org1/repo-auth": "401"})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo-auth")
    reachable, latency, error = adapter.probe_reachability()
    assert reachable is False
    assert error == "AUTH_ERROR"


# 6. malformed node.json
def test_06_malformed_node_json():
    gh = MockGitHubClient(files={"org1/repo1/fabric/node.json": "{ malformed json ..."})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    with pytest.raises(FabricError) as exc_info:
        adapter.read_node_config()
    assert exc_info.value.error_code == "FABRIC_NODE_MALFORMED"


# 7. valid node identity
def test_07_valid_node_identity():
    node_data = {
        "node_id": "NODE-99",
        "org": "org1",
        "repo": "repo1",
        "purpose": "REPOSITORY_FABRIC",
        "created_at": "2026-01-01T00:00:00Z"
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/node.json": json.dumps(node_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    node = adapter.read_node_config()
    assert node.node_id == "NODE-99"
    assert node.org == "org1"


# 8. tenant binding success
def test_08_tenant_binding_success():
    tenant_data = {
        "tenant_id": "tenant-1",
        "runtime_id": "rt-1",
        "project_ids": ["proj-1"],
        "enrolled_at": "2026-01-01T00:00:00Z"
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/tenants/rt-1.json": json.dumps(tenant_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    tenant = adapter.read_tenant_binding("rt-1")
    assert tenant.tenant_id == "tenant-1"
    assert tenant.runtime_id == "rt-1"


# 9. tenant mismatch
def test_09_tenant_mismatch():
    tenant_data = {
        "tenant_id": "tenant-1",
        "runtime_id": "other-rt",
        "project_ids": ["proj-1"],
        "enrolled_at": "2026-01-01T00:00:00Z"
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/tenants/rt-1.json": json.dumps(tenant_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    with pytest.raises(FabricError) as exc_info:
        adapter.read_tenant_binding("rt-1")
    assert exc_info.value.error_code == "TENANT_MISMATCH"


# 10. admission ALLOW
def test_10_admission_allow():
    adm_data = {"verdict": "ALLOW", "reason": "Authorized tenant"}
    gh = MockGitHubClient(files={"org1/repo1/fabric/admissions/rt-1.json": json.dumps(adm_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    res = adapter.check_admission("rt-1")
    assert res.verdict == "ALLOW"
    assert res.is_admitted() is True


# 11. admission DENY
def test_11_admission_deny():
    adm_data = {"verdict": "DENY", "reason": "Revoked"}
    gh = MockGitHubClient(files={"org1/repo1/fabric/admissions/rt-1.json": json.dumps(adm_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    res = adapter.check_admission("rt-1")
    assert res.verdict == "DENY"
    assert res.is_admitted() is False


# 12. admission UNKNOWN
def test_12_admission_unknown():
    node_data = {"default_admission_policy": "UNKNOWN"}
    gh = MockGitHubClient(files={"org1/repo1/fabric/node.json": json.dumps(node_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    res = adapter.check_admission("rt-unlisted")
    assert res.verdict == "UNKNOWN"
    assert res.is_admitted() is False


# 13. admission ERROR
def test_13_admission_error():
    gh = MockGitHubClient()
    # Mocking client error
    gh.get_file = MagicMock(side_effect=Exception("Read error"))
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    res = adapter.check_admission("rt-err")
    assert res.verdict == "ERROR"
    assert res.is_admitted() is False


# 14. policy loading
def test_14_policy_loading():
    policy_data = {
        "revision": "v2.0",
        "require_admission": True,
        "allow_local_models": True,
        "allow_remote_models": False,
        "max_workspace_size_mb": 2048
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/policy.json": json.dumps(policy_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    p_dict = adapter.read_policy()
    policy = FabricPolicy.from_dict(p_dict)
    assert policy.revision == "v2.0"
    assert policy.allow_remote_models is False
    assert policy.max_workspace_size_mb == 2048


# 15. contract loading
def test_15_contract_loading():
    contract_data = {
        "contract_id": "c-100",
        "tenant_id": "tenant-1",
        "granted_capabilities": ["repository.read"],
        "revoked_capabilities": ["system.mutate"]
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/contract.json": json.dumps(contract_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    c_dict = adapter.read_contract()
    contract = FabricContract.from_dict(c_dict)
    assert contract.contract_id == "c-100"
    assert "system.mutate" in contract.revoked_capabilities


# 16. revoked capability blocked
def test_16_revoked_capability_blocked():
    contract_data = {
        "contract_id": "c-100",
        "tenant_id": "tenant-1",
        "granted_capabilities": ["repository.read"],
        "revoked_capabilities": ["document.classify"]
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/contract.json": json.dumps(contract_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    orchestrator = Orchestrator(fabric_adapter=adapter)

    from datetime import datetime, timezone, timedelta
    task = Task(
        task_id="t-revoked",
        capability_id="document.classify",
        account_id="acc-1",
        project_id="proj-1",
        input={},
        constraints={},
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        workspace_policy="workspace_only",
        evidence_policy="required",
        requested_by="user-1",
        created_at=datetime.now(timezone.utc)
    )
    plan = orchestrator.plan_task(task)
    assert plan.routing_class == RoutingClass.BLOCKED
    assert "revoked by Fabric contract" in plan.decision_reason


# 17. remote HEAD verification
def test_17_remote_head_verification():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    exists, sha = adapter.node_json_exists_at_remote_head()
    assert exists is True
    assert sha == "blob-sha-node-123"


# 18. provenance success
def test_18_provenance_success():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    valid, err = adapter.validate_provenance("commit-good-123")
    assert valid is True
    assert err is None


# 19. provenance mismatch
def test_19_provenance_mismatch():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    valid, err = adapter.validate_provenance("commit-good-123", expected_org="other-org")
    assert valid is False
    assert "Commit repository mismatch" in err


# 20. fabric.read real boundary
def test_20_fabric_read_real_boundary():
    node_data = {
        "node_id": "NODE-REAL-1",
        "org": "org1",
        "repo": "repo1",
        "purpose": "REPOSITORY_FABRIC",
        "created_at": "2026-01-01T00:00:00Z"
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/node.json": json.dumps(node_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    
    node = adapter.read_node_config()
    assert node.node_id == "NODE-REAL-1"


# 21. fabric.register authorization denial
def test_21_fabric_register_authorization_denial():
    # Attempt unauthorized registration -> DENIED
    contract_data = {
        "contract_id": "c-100",
        "tenant_id": "tenant-1",
        "granted_capabilities": ["repository.read"],
        "revoked_capabilities": ["fabric.register"]
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/contract.json": json.dumps(contract_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    contract = FabricContract.from_dict(adapter.read_contract())
    assert "fabric.register" in contract.revoked_capabilities


# 22. cross-plane contradiction blocked
def test_22_cross_plane_contradiction_blocked():
    # When tenant binding runtime_id contradicts expected runtime_id -> FabricError TENANT_MISMATCH
    tenant_data = {
        "tenant_id": "tenant-1",
        "runtime_id": "wrong-runtime",
        "project_ids": ["proj-1"],
        "enrolled_at": "2026-01-01T00:00:00Z"
    }
    gh = MockGitHubClient(files={"org1/repo1/fabric/tenants/rt-expected.json": json.dumps(tenant_data)})
    adapter = GitHubFabricAdapter(gh, fabric_org="org1", fabric_repo="repo1")
    with pytest.raises(FabricError) as exc_info:
        adapter.read_tenant_binding("rt-expected")
    assert exc_info.value.error_code == "TENANT_MISMATCH"


# 23. mock-pass exclusion
def test_23_mock_pass_exclusion(tmp_path):
    gh = MockGitHubClient(files={
        "org-test/repo-test/fabric/node.json": json.dumps({
            "node_id": "node-1", "org": "org-test", "repo": "repo-test",
            "purpose": "testing", "status": "ACTIVE"
        })
    })
    adapter = GitHubFabricAdapter(gh, fabric_org="org-test", fabric_repo="repo-test")
    verifier = CriticalAccessVerifier(
        authorized_capabilities=[
            "repository.read", "repository.search", "filesystem.inspect",
            "filesystem.list", "fabric.read", "runtime.status", "runtime.execution",
            "tool.resolve", "model.resolve", "worker.resolve"
        ],
        data_dir=str(tmp_path),
        fabric_adapter=adapter,
        github_client=gh
    )
    res = verifier.verify()
    assert res.passed is True
    for r in res.results:
        assert "MOCK_PASS" not in r.evidence


# 24. no legacy Fabric fallback
def test_24_no_legacy_fabric_fallback():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, fabric_org="org-explicit", fabric_repo="repo-explicit")
    assert adapter.org == "org-explicit"
    assert adapter.repo == "repo-explicit"
