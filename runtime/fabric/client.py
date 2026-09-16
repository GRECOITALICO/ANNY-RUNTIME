"""
GitHub-authenticated Repository Fabric Client.

Accesses the Fabric via the GitHub API using the runtime's GitHub token.
The Fabric org and repo are resolved dynamically from RuntimeConfig at instantiation time;
they MUST NOT be hardcoded in production code paths.
"""
import json
import logging
import hmac
import hashlib
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta

from runtime.github.client import GitHubClient, GitHubNotFoundError, GitHubClientError
from runtime.fabric.models import (
    FabricNode, FabricTenant, FabricProject,
    FabricTrustToken, FabricHealthResult, FabricStatus
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# IMPORTANT: These module-level constants are LEGACY / test-fallback only.
# All production code must pass org and repo from RuntimeConfig.
# Do NOT use FABRIC_ORG / FABRIC_REPO directly in new code paths.
# -----------------------------------------------------------------------
_LEGACY_FABRIC_ORG = "GRECOITALICO"
_LEGACY_FABRIC_REPO = "ANNY-OPERATIONAL"


class FabricAdmissionResult:
    """Result of a real authoritative fabric admission check."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"

    def __init__(self, verdict: str, reason: str = "", raw: dict = None):
        self.verdict = verdict
        self.reason = reason
        self.raw = raw or {}

    def is_admitted(self) -> bool:
        return self.verdict == self.ALLOW

    def __repr__(self):
        return f"FabricAdmissionResult(verdict={self.verdict!r}, reason={self.reason!r})"


class FabricError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{error_code}] {message}")


class FabricClient:
    """Client for interacting with the Repository Fabric over GitHub.

    The fabric_org and fabric_repo are resolved from config at construction.
    They can also be overridden explicitly for testing.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        fabric_org: Optional[str] = None,
        fabric_repo: Optional[str] = None,
        config=None,
    ):
        self.gh = github_client

        # Resolve org/repo: explicit args > config > legacy fallback
        if fabric_org and fabric_repo:
            self._org = fabric_org
            self._repo = fabric_repo
        elif config and getattr(config, 'fabric_org', None) and getattr(config, 'fabric_repo', None):
            self._org = config.fabric_org
            self._repo = config.fabric_repo
        else:
            # Log a warning — this should never happen in production
            logger.warning(
                "FabricClient: fabric_org/fabric_repo not set via config. "
                "Falling back to legacy constants. Set config.fabric_org and config.fabric_repo."
            )
            self._org = _LEGACY_FABRIC_ORG
            self._repo = _LEGACY_FABRIC_REPO

        logger.info(f"FabricClient bound to {self._org}/{self._repo}")

    @property
    def org(self) -> str:
        return self._org

    @property
    def repo(self) -> str:
        return self._repo

    def probe_reachability(self) -> Tuple[bool, float, Optional[str]]:
        """Probes if the Fabric repository is reachable and accessible.

        Returns:
            (reachable: bool, latency_ms: float, error: Optional[str])
        """
        t0 = time.monotonic()
        try:
            self.gh.get_repository(self._org, self._repo)
            latency_ms = (time.monotonic() - t0) * 1000
            return True, latency_ms, None
        except GitHubNotFoundError:
            return False, 0.0, "Fabric repository not found (404)"
        except GitHubClientError as e:
            return False, 0.0, f"GitHub API error: {e}"
        except Exception as e:
            return False, 0.0, f"Unexpected error: {e}"

    def probe_health(self) -> FabricHealthResult:
        """Returns a FabricHealthResult for compatibility with existing callers."""
        reachable, latency_ms, error = self.probe_reachability()
        return FabricHealthResult(
            reachable=reachable,
            node_id=None,
            latency_ms=latency_ms,
            error=error,
        )

    def read_node_config(self) -> FabricNode:
        """Reads the fabric/node.json config from the Fabric repo."""
        try:
            content = self.gh.get_file(self._org, self._repo, "fabric/node.json")
            data = json.loads(content)
            return FabricNode.from_dict(data)
        except GitHubNotFoundError:
            raise FabricError("FABRIC_NODE_MISSING", "fabric/node.json not found in Fabric repo")
        except json.JSONDecodeError as e:
            raise FabricError("FABRIC_NODE_MALFORMED", f"fabric/node.json is malformed JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to read fabric node config: {e}")
            raise FabricError("FABRIC_NODE_ERROR", f"Could not read fabric/node.json: {e}")

    def node_json_exists_at_remote_head(self) -> Tuple[bool, Optional[str]]:
        """Verifies fabric/node.json exists at remote HEAD (not cached).

        Returns:
            (exists: bool, sha: Optional[str]) — sha is the blob SHA if found
        """
        try:
            # Use the Contents API — this always reflects remote HEAD
            endpoint = f"/repos/{self._org}/{self._repo}/contents/fabric/node.json"
            response = self.gh._request(endpoint)
            import json as _json
            data = _json.loads(response)
            return True, data.get("sha")
        except GitHubNotFoundError:
            return False, None
        except Exception as e:
            logger.warning(f"Could not verify fabric/node.json at remote HEAD: {e}")
            return False, None

    def read_tenant_binding(self, runtime_id: str) -> FabricTenant:
        """Reads the tenant binding for this runtime."""
        path = f"fabric/tenants/{runtime_id}.json"
        try:
            content = self.gh.get_file(self._org, self._repo, path)
            data = json.loads(content)
            return FabricTenant.from_dict(data)
        except GitHubNotFoundError:
            raise FabricError("TENANT_UNBOUND", f"No tenant binding found for {runtime_id}")
        except Exception as e:
            logger.error(f"Failed to read tenant binding: {e}")
            raise FabricError("FABRIC_TENANT_ERROR", f"Could not read {path}: {e}")

    def check_admission(self, runtime_id: str) -> FabricAdmissionResult:
        """Real authoritative admission check against the Fabric.

        Reads fabric/admissions/{runtime_id}.json from the Fabric repo.
        If absent, checks fabric/node.json for a global policy.
        Returns FabricAdmissionResult with verdict ALLOW | DENY | PENDING | UNKNOWN.
        """
        # 1. Try runtime-specific admission record
        admission_path = f"fabric/admissions/{runtime_id}.json"
        try:
            content = self.gh.get_file(self._org, self._repo, admission_path)
            data = json.loads(content)
            verdict = data.get("verdict", "UNKNOWN").upper()
            reason = data.get("reason", "")
            return FabricAdmissionResult(verdict=verdict, reason=reason, raw=data)
        except GitHubNotFoundError:
            pass  # Fall through to node-level policy
        except Exception as e:
            logger.warning(f"Could not read admission record for {runtime_id}: {e}")
            return FabricAdmissionResult(
                verdict=FabricAdmissionResult.ERROR,
                reason=f"Admission check failed: {e}"
            )

        # 2. Read node.json for default_admission_policy
        try:
            node_content = self.gh.get_file(self._org, self._repo, "fabric/node.json")
            node_data = json.loads(node_content)
            default_policy = node_data.get("default_admission_policy", "DENY").upper()
            return FabricAdmissionResult(
                verdict=default_policy,
                reason=f"No explicit record — default policy from node.json: {default_policy}",
                raw=node_data,
            )
        except GitHubNotFoundError:
            return FabricAdmissionResult(
                verdict=FabricAdmissionResult.DENY,
                reason="fabric/node.json not found — cannot determine admission policy",
            )
        except Exception as e:
            logger.error(f"Could not evaluate default admission policy: {e}")
            return FabricAdmissionResult(
                verdict=FabricAdmissionResult.ERROR,
                reason=f"Admission policy evaluation failed: {e}",
            )

    def read_fabric_state(self) -> Dict[str, Any]:
        """Reads the live fabric state from fabric/state.json.

        Returns dict or raises FabricError.
        """
        try:
            content = self.gh.get_file(self._org, self._repo, "fabric/state.json")
            return json.loads(content)
        except GitHubNotFoundError:
            raise FabricError("FABRIC_STATE_MISSING", "fabric/state.json not found in Fabric repo")
        except json.JSONDecodeError as e:
            raise FabricError("FABRIC_STATE_MALFORMED", f"fabric/state.json is malformed: {e}")
        except Exception as e:
            raise FabricError("FABRIC_STATE_ERROR", f"Could not read fabric/state.json: {e}")

    def validate_provenance(self, commit_sha: str) -> Tuple[bool, Optional[str]]:
        """Validates if a commit exists in the Fabric repository at remote HEAD.

        Returns:
            (valid: bool, error: Optional[str])
        """
        if not commit_sha or len(commit_sha) < 7:
            return False, "Invalid commit SHA"
        try:
            endpoint = f"/repos/{self._org}/{self._repo}/commits/{commit_sha}"
            import json as _json
            response = self.gh._request(endpoint)
            data = _json.loads(response)
            # Confirm we got a real commit object back
            if data.get("sha"):
                return True, None
            return False, "Commit object malformed"
        except GitHubNotFoundError:
            return False, f"Commit {commit_sha[:7]} not found in {self._org}/{self._repo}"
        except Exception as e:
            logger.warning(f"Provenance validation failed for {commit_sha[:7]}: {e}")
            return False, f"Provenance check error: {e}"

    def issue_trust_token(self, runtime_id: str, private_key: bytes) -> FabricTrustToken:
        """Issues an offline trust token using HMAC over GitHub token + Private Key."""
        try:
            gh_token = self.gh._get_token()
        except Exception:
            raise FabricError("FABRIC_AUTH_ERROR", "No GitHub token available for trust generation")

        # Read actual node_id from Fabric rather than hardcoding
        try:
            node = self.read_node_config()
            node_id = node.node_id
        except FabricError:
            node_id = "UNKNOWN-NODE"

        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)

        issued_at_str = now.isoformat()
        expires_at_str = expires.isoformat()

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
