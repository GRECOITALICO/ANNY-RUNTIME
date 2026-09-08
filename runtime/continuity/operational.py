"""Operational repository provider for reading ANNY-OPERATIONAL canonical state."""
import logging
import os
import json
from typing import Optional, Dict, Any, List
import yaml

from runtime.github.client import GitHubClient, GitHubClientError, GitHubNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_OPERATIONAL_OWNER = "GRECOITALICO"
DEFAULT_OPERATIONAL_REPOS = ["ANNY-OPERATIONAL", "ANNY"]


class OperationalRepositoryProvider:
    """Reads canonical state from GRECOITALICO/ANNY-OPERATIONAL repository."""

    def __init__(self, github_client: Optional[GitHubClient] = None, local_path_override: Optional[str] = None):
        self.github_client = github_client
        self.local_path_override = local_path_override
        self._resolved_repo: Optional[Dict[str, str]] = None

    def resolve_operational_repository(self) -> Optional[Dict[str, str]]:
        """Resolve which repository is the canonical operational repository."""
        if self._resolved_repo:
            return self._resolved_repo

        if self.local_path_override and os.path.exists(self.local_path_override):
            self._resolved_repo = {
                'type': 'local',
                'path': self.local_path_override,
                'full_name': 'local/ANNY-OPERATIONAL'
            }
            return self._resolved_repo

        if not self.github_client:
            return None

        # Attempt to find ANNY-OPERATIONAL first, then ANNY
        for repo_name in DEFAULT_OPERATIONAL_REPOS:
            try:
                repo = self.github_client.get_repository(DEFAULT_OPERATIONAL_OWNER, repo_name)
                if repo:
                    self._resolved_repo = {
                        'type': 'github',
                        'owner': DEFAULT_OPERATIONAL_OWNER,
                        'repo': repo_name,
                        'full_name': f"{DEFAULT_OPERATIONAL_OWNER}/{repo_name}",
                        'default_branch': repo.get('default_branch', 'main')
                    }
                    logger.info(f"Resolved operational repository: {self._resolved_repo['full_name']}")
                    return self._resolved_repo
            except GitHubNotFoundError:
                continue
            except GitHubClientError as e:
                logger.warning(f"Error checking {DEFAULT_OPERATIONAL_OWNER}/{repo_name}: {e}")
                continue

        return None

    def _read_file_content(self, relative_path: str) -> Optional[str]:
        """Read text content of a file from operational repo or local path."""
        repo_info = self.resolve_operational_repository()
        if not repo_info:
            return None

        if repo_info['type'] == 'local':
            full_path = os.path.join(repo_info['path'], relative_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception as e:
                    logger.error(f"Failed to read local file {full_path}: {e}")
                    return None
            return None

        elif repo_info['type'] == 'github':
            try:
                return self.github_client.get_file(
                    owner=repo_info['owner'],
                    repo=repo_info['repo'],
                    path=relative_path,
                    ref=repo_info.get('default_branch')
                )
            except GitHubNotFoundError:
                logger.warning(f"File not found in GitHub operational repo: {relative_path}")
                return None
            except GitHubClientError as e:
                logger.error(f"Error fetching file {relative_path} from GitHub: {e}")
                return None

        return None

    def _parse_yaml_or_json(self, content: str) -> Optional[Any]:
        """Parse string content as YAML or JSON."""
        if not content:
            return None
        try:
            return yaml.safe_load(content)
        except Exception:
            try:
                return json.loads(content)
            except Exception as e:
                logger.error(f"Failed to parse content as YAML/JSON: {e}")
                return None

    def read_bootstrap(self) -> Optional[str]:
        """Read BOOTSTRAP.md content."""
        return self._read_file_content("BOOTSTRAP.md")

    def read_current_state(self) -> Optional[Dict[str, Any]]:
        """Read and parse state/CURRENT_STATE.yaml."""
        content = self._read_file_content("state/CURRENT_STATE.yaml")
        if content:
            parsed = self._parse_yaml_or_json(content)
            return parsed if isinstance(parsed, dict) else None
        return None

    def read_current_mission(self) -> Optional[Dict[str, Any]]:
        """Read and parse state/CURRENT_MISSION.yaml."""
        content = self._read_file_content("state/CURRENT_MISSION.yaml")
        if content:
            parsed = self._parse_yaml_or_json(content)
            if isinstance(parsed, dict):
                parsed['_raw_content'] = content
                return parsed
        return None

    def read_blockers(self) -> Optional[Dict[str, Any]]:
        """Read and parse state/BLOCKERS.yaml."""
        content = self._read_file_content("state/BLOCKERS.yaml")
        if content:
            parsed = self._parse_yaml_or_json(content)
            return parsed if isinstance(parsed, dict) else None
        return None

    def read_next_action(self) -> Optional[Dict[str, Any]]:
        """Read and parse state/NEXT_ACTION.yaml."""
        content = self._read_file_content("state/NEXT_ACTION.yaml")
        if content:
            parsed = self._parse_yaml_or_json(content)
            return parsed if isinstance(parsed, dict) else None
        return None

    def read_l2_registry(self) -> Optional[List[Dict[str, Any]]]:
        """Read L2 worker registry if present."""
        for path in ["state/OFFICE_REGISTRY_001.json", "state/L2_WORKER_REGISTRY.yaml"]:
            content = self._read_file_content(path)
            if content:
                parsed = self._parse_yaml_or_json(content)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict) and 'workers' in parsed:
                    return parsed['workers']
        return []

    def read_referenced_evidence(self, evidence_ref: str) -> Optional[str]:
        """Read referenced evidence file content."""
        return self._read_file_content(evidence_ref)
