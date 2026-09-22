import pytest

from runtime.admin.server import build_fabric_client
from runtime.core.config import RuntimeConfig
from runtime.fabric.github_adapter import FabricError


class FakeGitHubClient:
    pass


def test_admin_fabric_client_uses_runtime_config() -> None:
    config = RuntimeConfig(
        data_dir="/tmp/anny-runtime-test",
        fabric_org="GRECOITALICO",
        fabric_repo="REPOSITORY-FABRIC",
    )
    client = build_fabric_client(FakeGitHubClient(), config)
    assert client is not None
    assert client.org == "GRECOITALICO"
    assert client.repo == "REPOSITORY-FABRIC"


def test_admin_fabric_client_fails_closed_without_binding() -> None:
    config = RuntimeConfig(data_dir="/tmp/anny-runtime-test")
    with pytest.raises(FabricError, match="FABRIC_CONFIG_MISSING"):
        build_fabric_client(FakeGitHubClient(), config)


def test_admin_fabric_client_is_absent_without_github_client() -> None:
    config = RuntimeConfig(
        data_dir="/tmp/anny-runtime-test",
        fabric_org="GRECOITALICO",
        fabric_repo="REPOSITORY-FABRIC",
    )
    assert build_fabric_client(None, config) is None
