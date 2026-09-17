# SYNC-IMPLEMENTATION-001-D — Evidence

Status: `IMPLEMENTED_NOT_VERIFIED`

## Scope

Added an explicit GitHub Release discovery provider for the Runtime Sync subsystem.

Configuration:

```text
ANNY_UPDATE_SOURCE_REPO=owner/name
```

Optional local runtime version:

```text
ANNY_RUNTIME_VERSION=vX.Y.Z
```

## Semantics

The configured repository is an explicit source selector. It is **not** treated as proof that a release is safe to activate.

Discovery returns:

- source identity;
- release revision/id;
- candidate version/tag;
- publication metadata;
- release assets;
- stable/non-stable classification.

Draft and prerelease candidates resolve to `authorized=false` and remain blocked from candidate progression.

A stable release is only a discovered candidate. Independent candidate verification remains required.

## Integrated behavior

The admin server now constructs `GitHubReleaseSource` only when both:

1. a GitHub client is available; and
2. `ANNY_UPDATE_SOURCE_REPO` is explicitly configured.

Without either prerequisite, Sync remains fail-closed/unknown rather than inventing a source.

## Tests added

`tests/test_github_release_source.py` covers:

- stable release discovery;
- prerelease rejection;
- repository configuration validation.

## Verification boundary

No current repository-wide CI result is available for this milestone. The implementation is therefore recorded as `IMPLEMENTED_NOT_VERIFIED`, not `VERIFIED`.

## Next

Implement candidate verification using release artifact identity, checksum/signature/provenance evidence, then persist evidence IDs into the Sync result. No Stage/Activate capability should be wired before that gate passes.
