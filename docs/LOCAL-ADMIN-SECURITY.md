# Local Administration Security Model

The ANNY Runtime Administration Panel implements a strict security model to ensure it cannot be weaponized as a backdoor into the system.

## 1. Network Exposure (No-LAN)
The server binds exclusively to `127.0.0.1` by default. It cannot be accessed by other machines on the local network (LAN) unless explicitly reconfigured via the `admin_host` setting (which requires physical file access).

## 2. Local Authentication
The panel automatically grants access only to requests originating from `127.0.0.1` (or localhost). 
- There is no default password (`admin/admin`).
- You cannot bypass auth using `?admin=true` if accessing via network.

## 3. Session Expiry & Cookies
Upon successful local connection, the server issues an `admin_session_id`.
- The cookie is marked `HttpOnly` (inaccessible to JavaScript) and `SameSite=Strict`.
- The session has a strict TTL (default 30 minutes). Closing the browser or leaving it idle results in an expired session.

## 4. CSRF Protection
All mutating administrative actions (e.g., Restart, Disconnect GitHub) require a valid CSRF token.
- The CSRF token is tied to the current admin session.
- It is validated using constant-time comparison to prevent timing attacks.

## 5. Audit Logging
Every action taken through the panel is appended to `~/.anny-runtime/admin_audit.jsonl`.
- The log records the `admin_session_id`, action type, principal, and result.
- Credentials are **never** logged.

## 6. Zero Credential Exposure
The server uses strict Data Transfer Objects (DTOs) for all browser communication. If a user inspects the HTML source or JSON API responses, they will never find raw GitHub tokens, Fabric keys, or internal authorization material.
