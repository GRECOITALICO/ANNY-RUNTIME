"""
GitHub-authenticated Repository Fabric Client.

Accesses the Fabric (GRECOITALICO/ANNY-OPERATIONAL) via the GitHub API
using the runtime's GitHub token.
"""
import json
import logging
import hmac
import hashlib
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from runtime.github.client import GitHubClient, GitHubNotFoundError, GitHubClientError
from runtime.fabric.models import (
    FabricNode, FabricTenant, FabricProject, 
    FabricTrustToken, FabricHealthResult, FabricStatus
)

logger = logging.getLogger(__name__)

FABRIC_ORG = "GRECOITALICO"
FABRIC_REPO = "ANNY-OPERATIONAL"


class FabricError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{error_code}] {message}")


class FabricClient:
    """Client for interacting with the Repository Fabric over GitHub."""

    def __init__(self, github_client: GitHubClient):
        self.gh = github_client

    def probe_reachability(self) -> FabricHealthResult:
        """Probes if the Fabric repository is reachable and accessible."""
        try:
            repo_info = self.gh.get_repository(FABRIC_ORG, FABRIC_REPO)
            return FabricHealthResult(
                reachable=True,
                node_id=None,
                latency_ms=0.0  # Cannot measure easily via urllib
            )
        except GitHubNotFoundError:
            return FabricHealthResult(reachable=False, error="Fabric repository not found")
        except GitHubClientError as e:
            return FabricHealthResult(reachable=False, error=str(e))
        except Exception as e:
            return FabricHealthResult(reachable=False, error=str(e))

    def read_node_config(self) -> FabricNode:
        """Reads the fabric/node.json config from the Fabric."""
        try:
            content = self.gh.get_file(FABRIC_ORG, FABRIC_REPO, "fabric/node.json")
            data = json.loads(content)
            return FabricNode.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to read fabric node config: {e}")
            raise FabricError("FABRIC_NODE_ERROR", "Could not read fabric/node.json")

    def read_tenant_binding(self, runtime_id: str) -> FabricTenant:
        """Reads the tenant binding for this runtime."""
        path = f"fabric/tenants/{runtime_id}.json"
        try:
            content = self.gh.get_file(FABRIC_ORG, FABRIC_REPO, path)
            data = json.loads(content)
            return FabricTenant.from_dict(data)
        except GitHubNotFoundError:
            raise FabricError("TENANT_UNBOUND", f"No tenant binding found for {runtime_id}")
        except Exception as e:
            logger.error(f"Failed to read tenant binding: {e}")
            raise FabricError("FABRIC_TENANT_ERROR", f"Could not read {path}")

    def issue_trust_token(self, runtime_id: str, private_key: bytes) -> FabricTrustToken:
        """Issues an offline trust token using HMAC over GitHub token + Private Key."""
        # For P0, we prove trust by signing a statement that we hold the private key 
        # and the GitHub token.
        try:
            gh_token = self.gh._get_token()
        except Exception:
            raise FabricError("FABRIC_AUTH_ERROR", "No GitHub token available for trust generation")
            
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        
        issued_at_str = now.isoformat()
        expires_at_str = expires.isoformat()
        
        node_id = "NODE-001" # Hardcoded for P0, normally read from node.json
        
        message = f"{runtime_id}:{node_id}:{issued_at_str}:{gh_token}".encode('utf-8')
        signature = hmac.new(private_key, message, hashlib.sha256).hexdigest()
        
        return FabricTrustToken(
            runtime_id=runtime_id,
            node_id=node_id,
            issued_at=issued_at_str,
            expires_at=expires_at_str,
            signature=signature,
            verified=True
        )

    def validate_provenance(self, commit_sha: str) -> bool:
        """Validates if a given commit exists in the Fabric repository."""
        # In P0, we just check if the commit can be retrieved from the repo via the commits API
        try:
            endpoint = f"/repos/{FABRIC_ORG}/{FABRIC_REPO}/commits/{commit_sha}"
            self.gh._request(endpoint)
            return True
        except GitHubNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"Provenance validation failed: {e}")
            return False
