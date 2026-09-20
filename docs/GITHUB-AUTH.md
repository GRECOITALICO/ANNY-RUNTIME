# GitHub Authorization Architecture

The customer-facing onboarding architecture is defined by
[ADR-022](ADR-022-CUSTOMER-ZERO-GITHUB-AUTH.md). It selects an ANNY-hosted
GitHub App authorization callback and a Runtime-bound one-time grant. A new
customer must only click `CONNECT GITHUB` and complete GitHub's normal
login/consent flow. They must never configure a client ID, client secret,
access token, scope, or device code.

The local Device Flow and token-entry implementations described below are
legacy engineering paths. They are **not** the customer-zero onboarding
contract and must fail closed unless explicitly enabled for an internal,
non-customer engineering workflow. They do not make customer onboarding
available in the absence of the ANNY authorization service.

## Legacy engineering flow: Device Flow

1. The Runtime operator configures the OAuth application's public client ID in the service environment as `GITHUB_CLIENT_ID`. No OAuth client secret is required or accepted by the Runtime Device Flow.
2. On first run, `CONNECT GITHUB` posts a session-bound CSRF token to `/github/device/init`.
3. The Runtime displays GitHub's device verification URI and user code, then permits `/github/device/poll` only within the restricted onboarding session.
4. On GitHub authorization, the Runtime validates and stores the access token through `SecretBackend`, discovers the available GitHub scope, revokes the onboarding session, and issues a regular admin session.
5. If the client ID is not configured, initiation fails closed and onboarding remains restricted.

## Legacy engineering flow: Token Recovery/Migration

1. **First Run:** The user opens the admin panel at `http://127.0.0.1:3643/`.
2. **Token Entry:** The panel presents a password input labeled "GITHUB ACCESS TOKEN" only in the recovery/migration interface.
3. **Validation:** The Runtime validates the token against `GET https://api.github.com/user`, checks required scopes (`repo`, `read:org`), and extracts the authenticated principal.
4. **Secure Storage:** The token is immediately encrypted and persisted to disk via the `SecretBackend`. **It is never returned to the browser.**
5. **Discovery:** Organizations and repositories are discovered dynamically.
6. **Session Upgrade:** The onboarding session is revoked and a regular admin session is created.

## Credential Safety

- The admin panel **never** exposes the raw GitHub token.
- The `/github` endpoint only returns sanitized DTOs containing the principal name, scopes, and status.
- Token renewal follows the same flow; the new token is validated before replacing the old token (safe rotation).

## Runtime Capability Boundary

The GitHub credential belongs to the **Runtime Engine**. It is used by the `ExecutionPipeline` to perform authorized operations (e.g., reading organizational state or pushing verified code). 

Even with a valid GitHub credential, a local user *cannot* use the web panel to push arbitrary code to GitHub. They must initiate an authorized operation through the proper ANNY channels.
