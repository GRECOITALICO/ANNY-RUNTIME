import os
import json
import pytest
from runtime.github.client import GitHubClient
from runtime.github.discovery import OrganizationDiscoveryService
from runtime.adapters.fabric_client import FabricClient, FabricError

FABRIC_ENDPOINT = os.environ.get(
    "FABRIC_ENDPOINT",
    "https://ca-fabric-node-001.purplerock-4a8636a6.eastus.azurecontainerapps.io"
)

@pytest.fixture(scope="module")
def github_client():
    from runtime.identity.runtime_identity import RuntimeIdentity
    from runtime.secrets.backend import FileSecretBackend
    from pathlib import Path
    data_dir = Path("/var/lib/anny-runtime")
    identity_manager = RuntimeIdentity.load(data_dir)
    secret_backend = FileSecretBackend(str(data_dir / "secrets"), identity_manager._private_key)
    return GitHubClient(secret_backend=secret_backend)

@pytest.fixture(scope="module")
def fabric_client():
    return FabricClient(endpoint=FABRIC_ENDPOINT)

def test_discovery_and_fabric_integration(github_client, fabric_client):
    disc = OrganizationDiscoveryService(github_client)
    
    # Phase 1: Discovery
    repos = disc.discover_repositories()
    
    selected_repo = None
    for r in repos:
        name = r.name.upper()
        if not r.archived and "VIEJO" not in name and "PROJECTS" not in name and "CONRRAD" not in name:
            selected_repo = r
            break
            
    assert selected_repo is not None, "No valid test repository found"
    
    # Phase 2: Normalization
    normalized = {
        "provider": "github",
        "external_id": str(selected_repo.latest_metadata.get("id", selected_repo.full_name)),
        "owner": selected_repo.owner,
        "name": selected_repo.name,
        "visibility": selected_repo.visibility,
        "default_branch": selected_repo.default_branch,
        "source_revision": selected_repo.latest_metadata.get("pushed_at", "unknown"),
        "observed_by": "anny-runtime-integration-test"
    }
    
    # Phase 3: Register
    resource1 = fabric_client.register_resource(
        provider=normalized["provider"],
        external_id=normalized["external_id"],
        name=normalized["name"],
        r_type="Repository",
        source_revision=normalized["source_revision"],
        observed_by=normalized["observed_by"]
    )
    if isinstance(resource1, str):
        resource1 = json.loads(resource1)
    
    resource_id = resource1["resource_id"]
    assert resource_id is not None
    
    # Phase 4: Idempotence
    resource2 = fabric_client.register_resource(
        provider=normalized["provider"],
        external_id=normalized["external_id"],
        name=normalized["name"],
        r_type="Repository",
        source_revision=normalized["source_revision"],
        observed_by=normalized["observed_by"]
    )
    if isinstance(resource2, str):
        resource2 = json.loads(resource2)
        
    assert resource2["resource_id"] == resource_id
    
    # Phase 5: Read Back
    fetched = fabric_client.get_resource(resource_id)
    if isinstance(fetched, str):
        fetched = json.loads(fetched)
    assert fetched["resource_id"] == resource_id
    assert fetched["provider"] == "github"
    assert fetched["external_id"] == normalized["external_id"]
    assert fetched["name"] == normalized["name"]
    assert fetched["state"] == "ACTIVE"
    
    # Phase 6: Provenance
    prov = fabric_client.get_provenance(resource_id)
    assert len(prov) >= 1
    record = prov[0]
    assert record["resource_id"] == resource_id
    assert record["source_system"] == "github"
    assert record["external_id"] == normalized["external_id"]
    assert record["source_revision"] == normalized["source_revision"]
    assert record["observed_by"] == normalized["observed_by"]
    assert "input_hash" in record
    assert "record_hash" in record
    
    # Phase 9: Failures
    with pytest.raises(FabricError) as exc:
        fabric_client.get_resource("nonexistent-0000")
    assert exc.value.error_code == "FABRIC_NOT_FOUND"
    
    # Network Error
    bad_client = FabricClient(endpoint="http://192.0.2.1:9999")
    with pytest.raises(FabricError) as exc:
        bad_client.health()
    assert exc.value.error_code == "FABRIC_NETWORK_ERROR"

    # Save data for evidence generation later
    os.makedirs("/tmp/anny_evidence", exist_ok=True)
    with open("/tmp/anny_evidence/repo.json", "w") as f:
        json.dump(selected_repo.to_dict(), f)
    with open("/tmp/anny_evidence/normalized.json", "w") as f:
        json.dump(normalized, f)
    with open("/tmp/anny_evidence/registered.json", "w") as f:
        json.dump(resource1, f)
    with open("/tmp/anny_evidence/fetched.json", "w") as f:
        json.dump(fetched, f)
    with open("/tmp/anny_evidence/provenance.json", "w") as f:
        json.dump(record, f)
