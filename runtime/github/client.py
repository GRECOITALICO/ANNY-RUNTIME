"""Read-only GitHub API client for ANNY Runtime.

Uses stored GitHub credentials from SecretBackend / GitHubAuthManager.
Enforces timeouts, typed exceptions, and read-only operations.
"""
import base64
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN_REF = "github-access-token"


class GitHubClientError(Exception):
    """Base exception for GitHub client errors."""
    pass


class GitHubAuthError(GitHubClientError):
    """Raised when authentication fails or token is missing."""
    pass


class GitHubNotFoundError(GitHubClientError):
    """Raised when requested resource is not found (HTTP 404)."""
    pass


class GitHubTimeoutError(GitHubClientError):
    """Raised when a request times out."""
    pass


class GitHubRateLimitError(GitHubClientError):
    """Raised when GitHub rate limit is exceeded (HTTP 403 / rate limit)."""
    pass


class GitHubClient:
    """Read-only GitHub API client."""

    def __init__(self, secret_backend=None, token: Optional[str] = None, timeout_seconds: int = 10):
        self.secret_backend = secret_backend
        self._token = token
        self.timeout_seconds = timeout_seconds

    def _get_token(self) -> str:
        """Retrieve GitHub token from direct argument or SecretBackend."""
        if self._token:
            return self._token
        if self.secret_backend:
            try:
                token_bytes = self.secret_backend.retrieve(GITHUB_TOKEN_REF)
                if token_bytes:
                    return token_bytes.decode('utf-8').strip()
            except Exception as e:
                logger.warning(f"Error retrieving GitHub token from secret backend: {e}")
        raise GitHubAuthError("No GitHub access token available")

    def _request(self, endpoint: str, query_params: Optional[Dict[str, Any]] = None, headers_extra: Optional[Dict[str, str]] = None) -> Any:
        """Execute HTTP GET request against GitHub API."""
        token = self._get_token()
        url = f"{GITHUB_API_BASE}{endpoint}"
        if query_params:
            url += "?" + urllib.parse.urlencode(query_params)

        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'ANNY-Runtime-CustomerZero/1.0'
        }
        if headers_extra:
            headers.update(headers_extra)

        req = urllib.request.Request(url, headers=headers, method='GET')

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw_data = resp.read().decode('utf-8')
                if not raw_data:
                    return {}
                return json.loads(raw_data)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise GitHubAuthError(f"GitHub API Unauthorized (401): {e.reason}")
            elif e.code == 404:
                raise GitHubNotFoundError(f"GitHub API Resource Not Found (404): {endpoint}")
            elif e.code == 403 and 'rate limit' in str(e.reason).lower():
                raise GitHubRateLimitError(f"GitHub API Rate Limit Exceeded (403): {e.reason}")
            else:
                raise GitHubClientError(f"GitHub API HTTP Error ({e.code}): {e.reason}")
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout):
                raise GitHubTimeoutError(f"GitHub API Request timed out: {url}")
            raise GitHubClientError(f"GitHub API Network Error: {e.reason}")
        except socket.timeout:
            raise GitHubTimeoutError(f"GitHub API Socket timed out: {url}")
        except json.JSONDecodeError as e:
            raise GitHubClientError(f"Failed to decode GitHub API JSON response: {e}")

    def get_authenticated_principal(self) -> Dict[str, Any]:
        """Fetch current authenticated GitHub user profile."""
        return self._request("/user")

    def list_organizations(self) -> List[Dict[str, Any]]:
        """List organizations accessible by the authenticated user."""
        return self._request("/user/orgs", query_params={'per_page': 100})

    def list_repositories(self, org: Optional[str] = None) -> List[Dict[str, Any]]:
        """List repositories for an organization or current user."""
        if org:
            endpoint = f"/orgs/{org}/repos"
            params = {'per_page': 100, 'type': 'all'}
        else:
            endpoint = "/user/repos"
            params = {'per_page': 100, 'affiliation': 'owner,collaborator,organization_member'}
        
        res = self._request(endpoint, query_params=params)
        return res if isinstance(res, list) else []

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository metadata."""
        return self._request(f"/repos/{owner}/{repo}")

    def file_exists(self, owner: str, repo: str, path: str, ref: Optional[str] = None) -> bool:
        """Check if a file or directory exists in the repository."""
        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        params = {'ref': ref} if ref else None
        try:
            self._request(endpoint, query_params=params)
            return True
        except GitHubNotFoundError:
            return False
        except GitHubClientError as e:
            if getattr(e, 'status_code', None) == 404:
                return False
            raise

    def get_file(self, owner: str, repo: str, path: str, ref: Optional[str] = None) -> str:
        """Get file contents from repository as plain text."""
        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        params = {'ref': ref} if ref else None
        res = self._request(endpoint, query_params=params)
        
        if isinstance(res, dict) and 'content' in res:
            encoding = res.get('encoding', 'base64')
            content_str = res['content']
            if encoding == 'base64':
                content_bytes = base64.b64decode(content_str)
                return content_bytes.decode('utf-8')
            return content_str
        elif isinstance(res, str):
            return res
        else:
            raise GitHubClientError(f"Unexpected response format for file {path}")

    def search_code(self, repo: str, query: str) -> Dict[str, Any]:
        """Search code in a repository."""
        q = f"repo:{repo} {query}"
        endpoint = "/search/code"
        params = {'q': q}
        return self._request(endpoint, query_params=params)
