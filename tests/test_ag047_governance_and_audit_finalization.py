import json
from datetime import datetime, timezone, timedelta
import pytest
from runtime.execution.models import Task, TaskExecutionContext, ExecutionStatus, FailureReason
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.manager import ExecutionManager
from runtime.workspace.ephemeral import EphemeralWorkspaceManager
from runtime.orchestration.kernel import Orchestrator
from runtime.orchestration.plan import ExecutionPlan, RoutingClass
from runtime.orchestration.frontier import DefaultFrontierExecutor
from runtime.fabric.models import FabricContract, FabricPolicy
from runtime.fabric.github_adapter import GitHubFabricAdapter, FabricError
from runtime.github.client import GitHubClient, GitHubNotFoundError, validate_github_sha
from runtime.continuity.engine import ContinuityEngine, CorruptionSeverity
from runtime.mcp import ToolRequest, ToolInvocationStatus
from runtime.mcp.gateway import MCPGateway
from runtime.mcp.registry import ToolRegistry

def _task(capability_id: str, **extra):
    now = datetime.now(timezone.utc)
    t = Task(task_id=extra.pop("task_id", "ag047-"+capability_id.replace(".", "-")),
             capability_id=capability_id, account_id="ag047-account", project_id="ag047-project",
             input=extra.pop("input", {}), constraints=extra.pop("constraints", {}),
             deadline=extra.pop("deadline", now+timedelta(minutes=5)),
             workspace_policy="workspace_only", evidence_policy="standard",
             requested_by="AG-047", created_at=now)
    for key, value in extra.items(): setattr(t, key, value)
    return t

def _capability(capability_id="test.inference", enabled=True, inference=True, deterministic=False):
    return CapabilityDefinition(capability_id=capability_id, name=capability_id,
        description="AG-047 governance test capability", version="1.0.0",
        risk_level="high" if inference else "low", inference_required=inference,
        deterministic_allowed=deterministic, network_policy="disabled",
        filesystem_policy="read_only", required_tools=[], max_runtime=60,
        max_output=1024, evidence_required=True,
        preferred_executor=ExecutorType.LOCAL_MODEL if inference else ExecutorType.DETERMINISTIC,
        fallback_executor=None, enabled=enabled)

class MinimalGitHub(GitHubClient):
    def __init__(self, files=None, commits=None):
        self.files = files or {}; self.commits = commits or {}
    def get_file(self, owner, repo, path, ref="main"):
        key=f"{owner}/{repo}/{path}"
        if key not in self.files: raise GitHubNotFoundError(path)
        return self.files[key]
    def get_commit(self, owner, repo, sha):
        if sha in self.commits: return self.commits[sha]
        raise GitHubNotFoundError(sha)
    def get_repository(self, owner, repo): return {"name":repo,"owner":{"login":owner}}
    def _request(self, endpoint, query_params=None, headers_extra=None): return {"sha":"blob-sha"}

def test_01_deterministic_route():
    plan=Orchestrator().plan_task(_task("repository.read")); assert plan.routing_class==RoutingClass.DETERMINISTIC; assert plan.executor_type=="DETERMINISTIC"

def test_02_unknown_capability_blocks():
    assert Orchestrator().plan_task(_task("ag047.unknown")).routing_class==RoutingClass.BLOCKED

def test_03_disabled_capability_blocks():
    r=CapabilityRegistry(); r.register(_capability(enabled=False,inference=False))
    assert Orchestrator(capability_registry=r).plan_task(_task("test.inference")).routing_class==RoutingClass.BLOCKED

def test_04_llm_policy_blocks_inference():
    r=CapabilityRegistry(); r.register(_capability())
    assert Orchestrator(capability_registry=r).plan_task(_task("test.inference"), RuntimePolicy(allow_llm=False)).routing_class==RoutingClass.BLOCKED

def test_05_network_denial_blocks():
    r=CapabilityRegistry(); r.register(_capability())
    assert Orchestrator(capability_registry=r).plan_task(_task("test.inference", requires_network=True), RuntimePolicy(allow_llm=True)).routing_class==RoutingClass.BLOCKED

def test_06_revoked_capability_blocks():
    class A:
        def read_contract(self): return {"contract_id":"c","tenant_id":"t","revoked_capabilities":["repository.read"],"granted_capabilities":["repository.read"]}
    assert Orchestrator(fabric_adapter=A()).plan_task(_task("repository.read")).routing_class==RoutingClass.BLOCKED

def test_07_contract_model_parses():
    c=FabricContract.from_dict({"contract_id":"c","tenant_id":"t","granted_capabilities":["repository.read"],"revoked_capabilities":[]})
    assert c.contract_id=="c" and "repository.read" in c.granted_capabilities

def test_08_fabric_policy_defaults():
    p=FabricPolicy.from_dict({"revision":"r1"}); assert p.revision=="r1" and p.require_admission is True

def test_09_routing_provenance():
    p=Orchestrator().plan_task(_task("repository.read")); assert p.provenance["requested_capability"]=="repository.read"; assert p.provenance["task_id"]==p.task_id

def test_10_execution_plan_secret_sanitization():
    p=ExecutionPlan(task_id="t",capability_id="repository.read",capability_version="1.1.0",routing_class=RoutingClass.DETERMINISTIC,executor_type="DETERMINISTIC",executor_id="deterministic-v1",provenance={"api_key":"secret","secrets":{"token":"secret"},"ok":True})
    d=p.to_dict(); assert "api_key" not in d["provenance"] and "secrets" not in d["provenance"] and d["provenance"]["ok"] is True

def test_11_frontier_default_disabled(): assert DefaultFrontierExecutor().is_available() is False

def test_12_frontier_model_allowlist():
    f=DefaultFrontierExecutor(enabled=True,available_models=["frontier-test"]); assert f.is_available("frontier-test") and not f.is_available("frontier-other")

def test_13_frontier_execution_denies_unavailable():
    f=DefaultFrontierExecutor(enabled=True,available_models=["frontier-test"])
    p=ExecutionPlan(task_id="t",capability_id="document.classify",capability_version="1.0.0",routing_class=RoutingClass.FRONTIER_MODEL,executor_type="REMOTE_MODEL",executor_id="frontier-executor",model_id="frontier-other")
    with pytest.raises(RuntimeError): f.execute_plan(_task("document.classify"),p)

def test_14_mcp_requires_worker():
    g=MCPGateway(ToolRegistry(),CapabilityRegistry())
    r=ToolRequest.create("filesystem.inspect","filesystem.inspect","", "exec-1",{"path":"."},datetime.now(timezone.utc)+timedelta(minutes=1))
    assert g.invoke(r).status==ToolInvocationStatus.FAILED

def test_15_mcp_requires_execution():
    g=MCPGateway(ToolRegistry(),CapabilityRegistry())
    r=ToolRequest.create("filesystem.inspect","filesystem.inspect","worker-1","",{"path":"."},datetime.now(timezone.utc)+timedelta(minutes=1))
    assert g.invoke(r).status==ToolInvocationStatus.FAILED

def test_16_mcp_policy_denies_wrong_caller():
    g=MCPGateway(ToolRegistry(),CapabilityRegistry())
    r=ToolRequest.create("repository.search","repository.read","worker-1","exec-1",{"repo_path":".","pattern":"x"},datetime.now(timezone.utc)+timedelta(minutes=1))
    assert g.invoke(r).status==ToolInvocationStatus.DENIED

def test_17_mcp_disabled_capability_denied():
    c=CapabilityRegistry(); c.get("filesystem.inspect").enabled=False
    g=MCPGateway(ToolRegistry(),c)
    r=ToolRequest.create("filesystem.inspect","filesystem.inspect","worker-1","exec-1",{"path":"."},datetime.now(timezone.utc)+timedelta(minutes=1))
    assert g.invoke(r).status==ToolInvocationStatus.DENIED

def test_18_continuity_sequence(tmp_path):
    e=ContinuityEngine(str(tmp_path))
    from runtime.continuity.models import EventRecord
    from runtime.continuity.events import ContinuityEventType
    b=dict(timestamp=datetime.now(timezone.utc).isoformat(),mission_id="m",task_id="t",step_id="s",parent_event_id=None,actor_id="a",actor_level="L0",parent_actor_id=None,event_type=ContinuityEventType.TASK_CREATED,target="runtime",intent="test",inputs={},repository=None,branch=None,commit_before=None,commit_after=None,files_changed=[],observation="",result="",evidence_refs=[],test_results=[],decision_ref=None,state_change=None,status="QUEUED",implementation_state="QUEUED",verification_state="PENDING",certification_state="NOT_CERTIFIED",blocker_refs=[],next_action=None,execution_id="exec-seq")
    e.append_event(EventRecord(event_id="e1",sequence=99,**b)); e.append_event(EventRecord(event_id="e2",sequence=99,**b))
    assert e._events[1].sequence>e._events[0].sequence

def test_19_corruption_quarantined(tmp_path):
    c=tmp_path/"continuity"; c.mkdir(parents=True); (c/"event_records.jsonl").write_text("not-json\n")
    e=ContinuityEngine(str(tmp_path)); assert e.corruption_status==CorruptionSeverity.QUARANTINED and len(e.quarantined_records)==1

def test_20_restart_reconstruction(tmp_path):
    e1=ContinuityEngine(str(tmp_path))
    from runtime.continuity.models import ContinuityRecord
    e1.save_record(ContinuityRecord.create("m","t","s","a","L0","objective",execution_id="exec-restart"))
    assert ContinuityEngine(str(tmp_path)).reconstruct_execution("exec-restart") is not None

def test_21_generation_fence_failure(tmp_path):
    class RuntimeEngine:
        class Generation:
            current=2
            def fence(self,generation):
                if generation<self.current:
                    from runtime.core.generation import StaleGenerationError
                    raise StaleGenerationError("stale")
        generation=Generation()
    em=ExecutionManager(EphemeralWorkspaceManager(str(tmp_path/"ws")),runtime_engine=RuntimeEngine(),continuity_engine=ContinuityEngine(str(tmp_path)))
    ctx=em.submit_task(_task("repository.read")); ctx.generation=1; em.execute_sync(ctx.execution_id)
    assert ctx.status==ExecutionStatus.FAILED and ctx.failure_reason==FailureReason.AUTHORIZATION_DENIED

def test_22_invalid_github_sha():
    assert validate_github_sha(MinimalGitHub(), "org","repo","missing-sha") is False

def test_23_missing_fabric_configuration():
    with pytest.raises(FabricError): GitHubFabricAdapter(MinimalGitHub(),config={})

def test_24_legacy_governance_surfaces_deprecated():
    from runtime.execution.receipt import ReceiptStore
    from runtime.admin.audit import AdminAuditLog
    from runtime.journal.journal import OperationJournal
    assert "DEPRECATED" in (ReceiptStore.__doc__ or "")
    assert "DEPRECATED" in (AdminAuditLog.__doc__ or "")
    assert "DEPRECATED" in (OperationJournal.__doc__ or "")

def test_25_runtime_readiness_blocker_is_preserved():
    s=open("docs/MILESTONE-LEDGER-001.yaml",encoding="utf-8").read()
    section=s[s.index("name: DISTRIBUTION_READINESS_GATE"):s.index("  - id: ANNY-ORCHESTRATION-KERNEL-001")]
    assert "status: NOT_READY" in section and "OS_SERVICE_INTEGRATION: NOT_ESTABLISHED" in section
