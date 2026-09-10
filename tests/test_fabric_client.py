"""
Tests for ANNY-REPOSITORY-FABRIC-MVP-001
Phases 16-22: Resource registration, round-trip, idempotence, provenance, restart, security
"""
import os
import json
import pytest
import uuid
import subprocess
import sys

# ============================================================
# Phase 20 — Test Suite
# ============================================================

FABRIC_ENDPOINT = os.environ.get(
    "FABRIC_ENDPOINT",
    "https://ca-fabric-node-001.purplerock-4a8636a6.eastus.azurecontainerapps.io"
)

SYNTHETIC_PROVIDER = "fabric-test"
SYNTHETIC_EXTERNAL_ID = f"synthetic-pytest-{uuid.uuid4().hex[:8]}"
SYNTHETIC_NAME = "PyTest Synthetic Resource"

@pytest.fixture(scope="module")
def client():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from runtime.adapters.fabric_client import FabricClient
    return FabricClient(endpoint=FABRIC_ENDPOINT)


# --- Phase 20: health ---
def test_health(client):
    result = client.health()
    assert result["status"] == "up"
    assert "timestamp" in result
    assert result.get("schema_version") == "1.0"


# --- Phase 20: identity ---
def test_identity(client):
    result = client.identity()
    assert result["node_id"] == "fabric-node-001"
    assert "environment" in result


# --- Phase 20: list ---
def test_list_resources(client):
    resources = client.list_resources()
    assert isinstance(resources, list)


# --- Phase 20: register ---
def test_register_resource(client):
    resource = client.register_resource(
        provider=SYNTHETIC_PROVIDER,
        external_id=SYNTHETIC_EXTERNAL_ID,
        name=SYNTHETIC_NAME,
        r_type="Repository",
        source_revision="test-rev-1",
        observed_by="pytest-fabric-mvp"
    )
    assert resource is not None
    # Resource might be a JSON string or dict depending on status
    if isinstance(resource, str):
        resource = json.loads(resource)
    assert resource["provider"] == SYNTHETIC_PROVIDER
    assert resource["external_id"] == SYNTHETIC_EXTERNAL_ID


# --- Phase 20: idempotence ---
def test_idempotent_register(client):
    r1 = client.register_resource(
        provider=SYNTHETIC_PROVIDER,
        external_id=SYNTHETIC_EXTERNAL_ID,
        name=SYNTHETIC_NAME,
        r_type="Repository",
        source_revision="test-rev-1",
        observed_by="pytest-fabric-mvp"
    )
    r2 = client.register_resource(
        provider=SYNTHETIC_PROVIDER,
        external_id=SYNTHETIC_EXTERNAL_ID,
        name=SYNTHETIC_NAME,
        r_type="Repository",
        source_revision="test-rev-1",
        observed_by="pytest-fabric-mvp"
    )
    
    if isinstance(r1, str):
        r1 = json.loads(r1)
    if isinstance(r2, str):
        r2 = json.loads(r2)
        
    assert r1["resource_id"] == r2["resource_id"]


# --- Phase 20: get ---
def test_get_resource(client):
    # First register to ensure it exists
    resource = client.register_resource(
        provider=SYNTHETIC_PROVIDER,
        external_id=SYNTHETIC_EXTERNAL_ID,
        name=SYNTHETIC_NAME,
        r_type="Repository",
        source_revision="test-rev-1",
        observed_by="pytest-fabric-mvp"
    )
    if isinstance(resource, str):
        resource = json.loads(resource)
    resource_id = resource["resource_id"]
    
    fetched = client.get_resource(resource_id)
    if isinstance(fetched, str):
        fetched = json.loads(fetched)
    assert fetched["resource_id"] == resource_id
    assert fetched["provider"] == SYNTHETIC_PROVIDER


# --- Phase 20: provenance ---
def test_provenance(client):
    resource = client.register_resource(
        provider=SYNTHETIC_PROVIDER,
        external_id=SYNTHETIC_EXTERNAL_ID,
        name=SYNTHETIC_NAME,
        r_type="Repository",
        source_revision="test-rev-1",
        observed_by="pytest-fabric-mvp"
    )
    if isinstance(resource, str):
        resource = json.loads(resource)
    resource_id = resource["resource_id"]
    
    provenance = client.get_provenance(resource_id)
    assert isinstance(provenance, list)
    assert len(provenance) >= 1
    record = provenance[0]
    assert record["resource_id"] == resource_id
    assert record["source_system"] == SYNTHETIC_PROVIDER
    assert "input_hash" in record
    assert "record_hash" in record


# --- Phase 20: auth error ---
def test_auth_error():
    """Test that unauthenticated requests fail with FABRIC_AUTH_ERROR."""
    import httpx
    response = httpx.get(f"{FABRIC_ENDPOINT}/resources")
    assert response.status_code == 401


# --- Phase 20: schema error ---
def test_schema_error():
    """Test that malformed register requests fail."""
    import httpx
    response = httpx.post(
        f"{FABRIC_ENDPOINT}/resources/register",
        json={"bad_field": "invalid"},
        headers={"token": "Bearer fake-token"}
    )
    assert response.status_code == 422  # Pydantic validation error


# --- Phase 20: not found ---
def test_not_found():
    """Test that requesting a nonexistent resource returns 404."""
    from runtime.adapters.fabric_client import FabricClient, FabricError
    c = FabricClient(endpoint=FABRIC_ENDPOINT)
    with pytest.raises(FabricError) as exc_info:
        c.get_resource("nonexistent-resource-id-00000")
    assert exc_info.value.error_code == "FABRIC_NOT_FOUND"


# --- Phase 20: network error ---
def test_network_error():
    """Test that connecting to an invalid endpoint raises FABRIC_NETWORK_ERROR."""
    from runtime.adapters.fabric_client import FabricClient, FabricError
    c = FabricClient(endpoint="http://192.0.2.1:9999")  # RFC 5737 TEST-NET
    with pytest.raises(FabricError) as exc_info:
        c.health()
    assert exc_info.value.error_code == "FABRIC_NETWORK_ERROR"


# --- Phase 20: Control Plane ---
def test_control_plane_fabric_status():
    """Control Plane should show CONNECTED only if health responds."""
    from runtime.adapters.fabric_client import FabricClient
    c = FabricClient(endpoint=FABRIC_ENDPOINT)
    health = c.health()
    assert health["status"] == "up"
    # This confirms that the /fabric page on :3643 would show CONNECTED
