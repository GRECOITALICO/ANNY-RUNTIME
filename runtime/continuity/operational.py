"""Operational repository provider for reading canonical state from the resolved operational repository."""
import logging
import os
import json
from typing import Optional, Dict, Any, List
import yaml

from runtime.github.client import GitHubClient, GitHubClientError, GitHubNotFoundError

logger = logging.getLogger(__name__)

class OperationalRepositoryAmbiguousError(Exception):
    """Raised when multiple valid operational repositories are found."""
    pass

class OperationalRepositoryNotFoundError(Exception):
    """Raised when no operational repositories are found."""
    pass


class OperationalRepositoryProvider:
    """Reads canonical state from the dynamically discovered operational repository."""

    def __init__(self, github_client: Optional[GitHubClient] = None, local_path_override: Optional[str] = None, environment: str = "PRODUCTION"):
        self.github_client = github_client
        self.local_path_override = local_path_override
        self.environment = environment
        self._resolved_repo: Optional[Dict[str, str]] = None

    def resolve_operational_repository(self) -> Optional[Dict[str, str]]:
        """Resolve which repository is the canonical operational repository."""
        if self._resolved_repo:
            return self._resolved_repo

        if self.local_path_override:
            if self.environment == "PRODUCTION":
                logger.error("PRODUCTION environment rejects local_path_override. Configuration ignored.")
            elif self.environment in ("CONTROLLED_TEST", "CUSTOMER_ZERO_TEST"):
                if os.path.exists(self.local_path_override):
                    self._resolved_repo = {
                        'type': 'local',
                        'path': self.local_path_override,
                        'full_name': 'LOCAL_CONTROLLED_TEST'
                    }
                    logger.info("Using local override for Operational Repository: LOCAL_CONTROLLED_TEST")
                    return self._resolved_repo

        if not self.github_client:
            return None

        # 1. Check principal and orgs repos
        candidates = []
        try:
            # Gather repos
            all_repos = self.github_client.list_repositories()
            
            for repo in all_repos:
                if not repo: continue
                owner = repo.get('owner', {}).get('login')
                repo_name = repo.get('name')
                if not owner or not repo_name:
                    continue
                
                # Check topics for explicit marker
                topics = repo.get('topics', [])
                if 'anny-operational' in topics:
                    candidates.append({
                        'type': 'github',
                        'owner': owner,
                        'repo': repo_name,
                        'full_name': f"{owner}/{repo_name}",
                        'default_branch': repo.get('default_branch', 'main')
                    })
                    continue
                
                # Check for explicit .anny/operational.yaml marker, then BOOTSTRAP.md
                try:
                    if self.github_client.file_exists(owner, repo_name, ".anny/operational.yaml", ref=repo.get('default_branch', 'main')):
                        candidates.append({
                            'type': 'github',
                            'owner': owner,
                            'repo': repo_name,
                            'full_name': f"{owner}/{repo_name}",
                            'default_branch': repo.get('default_branch', 'main')
                        })
                        continue

                    if self.github_client.file_exists(owner, repo_name, "BOOTSTRAP.md", ref=repo.get('default_branch', 'main')):
                        candidates.append({
                            'type': 'github',
                            'owner': owner,
                            'repo': repo_name,
                            'full_name': f"{owner}/{repo_name}",
                            'default_branch': repo.get('default_branch', 'main')
                        })
                except GitHubClientError as e:
                    # P0-C: Stop discovery on network/auth errors, do not treat as "not candidate"
                    status_code = getattr(e, 'status_code', None)
                    if status_code == 401:
                        logger.error(f"Unauthorized accessing {owner}/{repo_name}")
                        raise OperationalRepositoryNotFoundError("UNAUTHORIZED")
                    elif status_code == 403:
                        if "rate limit" in str(e).lower():
                            raise OperationalRepositoryNotFoundError("RATE_LIMITED")
                        raise OperationalRepositoryNotFoundError("FORBIDDEN")
                    else:
                        raise OperationalRepositoryNotFoundError("UNKNOWN_ERROR")

        except GitHubClientError as e:
            logger.warning(f"Failed to list repos for operational resolution: {e}")
            raise OperationalRepositoryNotFoundError("NETWORK_ERROR")

        # 5. select only if exactly one valid candidate is identified
        if len(candidates) == 0:
            logger.info("No operational repository candidates found.")
            raise OperationalRepositoryNotFoundError("OPERATIONAL_REPOSITORY_NOT_FOUND")
        elif len(candidates) == 1:
            self._resolved_repo = candidates[0]
            logger.info(f"Resolved operational repository: {self._resolved_repo['full_name']}")
            return self._resolved_repo
        else:
            names = [c['full_name'] for c in candidates]
            logger.warning(f"Ambiguous operational repositories found: {names}")
            raise OperationalRepositoryAmbiguousError(f"OPERATIONAL_REPOSITORY_AMBIGUOUS: {names}")

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

        return None

    def path_exists(self, relative_path: str) -> bool:
        """Check if a path exists (file or directory)."""
        repo_info = self.resolve_operational_repository()
        if not repo_info:
            return False

        if repo_info['type'] == 'local':
            return os.path.exists(os.path.join(repo_info['path'], relative_path))
        
        elif repo_info['type'] == 'github':
            return self.github_client.file_exists(
                owner=repo_info['owner'],
                repo=repo_info['repo'],
                path=relative_path,
                ref=repo_info.get('default_branch')
            )
        return False

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
