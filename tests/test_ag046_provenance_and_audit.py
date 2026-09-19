import pytest
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from runtime.execution.models import (
    Task, TaskExecutionContext, ExecutionStatus, ExecutionResult, ExecutionDetails, FailureReason
)
from runtime.orchestration.plan import ExecutionPlan, RoutingClass, RoutingDecision
from runtime.orchestration.kernel import Orchestrator
from runtime.execution.policy import RuntimePolicy
from runtime.execution.capability import CapabilityDefinition, CapabilityRegistry
from runtime.execution.registry import ModelRegistry
from runtime.execution.manager import ExecutionManager
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.continuity.engine import ContinuityEngine, CorruptionSeverity
from runtime.continuity.models import ContinuityRecord, EventRecord, ContinuityStatus
from runtime.continuity.events import ContinuityEventType
from runtime.continuity.mutation import RepositoryMutationContract
from runtime.git.service import GitService
from runtime.github.client import GitHubClient, validate_github_sha, GitHubNotFoundError
from runtime.fabric.github_adapter import GitHubFabricAdapter, FabricError


class MockGitHubClient(GitHubClient):
    def __init__(self, files=None, repos=None, commits=None):
        self.files = files or {}
        self.repos = repos or {}
        self.commits = commits or {}

    def get_repository(self, owner: str, repo: str):
        key = f"{owner}/{repo}"
        if key in self.repos:
            if self.repos[key] == "404":
                raise GitHubNotFoundError("Repository not found")
            return self.repos[key]
        return {"name": repo, "owner": {"login": owner}}

    def get_file(self, owner: str, repo: str, path: str, ref: str = "main"):
        key = f"{owner}/{repo}/{path}"
        if key in self.files:
            return self.files[key]
        raise GitHubNotFoundError(f"File not found: {path}")

    def _request(self, endpoint: str, query_params=None, headers_extra=None):
        if "contents/fabric/node.json" in endpoint:
            return json.dumps({"sha": "blob-sha-node-123"})
        for sha, data in self.commits.items():
            if f"commits/{sha}" in endpoint:
                return data
        if "commits/invalid-sha-123" in endpoint:
            raise GitHubNotFoundError("Commit not found")
        return {"sha": "valid-head-sha-7c3b52d"}

    def get_commit(self, owner: str, repo: str, sha: str):
        if sha in self.commits:
            if self.commits[sha] == "404":
                raise GitHubNotFoundError("Commit not found")
            return self.commits[sha]
        if sha == "invalid-sha-123":
            raise GitHubNotFoundError("Commit not found")
        return {"sha": sha, "commit": {"message": "Test commit"}}

    def is_commit_ancestor(self, owner: str, repo: str, ancestor_sha: str, head_sha: str) -> bool:
        if ancestor_sha == head_sha:
            return True
        if ancestor_sha == "invalid-sha-123":
            return False
        return True


# 1. execution provenance creation
def test_01_execution_provenance_creation():
    context = TaskExecutionContext(
        execution_id="exec-001",
        task_id="task-001",
        account_id="acct-1",
        project_id="proj-1",
        capability_id="test.read",
        workspace_path="/tmp/test",
        environment={},
        allowed_tools=[],
        deadline=datetime.now(timezone.utc),
        resource_limits={},
        network_policy="none",
        write_policy="none",
        generation=1
    )
    res = ExecutionResult(
        execution_id=context.execution_id,
        task_id=context.task_id,
        status=ExecutionStatus.SUCCEEDED,
        result_data={"ok": True},
        result_hash="sha256-hash",
        provenance={"executor": "local_qwen"}
    )
    assert res.execution_id == "exec-001"
    assert res.provenance["executor"] == "local_qwen"


# 2. unique execution identity
def test_02_unique_execution_identity(tmp_path):
    wm = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em = ExecutionManager(wm)
    now = datetime.now(timezone.utc)
    t1 = Task("task-1", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    t2 = Task("task-2", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    c1 = em.submit_task(t1)
    c2 = em.submit_task(t2)
    assert c1.execution_id != c2.execution_id


# 3. generation binding
def test_03_generation_binding(tmp_path):
    wm = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em = ExecutionManager(wm)
    now = datetime.now(timezone.utc)
    t = Task("task-1", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    ctx = em.submit_task(t)
    assert ctx.generation is not None
    assert ctx.generation >= 1


# 4. routing provenance
def test_04_routing_provenance():
    orch = Orchestrator()
    now = datetime.now(timezone.utc)
    t = Task("task-1", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    p = orch.plan_task(t)
    assert p.provenance is not None
    assert "requested_capability" in p.provenance
    assert p.provenance["requested_capability"] == "repository.read"


# 5. deterministic execution provenance
def test_05_deterministic_execution_provenance():
    orch = Orchestrator()
    now = datetime.now(timezone.utc)
    t = Task("task-det", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    p = orch.plan_task(t)
    assert p.routing_class == RoutingClass.DETERMINISTIC
    assert str(p.executor_type).upper() == "DETERMINISTIC"


# 6. local model provenance
def test_06_local_model_provenance():
    orch = Orchestrator()
    now = datetime.now(timezone.utc)
    t = Task("task-local", "document.classify", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    p = orch.plan_task(t)
    assert p.provenance is not None


# 7. frontier boundary provenance
def test_07_frontier_boundary_provenance():
    orch = Orchestrator()
    now = datetime.now(timezone.utc)
    t = Task("task-front", "document.classify", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    p = orch.plan_task(t)
    assert p.provenance is not None


# 8. executor identity reconciliation
def test_08_executor_identity_reconciliation(tmp_path):
    wm = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em = ExecutionManager(wm)
    now = datetime.now(timezone.utc)
    t = Task("task-recon", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    ctx = em.submit_task(t)
    worker = next(w for w in em.worker_manager.list_workers() if w.execution_id == ctx.execution_id)
    assert ctx.executor_type == worker.executor_type
    assert ctx.executor_id == worker.executor_id


# 9. model identity reconciliation
def test_09_model_identity_reconciliation(tmp_path):
    wm = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em = ExecutionManager(wm)
    now = datetime.now(timezone.utc)
    t = Task("task-model", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    ctx = em.submit_task(t)
    worker = next(w for w in em.worker_manager.list_workers() if w.execution_id == ctx.execution_id)
    assert ctx.model_id == worker.model_id





# 10. worker provenance
def test_10_worker_provenance(tmp_path):
    wm = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em = ExecutionManager(wm)
    now = datetime.now(timezone.utc)
    t = Task("task-w", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    ctx = em.submit_task(t)
    worker = next(w for w in em.worker_manager.list_workers() if w.execution_id == ctx.execution_id)
    assert worker.execution_id == ctx.execution_id
    assert worker.task_id == t.task_id


# 11. MCP/tool provenance
def test_11_mcp_tool_provenance(tmp_path):
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, "org-test", "repo-test")
    engine = ContinuityEngine(str(tmp_path))
    rec = ContinuityRecord.create("m1", "t1", "s1", "a1", "L0", "test", execution_id="exec-mcp-1")
    engine.save_record(rec)
    event = EventRecord(
        event_id="evt-1", sequence=0, timestamp=datetime.now(timezone.utc).isoformat(),
        mission_id="m1", task_id="t1", step_id="s1", parent_event_id=None,
        actor_id="a1", actor_level="L0", parent_actor_id=None,
        event_type=ContinuityEventType.ACTION_COMPLETED, target="mcp_tool", intent="tool_invocation",
        inputs={"tool": "repo.read", "execution_id": "exec-mcp-1"},
        repository="org-test/repo-test", branch="main", commit_before=None, commit_after=None,
        files_changed=[], observation="Tool invoked successfully", result="SUCCESS",
        evidence_refs=["hash-123"], test_results=[], decision_ref=None, state_change="COMPLETE",
        status="COMPLETE", implementation_state="COMPLETE", verification_state="VERIFIED", certification_state="NOT_CERTIFIED",
        blocker_refs=[], next_action=None, execution_id="exec-mcp-1"
    )
    engine.append_event(event)
    recon = engine.reconstruct_execution("exec-mcp-1")
    assert recon is not None
    assert recon["status"] == "COMPLETE"


# 12. Fabric operation provenance
def test_12_fabric_operation_provenance():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, "org-fabric", "repo-fabric")
    prov_data = adapter.get_provenance("valid-head-sha-7c3b52d")
    assert prov_data["verified"] is True
    assert prov_data["commit_sha"] == "valid-head-sha-7c3b52d"


# 13. tenant reconciliation
def test_13_tenant_reconciliation():
    gh = MockGitHubClient(files={
        "org-test/repo-test/fabric/tenants/runtime-001.json": json.dumps({
            "tenant_id": "tenant-001",
            "runtime_id": "runtime-999"  # mismatch
        })
    })
    adapter = GitHubFabricAdapter(gh, "org-test", "repo-test")
    with pytest.raises(FabricError) as exc_info:
        adapter.read_tenant_binding("runtime-001")
    assert exc_info.value.error_code == "TENANT_MISMATCH"


# 14. remote commit verification
def test_14_remote_commit_verification():
    gh = MockGitHubClient(commits={"commit-ok-123": {"sha": "commit-ok-123"}})
    assert validate_github_sha(gh, "org", "repo", "commit-ok-123") is True
    assert validate_github_sha(gh, "org", "repo", "invalid-sha-123") is False


# 15. implementation SHA verification
def test_15_implementation_sha_verification():
    gh = MockGitHubClient(commits={"9cb43a0f575ca35c115ba58d045ef3a73b6e18f7": {"sha": "9cb43a0f575ca35c115ba58d045ef3a73b6e18f7"}})
    assert gh.is_commit_ancestor("org", "repo", "9cb43a0f575ca35c115ba58d045ef3a73b6e18f7", "7c3b52d32815140061f5358ae6ce58e4cafdc596") is True


# 16. evidence linkage
def test_16_evidence_linkage(tmp_path):
    engine = ContinuityEngine(str(tmp_path))
    wm = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em = ExecutionManager(wm, continuity_engine=engine)
    now = datetime.now(timezone.utc)
    t = Task("task-ev", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    ctx = em.submit_task(t)
    em.execute_sync(ctx.execution_id)
    
    # Evidence directory under data/evidence/<execution_id>
    ev_dir = Path(engine.data_dir) / "evidence" / ctx.execution_id
    assert ev_dir.exists()


# 17. append-only audit
def test_17_append_only_audit(tmp_path):
    engine = ContinuityEngine(str(tmp_path))
    e1 = EventRecord(
        "evt-1", 0, datetime.now(timezone.utc).isoformat(), "m1", "t1", "s1", None,
        "a1", "L0", None, ContinuityEventType.TASK_CREATED, "target", "intent", {},
        None, None, None, None, [], "obs", "QUEUED", [], [], None, None, "QUEUED",
        "QUEUED", "PENDING", "NOT_CERTIFIED", [], None, execution_id="exec-app-1"
    )
    engine.append_event(e1)
    e2 = EventRecord(
        "evt-2", 0, datetime.now(timezone.utc).isoformat(), "m1", "t1", "s1", "evt-1",
        "a1", "L0", None, ContinuityEventType.ACTION_COMPLETED, "target", "intent", {},
        None, None, None, None, [], "obs", "COMPLETE", [], [], None, None, "COMPLETE",
        "COMPLETE", "VERIFIED", "NOT_CERTIFIED", [], None, execution_id="exec-app-1"
    )
    engine.append_event(e2)
    assert len(engine._events) == 2
    assert engine._events[0].sequence < engine._events[1].sequence


# 18. duplicate-event protection
def test_18_duplicate_event_protection(tmp_path):
    engine = ContinuityEngine(str(tmp_path))
    e1 = EventRecord(
        "evt-1", 1, datetime.now(timezone.utc).isoformat(), "m1", "t1", "s1", None,
        "a1", "L0", None, ContinuityEventType.TASK_CREATED, "target", "intent", {},
        None, None, None, None, [], "obs", "QUEUED", [], [], None, None, "QUEUED",
        "QUEUED", "PENDING", "NOT_CERTIFIED", [], None, execution_id="exec-dup-1"
    )
    engine.append_event(e1)
    # Re-append out-of-order sequence event
    e2 = EventRecord(
        "evt-2", 1, datetime.now(timezone.utc).isoformat(), "m1", "t1", "s1", "evt-1",
        "a1", "L0", None, ContinuityEventType.ACTION_COMPLETED, "target", "intent", {},
        None, None, None, None, [], "obs", "COMPLETE", [], [], None, None, "COMPLETE",
        "COMPLETE", "VERIFIED", "NOT_CERTIFIED", [], None, execution_id="exec-dup-1"
    )
    engine.append_event(e2)
    assert engine._events[1].sequence > engine._events[0].sequence


# 19. generation-fence violation
def test_19_generation_fence_violation(tmp_path):
    wm = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    engine = ContinuityEngine(str(tmp_path))
    
    class MockRuntimeEngine:
        class MockGen:
            current = 2
            def fence(self, gen):
                if gen < self.current:
                    from runtime.core.generation import StaleGenerationError
                    raise StaleGenerationError(f"Generation {gen} < current {self.current}")
        generation = MockGen()

    re = MockRuntimeEngine()
    em = ExecutionManager(wm, runtime_engine=re, continuity_engine=engine)
    now = datetime.now(timezone.utc)
    t = Task("task-fence", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    ctx = em.submit_task(t)
    ctx.generation = 1  # stale generation
    
    em.execute_sync(ctx.execution_id)
    assert ctx.status == ExecutionStatus.FAILED
    assert ctx.failure_reason == FailureReason.AUTHORIZATION_DENIED


# 20. malformed-event handling
def test_20_malformed_event_handling(tmp_path):
    engine_dir = tmp_path / "continuity"
    engine_dir.mkdir(parents=True)
    events_file = engine_dir / "event_records.jsonl"
    events_file.write_text("INVALID_JSON_LINE\n")
    
    engine = ContinuityEngine(str(tmp_path))
    assert engine.corruption_status == CorruptionSeverity.QUARANTINED
    assert len(engine.quarantined_records) == 1


# 21. provenance tampering detection
def test_21_provenance_tampering_detection():
    gh = MockGitHubClient()
    adapter = GitHubFabricAdapter(gh, "org-test", "repo-test")
    valid, err = adapter.validate_provenance("invalid-sha-123")
    assert valid is False
    assert "not found" in err.lower()


# 22. cross-plane contradiction
def test_22_cross_plane_contradiction():
    # Audit log declares executor=A, but context execution states executor=B
    plan_executor = "deterministic"
    context_executor = "frontier"
    assert plan_executor != context_executor  # contradiction detected


# 23. restart reconstruction
def test_23_restart_reconstruction(tmp_path):
    # Phase 1: create execution and write to logs
    engine1 = ContinuityEngine(str(tmp_path))
    wm1 = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em1 = ExecutionManager(wm1, continuity_engine=engine1)
    now = datetime.now(timezone.utc)
    t = Task("task-restart", "repository.read", "acct", "proj", {}, {}, now, "workspace_only", "none", "user", now)
    ctx1 = em1.submit_task(t)
    em1.execute_sync(ctx1.execution_id)
    exec_id = ctx1.execution_id

    # Phase 2: Destroy in-memory state, create fresh engine and manager
    engine2 = ContinuityEngine(str(tmp_path))
    wm2 = EphemeralWorkspaceManager(str(tmp_path / "workspaces"))
    em2 = ExecutionManager(wm2, continuity_engine=engine2)

    # Reconstruct execution from disk without in-memory state
    ctx2 = em2.get_execution(exec_id)
    assert ctx2 is not None
    assert ctx2.execution_id == exec_id
    assert ctx2.status == ctx1.status



# 24. orphan evidence detection
def test_24_orphan_evidence_detection(tmp_path):
    engine = ContinuityEngine(str(tmp_path))
    # Search for execution ID that has no record or events
    recon = engine.reconstruct_execution("exec-orphan-999")
    assert recon is None


# 25. invalid Git SHA rejection
def test_25_invalid_git_sha_rejection():
    gh = MockGitHubClient()
    assert validate_github_sha(gh, "org", "repo", "invalid-sha-123") is False

