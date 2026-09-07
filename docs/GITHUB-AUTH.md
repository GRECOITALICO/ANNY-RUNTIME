# GitHub Authorization Architecture

The ANNY Runtime uses **GitHub Device Flow (RFC 8628)** for credential acquisition. This ensures that the local Runtime securely negotiates its own token without requiring the user to copy-paste sensitive Personal Access Tokens into config files.

## Authorization Flow

1. **Initiation:** The Admin clicks "Connect GitHub" in the admin panel.
2. **Device Code:** The Runtime contacts GitHub and receives a Device Code, User Code, and Verification URI.
3. **User Action:** The browser displays the User Code and a link to GitHub. The user opens GitHub, logs in, and enters the code.
4. **Polling:** Meanwhile, the Runtime polls GitHub (`/login/oauth/access_token`).
5. **Acquisition:** Once the user approves the prompt on GitHub, the Runtime receives the Access Token.
6. **Secure Storage:** The token is immediately encrypted and persisted to disk via the `SecretBackend`. **It is never returned to the browser.**

## Credential Safety

- The admin panel **never** exposes the raw GitHub token.
- The `/github` endpoint only returns sanitized DTOs containing the principal name, scopes, and status.
- Token renewal follows the same flow; the new token is validated before replacing the old token (safe rotation).

## Runtime Capability Boundary

The GitHub credential belongs to the **Runtime Engine**. It is used by the `ExecutionPipeline` to perform authorized operations (e.g., reading organizational state or pushing verified code). 

Even with a valid GitHub credential, a local user *cannot* use the web panel to push arbitrary code to GitHub. They must initiate an authorized operation through the proper ANNY channels.
