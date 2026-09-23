from datetime import datetime, timezone

import pytest

from runtime.fabric.governed_write import GovernedFabricWriteBoundary, GovernedWriteError
from runtime.fabric.models import GovernedWriteReceipt, GovernedWriteRequest, GovernedWriteState


def _request(**overrides):
    values = dict(
        request_id="req-1", runtime_id="runtime-1", tenant_id="tenant-1",
        account_id="account-1", project_id="project-1", repository_scope="owner/repository",
        generation=7, authorization_ref="auth-1", policy_ref="policy-1", evidence_ref="evidence-1",
        operation="merge", payload_digest="a" * 64,
    )
    values.update(overrides)
    return GovernedWriteRequest(**values)


def test_governed_write_without_authoritative_transport_is_not_executed():
    receipt = GovernedFabricWriteBoundary().submit(_request(), current_generation=7)
    assert receipt.state is GovernedWriteState.NOT_EXECUTED
    assert receipt.reason == "AUTHORITATIVE_FABRIC_TRANSPORT_UNAVAILABLE"


@pytest.mark.parametrize("write_request,current_generation,reason", [
    (_request(generation=6), 7, "STALE_GENERATION"),
    (_request(repository_scope=""), 7, "REQUIRED_GOVERNANCE_BINDING_MISSING"),
    (_request(tenant_id=""), 7, "REQUIRED_GOVERNANCE_BINDING_MISSING"),
    (_request(project_id=""), 7, "REQUIRED_GOVERNANCE_BINDING_MISSING"),
])
def test_governed_write_rejects_incomplete_or_stale_governance(write_request, current_generation, reason):
    receipt = GovernedFabricWriteBoundary().submit(write_request, current_generation=current_generation)
    assert receipt.state is GovernedWriteState.BLOCKED
    assert receipt.reason == reason


def test_governed_write_rejects_uncorrelated_or_synthetic_success_receipt():
    def uncorrelated(_request):
        return GovernedWriteReceipt("receipt", "other-request", GovernedWriteState.SUCCEEDED, "operation", "evidence")
    with pytest.raises(GovernedWriteError, match="CORRELATION"):
        GovernedFabricWriteBoundary(uncorrelated).submit(_request(), current_generation=7)

    def incomplete(request):
        return GovernedWriteReceipt("receipt", request.request_id, GovernedWriteState.SUCCEEDED)
    with pytest.raises(GovernedWriteError, match="INCOMPLETE"):
        GovernedFabricWriteBoundary(incomplete).submit(_request(), current_generation=7)


def test_governed_write_accepts_only_correlated_authoritative_success():
    def authoritative(request):
        return GovernedWriteReceipt(
            "receipt-1", request.request_id, GovernedWriteState.SUCCEEDED,
            authoritative_operation_id="fabric-operation-1", evidence_ref="fabric-evidence-1",
        )
    receipt = GovernedFabricWriteBoundary(authoritative).submit(_request(), current_generation=7)
    assert receipt.state is GovernedWriteState.SUCCEEDED


def test_local_trust_issuance_is_never_verified(monkeypatch):
    from runtime.fabric.github_adapter import GitHubFabricAdapter
    from runtime.fabric.models import FabricNode

    class GitHub:
        def _get_token(self): return "token"
    adapter = GitHubFabricAdapter(GitHub(), fabric_org="owner", fabric_repo="repository")
    monkeypatch.setattr(adapter, "read_node_config", lambda: FabricNode("node-1", "owner", "repository", "REPOSITORY_FABRIC", datetime.now(timezone.utc).isoformat()))
    token = adapter.issue_trust_token("runtime-1", b"private")
    assert token.runtime_id == "runtime-1"
    assert token.node_id == "node-1"
    assert token.expires_at > token.issued_at
    assert token.verified is False
    assert token.verification_state == "UNVERIFIED"
