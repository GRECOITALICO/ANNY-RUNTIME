"""GitHub client and discovery package."""
from runtime.github.client import (
    GitHubClient,
    GitHubClientError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubTimeoutError,
    GitHubRateLimitError,
)

__all__ = [
    "GitHubClient",
    "GitHubClientError",
    "GitHubAuthError",
    "GitHubNotFoundError",
    "GitHubTimeoutError",
    "GitHubRateLimitError",
]

from runtime.github.engineering import (
    GitHubEngineeringClient,
    GitHubEngineeringError,
    GitHubEngineeringAuthorizationError,
)

__all__ += [
    "GitHubEngineeringClient",
    "GitHubEngineeringError",
    "GitHubEngineeringAuthorizationError",
]
