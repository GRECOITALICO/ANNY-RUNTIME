from runtime.sync.github_source import GitHubReleaseSource


class FakeGitHubClient:
    def __init__(self, payload):
        self.payload = payload

    def _request(self, endpoint):
        assert endpoint == "/repos/example/anny-runtime/releases/latest"
        return self.payload


def test_release_source_discovers_stable_release():
    source = GitHubReleaseSource(
        FakeGitHubClient({
            "id": 123,
            "tag_name": "v0.5.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-09-17T00:00:00Z",
            "html_url": "https://example.invalid/release",
            "assets": [{"name": "anny-runtime.tar.gz", "size": 10, "browser_download_url": "https://example.invalid/a"}],
        }),
        "example/anny-runtime",
    )

    result = source.discover()

    assert result["authorized"] is True
    assert result["candidate_version"] == "v0.5.0"
    assert result["source"] == "github:example/anny-runtime"
    assert result["assets"][0]["name"] == "anny-runtime.tar.gz"


def test_release_source_rejects_prerelease_as_authorized():
    source = GitHubReleaseSource(
        FakeGitHubClient({
            "id": 124,
            "tag_name": "v0.6.0-rc1",
            "draft": False,
            "prerelease": True,
        }),
        "example/anny-runtime",
    )

    result = source.discover()

    assert result["authorized"] is False
    assert result["reason"] == "NON_STABLE_RELEASE"


def test_release_source_validates_repository_shape():
    try:
        GitHubReleaseSource(FakeGitHubClient({}), "not-a-repository")
    except ValueError as exc:
        assert "owner/name" in str(exc)
    else:
        raise AssertionError("invalid repository shape must fail closed")
