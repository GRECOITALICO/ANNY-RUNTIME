# GitHub Authorization Architecture

ANNY Runtime has one GitHub credential boundary. The Runtime owns the credential, validates it against GitHub, stores it through `SecretBackend`, and exposes only sanitized authentication status to the admin UI.

## Onboarding methods

The preferred onboarding path is GitHub OAuth Device Flow when a public GitHub OAuth client ID is configured.

The manual Personal Access Token path remains the recovery and fallback method. Both paths are validated before Runtime considers GitHub authorization usable.

### Device Flow

Set the public OAuth application client ID through either:

- `ANNY_GITHUB_CLIENT_ID` in the Runtime process environment; or
- `github_client_id` in the Runtime `config.yaml`.

The client ID is not a secret. The GitHub OAuth application must have Device Flow enabled.

The Device Flow requests the scopes required by the current Runtime boundary: `repo` and `read:org`. Runtime also verifies the granted scopes from GitHub before marking the credential `AUTHORIZED`.

A missing client ID does not dead-end onboarding: the first-run UI keeps the manual token path available.

### Manual token fallback

The admin panel accepts a GitHub access token over the authenticated local onboarding route. Runtime validates:

1. `GET https://api.github.com/user`;
2. the authenticated principal;
3. the granted GitHub scopes, requiring `repo` and `read:org`.

The token is encrypted by `SecretBackend` before persistent storage and is never returned to HTML, JSON status DTOs, telemetry or audit messages.

## Credential boundaries

- Admin browser sessions are separate from GitHub credentials.
- GitHub credentials are separate from ANNY Runtime identity keys.
- Repository Fabric uses the Runtime GitHub client; Fabric organization/repository binding comes only from `RuntimeConfig`.
- No product repository, organization, Fabric repository, or cloud provider is hardcoded into the authentication path.
- An invalid or insufficiently scoped credential never becomes `AUTHORIZED`.
- Device Flow tokens that fail post-authorization validation are removed instead of being retained as unusable credentials.

## Startup contract

The supported installation path is `scripts/install.sh`. It generates the actual systemd/user service and supplies the Runtime environment. A second static systemd service definition is intentionally not shipped, so it cannot diverge from the installer-generated startup path.

## Current source of truth

The current Runtime startup chain is:

`installer → generated systemd service → /usr/local/bin/anny-runtime server → cli/main.py → start_admin_server() → RuntimeConfig → GitHubAuthManager / GitHubClient → Repository Fabric adapter`

The organizational ANNY bootstrap remains separate from the Runtime substrate and is resolved by `GRECOITALICO/ANNY-OPERATIONAL/state/BOOTSTRAP_REGISTRY.yaml`.
