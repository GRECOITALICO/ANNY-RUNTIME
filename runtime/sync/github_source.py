"""Configured GitHub release discovery for governed ANNY Runtime Sync."""

from __future__ import annotations

from typing import Any, Dict

from runtime.github.client import GitHubClient


class GitHubReleaseSource:
    """Discover the latest release from an explicitly configured repository.

    Configuration is treated as source selection, not as proof that a candidate is
    safe to activate. Candidate verification remains a separate contract.
    """

    def __init__(self, github_client: GitHubClient, repository: str) -> None:
        self.github_client = github_client
        self.repository = self._validate_repository(repository)

    @staticmethod
    def _validate_repository(repository: str) -> str:
        value = (repository or "").strip()
        parts = value.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("Update source repository must be owner/name")
        return value

    def discover(self) -> Dict[str, Any]:
        owner, repo = self.repository.split("/", 1)
        release = self.github_client._request(f"/repos/{owner}/{repo}/releases/latest")
        if not isinstance(release, dict):
            raise RuntimeError("Invalid GitHub release response")

        tag = release.get("tag_name")
        if not tag:
            return {
                "source": f"github:{self.repository}",
                "revision": release.get("id"),
                "candidate_version": None,
                "authorized": False,
                "reason": "RELEASE_TAG_UNAVAILABLE",
            }

        if release.get("draft") or release.get("prerelease"):
            return {
                "source": f"github:{self.repository}",
                "revision": release.get("id") or release.get("target_commitish"),
                "candidate_version": tag,
                "authorized": False,
                "reason": "NON_STABLE_RELEASE",
            }

        return {
            "source": f"github:{self.repository}",
            "revision": release.get("id") or release.get("target_commitish"),
            "candidate_version": tag,
            "authorized": True,
            "release_id": release.get("id"),
            "published_at": release.get("published_at"),
            "html_url": release.get("html_url"),
            "assets": [
                {
                    "name": asset.get("name"),
                    "size": asset.get("size"),
                    "browser_download_url": asset.get("browser_download_url"),
                }
                for asset in (release.get("assets") or [])
                if isinstance(asset, dict)
            ],
        }
