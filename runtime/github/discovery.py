"""Organization and repository discovery service for ANNY Runtime."""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import logging
from runtime.github.client import GitHubClient, GitHubClientError

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredPrincipal:
    """Discovered GitHub principal."""
    login: str
    identity_type: str = "User"
    authorization_state: str = "AUTHORIZED"
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveredOrganization:
    """Discovered GitHub organization."""
    login: str
    display_name: Optional[str] = None
    repository_count: int = 0
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveredRepository:
    """Discovered GitHub repository."""
    full_name: str
    name: str
    owner: str
    visibility: str = "public"
    archived: bool = False
    default_branch: str = "main"
    latest_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OrganizationDiscoveryService:
    """Discovers accessible GitHub principal, organizations, and repositories."""

    def __init__(self, github_client: GitHubClient):
        self.github_client = github_client

    def discover_principal(self) -> Optional[DiscoveredPrincipal]:
        """Discover the authenticated GitHub user profile."""
        user_data = self.github_client.get_authenticated_principal()
        return DiscoveredPrincipal(
            login=user_data.get('login', 'unknown'),
            identity_type=user_data.get('type', 'User'),
            authorization_state="AUTHORIZED",
            raw_metadata={
                'id': user_data.get('id'),
                'name': user_data.get('name'),
                'email': user_data.get('email')
            }
        )

    def discover_organizations(self) -> List[DiscoveredOrganization]:
        """Discover accessible GitHub organizations."""
        orgs_data = self.github_client.list_organizations()
        result = []
        for org in orgs_data:
            result.append(
                DiscoveredOrganization(
                    login=org.get('login', ''),
                    display_name=org.get('description') or org.get('login'),
                    repository_count=org.get('public_repos', 0),
                    raw_metadata={'id': org.get('id'), 'url': org.get('url')}
                )
            )
        return result

    def discover_repositories(self, org: Optional[str] = None) -> List[DiscoveredRepository]:
        """Discover accessible repositories for an organization or authenticated principal."""
        repos_data = self.github_client.list_repositories(org=org)
        result = []
        for repo in repos_data:
            full_name = repo.get('full_name', '')
            owner = repo.get('owner', {}).get('login', '') if isinstance(repo.get('owner'), dict) else ''
            name = repo.get('name', '')
            is_private = repo.get('private', False)
            visibility = "private" if is_private else "public"
            
            result.append(
                DiscoveredRepository(
                    full_name=full_name,
                    name=name,
                    owner=owner,
                    visibility=visibility,
                    archived=repo.get('archived', False),
                    default_branch=repo.get('default_branch', 'main'),
                    latest_metadata={
                        'description': repo.get('description'),
                        'pushed_at': repo.get('pushed_at'),
                        'updated_at': repo.get('updated_at'),
                        'stargazers_count': repo.get('stargazers_count', 0)
                    }
                )
            )
        return result
