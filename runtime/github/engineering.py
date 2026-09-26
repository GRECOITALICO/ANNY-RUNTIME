"""Governed GitHub engineering operations for ANNY Runtime.

This module extends the existing read-oriented GitHub client with explicit
repository engineering mutations. Every mutation is bound to a canonical
ExecutionContext capability grant and uses the GitHub REST API directly.
"""

from __future__ import annotations

import base64
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from runtime.github.client import GitHubClient, GitHubClientError
from runtime.security.execution_context import ExecutionContext


API_BASE = "https://api.github.com"
API_VERSION = "2026-03-10"


class GitHubEngineeringError(GitHubClientError):
    """Base error for governed GitHub engineering operations."""


class GitHubEngineeringAuthorizationError(GitHubEngineeringError):
    """Raised when Runtime context does not authorize an operation."""


class GitHubEngineeringClient:
    """Provider-neutral GitHub engineering client with explicit capability gates."""

    def __init__(
        self,
        github_client: GitHubClient,
        *,
        current_generation_provider=None,
    ) -> None:
        self.github_client = github_client
        self.current_generation_provider = current_generation_provider

    def _authorize(self, context: ExecutionContext, capability: str) -> None:
        if not isinstance(context, ExecutionContext):
            raise GitHubEngineeringAuthorizationError("Canonical ExecutionContext required")
        current_generation = (
            self.current_generation_provider()
            if self.current_generation_provider is not None
            else context.generation
        )
        if not context.is_valid(__import__("datetime").datetime.now(__import__("datetime").timezone.utc), current_generation):
            raise GitHubEngineeringAuthorizationError("ExecutionContext expired or generation-stale")
        if not context.has_capability(capability):
            raise GitHubEngineeringAuthorizationError(
                f"GitHub operation requires capability {capability}"
            )

    def _request(
        self,
        context: ExecutionContext,
        capability: str,
        method: str,
        endpoint: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        self._authorize(context, capability)
        token = self.github_client._get_token()
        url = f"{API_BASE}{endpoint}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "ANNY-Runtime/1.0",
        }
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.github_client.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubEngineeringError(
                f"GitHub API {method.upper()} {endpoint} failed with {exc.code}: {detail[:1000]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GitHubEngineeringError(
                f"GitHub API network failure for {endpoint}: {exc.reason}"
            ) from exc
        except socket.timeout as exc:
            raise GitHubEngineeringError(
                f"GitHub API timeout for {endpoint}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise GitHubEngineeringError(
                f"GitHub API returned invalid JSON for {endpoint}"
            ) from exc

    @staticmethod
    def _repo_path(owner: str, repo: str, suffix: str = "") -> str:
        return f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}{suffix}"

    def get_repository(self, context: ExecutionContext, owner: str, repo: str) -> Dict[str, Any]:
        return self._request(context, "GITHUB_READ", "GET", self._repo_path(owner, repo))

    def list_branches(self, context: ExecutionContext, owner: str, repo: str, *, per_page: int = 100) -> Any:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, "/branches"),
            query={"per_page": min(max(per_page, 1), 100)},
        )

    def compare_commits(self, context: ExecutionContext, owner: str, repo: str, base: str, head: str) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, f"/compare/{urllib.parse.quote(base, safe='') }...{urllib.parse.quote(head, safe='') }"),
        )

    def create_ref(self, context: ExecutionContext, owner: str, repo: str, ref: str, sha: str) -> Dict[str, Any]:
        if not ref.startswith("refs/heads/"):
            raise ValueError("Only refs/heads/* are supported by this method")
        return self._request(
            context,
            "GITHUB_WRITE",
            "POST",
            self._repo_path(owner, repo, "/git/refs"),
            body={"ref": ref, "sha": sha},
        )

    def update_ref(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        ref: str,
        sha: str,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not ref.startswith("heads/") and not ref.startswith("refs/heads/"):
            raise ValueError("Only branch refs are supported")
        ref_path = ref.removeprefix("refs/")
        return self._request(
            context,
            "GITHUB_WRITE",
            "PATCH",
            self._repo_path(owner, repo, f"/git/refs/{urllib.parse.quote(ref_path, safe='')}"),
            body={"sha": sha, "force": bool(force)},
        )

    def get_content(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = {"ref": ref} if ref else None
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, f"/contents/{path.lstrip('/')}"),
            query=query,
        )

    def write_content(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        path: str,
        content: str,
        *,
        message: str,
        branch: str,
        sha: Optional[str] = None,
        committer: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        if committer:
            payload["committer"] = dict(committer)
        return self._request(
            context,
            "GITHUB_WRITE",
            "PUT",
            self._repo_path(owner, repo, f"/contents/{path.lstrip('/')}"),
            body=payload,
        )

    def list_pull_requests(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        per_page: int = 100,
    ) -> Any:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, "/pulls"),
            query={"state": state, "per_page": min(max(per_page, 1), 100)},
        )

    def get_pull_request(self, context: ExecutionContext, owner: str, repo: str, number: int) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, f"/pulls/{int(number)}"),
        )

    def create_pull_request(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = True,
    ) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_PR_WRITE",
            "POST",
            self._repo_path(owner, repo, "/pulls"),
            body={
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": bool(draft),
            },
        )

    def update_pull_request(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        number: int,
        **fields: Any,
    ) -> Dict[str, Any]:
        allowed = {"title", "body", "state", "base", "maintainer_can_modify", "draft"}
        payload = {k: v for k, v in fields.items() if k in allowed}
        if not payload:
            raise ValueError("No supported pull request update fields supplied")
        return self._request(
            context,
            "GITHUB_PR_WRITE",
            "PATCH",
            self._repo_path(owner, repo, f"/pulls/{int(number)}"),
            body=payload,
        )

    def create_issue(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str = "",
        labels: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        return self._request(
            context,
            "GITHUB_ISSUE_WRITE",
            "POST",
            self._repo_path(owner, repo, "/issues"),
            body=payload,
        )

    def update_issue(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        number: int,
        **fields: Any,
    ) -> Dict[str, Any]:
        allowed = {"title", "body", "state", "state_reason", "labels", "assignees", "milestone"}
        payload = {k: v for k, v in fields.items() if k in allowed}
        if not payload:
            raise ValueError("No supported issue update fields supplied")
        return self._request(
            context,
            "GITHUB_ISSUE_WRITE",
            "PATCH",
            self._repo_path(owner, repo, f"/issues/{int(number)}"),
            body=payload,
        )

    def create_issue_comment(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_ISSUE_WRITE",
            "POST",
            self._repo_path(owner, repo, f"/issues/{int(issue_number)}/comments"),
            body={"body": body},
        )

    def list_pull_request_reviews(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        number: int,
        *,
        per_page: int = 100,
    ) -> Any:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, f"/pulls/{int(number)}/reviews"),
            query={"per_page": min(max(per_page, 1), 100)},
        )

    def create_pull_request_review(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        number: int,
        *,
        body: str = "",
        event: str = "COMMENT",
        comments: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"body": body, "event": event}
        if comments:
            payload["comments"] = comments
        return self._request(
            context,
            "GITHUB_PR_WRITE",
            "POST",
            self._repo_path(owner, repo, f"/pulls/{int(number)}/reviews"),
            body=payload,
        )

    def list_releases(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        *,
        per_page: int = 100,
    ) -> Any:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, "/releases"),
            query={"per_page": min(max(per_page, 1), 100)},
        )

    def get_release(self, context: ExecutionContext, owner: str, repo: str, release_id: int) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, f"/releases/{int(release_id)}"),
        )

    def create_release(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        *,
        tag_name: str,
        name: str,
        target_commitish: Optional[str] = None,
        body: str = "",
        draft: bool = True,
        prerelease: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "tag_name": tag_name,
            "name": name,
            "body": body,
            "draft": bool(draft),
            "prerelease": bool(prerelease),
        }
        if target_commitish:
            payload["target_commitish"] = target_commitish
        return self._request(
            context,
            "GITHUB_WRITE",
            "POST",
            self._repo_path(owner, repo, "/releases"),
            body=payload,
        )

    def list_tags(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        *,
        per_page: int = 100,
    ) -> Any:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, "/tags"),
            query={"per_page": min(max(per_page, 1), 100)},
        )

    def get_branch_protection(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        branch: str,
    ) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, f"/branches/{urllib.parse.quote(branch, safe='')}/protection"),
        )

    def list_workflows(self, context: ExecutionContext, owner: str, repo: str) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, "/actions/workflows"),
        )

    def list_workflow_runs(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        *,
        workflow_id: Optional[str] = None,
        branch: Optional[str] = None,
        per_page: int = 100,
    ) -> Dict[str, Any]:
        suffix = "/actions/runs" if workflow_id is None else f"/actions/workflows/{urllib.parse.quote(str(workflow_id), safe='')}/runs"
        query: Dict[str, Any] = {"per_page": min(max(per_page, 1), 100)}
        if branch:
            query["branch"] = branch
        return self._request(context, "GITHUB_READ", "GET", self._repo_path(owner, repo, suffix), query=query)

    def get_workflow_run(self, context: ExecutionContext, owner: str, repo: str, run_id: int) -> Dict[str, Any]:
        return self._request(
            context,
            "GITHUB_READ",
            "GET",
            self._repo_path(owner, repo, f"/actions/runs/{int(run_id)}"),
        )

    def dispatch_workflow(
        self,
        context: ExecutionContext,
        owner: str,
        repo: str,
        workflow_id: str,
        *,
        ref: str,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ref": ref}
        if inputs:
            if len(inputs) > 25:
                raise ValueError("GitHub workflow dispatch accepts at most 25 inputs")
            payload["inputs"] = inputs
        return self._request(
            context,
            "GITHUB_ACTIONS_DISPATCH",
            "POST",
            self._repo_path(owner, repo, f"/actions/workflows/{urllib.parse.quote(str(workflow_id), safe='')}/dispatches"),
            body=payload,
        )
