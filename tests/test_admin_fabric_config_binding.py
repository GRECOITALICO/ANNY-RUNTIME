from runtime.admin.server import build_fabric_client
from runtime.core.config import RuntimeConfig


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


def test_admin_fabric_client_is_not_configured_without_binding() -> None:
    config = RuntimeConfig(data_dir="/tmp/anny-runtime-test")
    assert build_fabric_client(FakeGitHubClient(), config) is None


def test_admin_fabric_client_is_absent_without_github_client() -> None:
    config = RuntimeConfig(
        data_dir="/tmp/anny-runtime-test",
        fabric_org="GRECOITALICO",
        fabric_repo="REPOSITORY-FABRIC",
    )
    assert build_fabric_client(None, config) is None
