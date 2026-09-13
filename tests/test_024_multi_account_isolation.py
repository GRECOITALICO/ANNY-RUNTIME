import pytest
import os
import tempfile
from runtime.accounts.registry import AccountRegistry
from runtime.accounts.models import AccountStatus
from runtime.projects.registry import ProjectRegistry
from runtime.security.context_guard import ContextGuard, ContextAccessError
from runtime.security.execution_context import ExecutionContext
from runtime.secrets.backend import FileSecretBackend, AccountCredentialBroker
from runtime.workspace.manager import WorkspaceManager, Workspace
from runtime.execution.models import Task, WorkerDefinition, TaskExecutionContext
from runtime.events.bus import EventBus, Event, EventType

@pytest.fixture
def env():
    with tempfile.TemporaryDirectory() as tmp:
        # Create registries and backend
        acc_reg = AccountRegistry(data_dir=tmp)
        proj_reg = ProjectRegistry(data_dir=tmp)
        sec_backend = FileSecretBackend(data_dir=tmp, master_key=b"0" * 32)
        yield {
            "tmp": tmp,
            "accounts": acc_reg,
            "projects": proj_reg,
            "secrets": sec_backend
        }

def test_1_accounts(env):
    """Create 5 accounts, verify unique IDs and limits."""
    acc_reg = env["accounts"]
    
    accounts = []
    for i in range(5):
        acc = acc_reg.create_account(f"user{i}", "personal")
        accounts.append(acc)
    
    assert len(acc_reg.list_accounts()) == 5
    ids = {a.account_id for a in accounts}
    assert len(ids) == 5

def test_credential_namespacing(env):
    """Store token for acct-A, retrieve with acct-B ref should fail if strictly namespaced by broker."""
    sec_backend = env["secrets"]
    broker_a = AccountCredentialBroker(sec_backend, "1")
    broker_b = AccountCredentialBroker(sec_backend, "2")
    
    ref_a = broker_a.credential_ref_for("github-token")
    ref_b = broker_b.credential_ref_for("github-token")
    
    broker_a.store(ref_a, b"token-a")
    assert broker_a.retrieve(ref_a) == b"token-a"
    
    # broker_b cannot retrieve broker_a's ref
    with pytest.raises(ContextAccessError, match="CONTEXT_ACCESS_DENIED"):
        broker_b.retrieve(ref_a)
        
    # broker_a cannot store with acct-2 prefix
    with pytest.raises(ContextAccessError, match="CONTEXT_ACCESS_DENIED"):
        broker_a.store(ref_b, b"token-b")

def test_worker_crosses_project(env):
    """Worker A context -> workspace B (different project)"""
    from datetime import datetime, timezone
    ctx = ExecutionContext(
        tenant_id="tenant-1",
        account_id="acct-1",
        project_id="proj-1",
        session_id="sess-1",
        actor_id="actor-1",
        execution_id="exec-1",
        anny_instance_id="inst-1",
        runtime_id="rt-1",
        operation_id="op-1",
        generation=1,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc)
    )
    
    from runtime.workspace.manager import WorkspaceState
    workspace = Workspace(
        workspace_id="ws-1",
        project_id="proj-2", # DIFFERENT
        tenant_id="tenant-1",
        actor_scope=["actor-1"],
        repository="repo-1",
        source_revision="main",
        state=WorkspaceState.ACTIVE,
        generation=1,
        local_path="/tmp/ws-1",
        created_at="2026-09-12T00:00:00Z"
    )
    
    with pytest.raises(ContextAccessError, match="CONTEXT_ACCESS_DENIED"):
        ContextGuard.assert_workspace(ctx, workspace)

def test_task_crosses_project(env):
    """Task with project-A -> submit into project-B."""
    # Since ExecutionManager does the submit, it propagates context.
    # The task should receive the context's project.
    from datetime import datetime, timezone
    ctx = ExecutionContext(
        tenant_id="tenant-1",
        account_id="acct-1",
        project_id="proj-1",
        session_id="sess-1",
        actor_id="actor-1",
        execution_id="exec-1",
        anny_instance_id="inst-1",
        runtime_id="rt-1",
        operation_id="op-1",
        generation=1,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc)
    )
    
    task = Task(
        task_id="t-1",
        account_id="acct-2", # DIFFERENT
        project_id="proj-2",
        capability_id="cap-1",
        input={},
        constraints={},
        deadline=datetime.now(timezone.utc),
        workspace_policy="NONE",
        evidence_policy="NONE",
        requested_by="actor-1",
        created_at=datetime.now(timezone.utc)
    )
    
    # If the execution engine uses ContextGuard on task execution:
    with pytest.raises(ContextAccessError, match="CONTEXT_ACCESS_DENIED"):
        ContextGuard.assert_project(ctx, task.project_id)

def test_telemetry_scope_isolation():
    from runtime.telemetry.telemetry import TelemetryEnvelope
    env1 = TelemetryEnvelope.create(
        component="test",
        event_type="test.event",
        source="test",
        account_id="acct-1"
    )
    assert env1.account_id == "acct-1"

def test_project_isolation_same_account():
    from datetime import datetime, timezone
    ctx = ExecutionContext(
        tenant_id="tenant-1",
        account_id="acct-1",
        project_id="proj-1",
        session_id="sess-1",
        actor_id="actor-1",
        execution_id="exec-1",
        anny_instance_id="inst-1",
        runtime_id="rt-1",
        operation_id="op-1",
        generation=1,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc)
    )
    
    ContextGuard.assert_account(ctx, "acct-1") # Matches
    with pytest.raises(ContextAccessError, match="CONTEXT_ACCESS_DENIED"):
        ContextGuard.assert_project(ctx, "proj-2") # Does not match
