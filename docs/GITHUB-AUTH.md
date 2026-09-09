# GitHub Authorization Architecture

The ANNY Runtime uses **GitHub Access Token** (paste-based) as the **current Customer Zero onboarding method**. The user provides a single GitHub Personal Access Token through the admin panel, which is validated, encrypted, and stored securely.

> **Device Flow (RFC 8628)** is retained internally as an **optional future authentication method**. It is NOT the primary onboarding mechanism for Customer Zero.

## Authorization Flow (Current — Token-Based)

1. **First Run:** The user opens the admin panel at `http://127.0.0.1:3643/`.
2. **Token Entry:** The panel presents a single password input labeled "GITHUB ACCESS TOKEN" and a "CONNECT" button.
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
