# ADR-022: Customer-Zero GitHub Authorization

- Status: **ACCEPTED DESIGN — NOT YET DEPLOYED**
- Date: 2026-09-20
- Decision owner: ANNY Runtime

## Decision

Customer-zero onboarding will use a **hosted ANNY authorization service backed
by a GitHub App**, its HTTPS callback, and a Runtime-bound, single-use
authorization grant.  The installed Runtime will never ask a customer to
configure an OAuth application, client ID, client secret, token, scope, or
device code.

This is the only option considered that meets the required product journey and
keeps GitHub App credentials out of the local installation.  It is a target
architecture, not a claim that the currently local-only Runtime implements it.
Until the hosted service and its trust configuration are delivered, onboarding
must fail closed; it must not fall back to Device Flow or token entry.

## Options reviewed

| Option | Customer-zero journey | Secret exposure | Decision |
| --- | --- | --- | --- |
| A. Local Device Flow | No: requires user code and a local client ID | No local secret, but requires technical setup and is inappropriate for a browser-capable Runtime | Rejected for customer onboarding; may remain an internal engineering recovery tool only. |
| B. Direct web authorization with PKCE from the Runtime | The browser redirect can be simple, but the Runtime is a public client and cannot protect a GitHub App client secret | Unsafe for the required trust boundary; GitHub's GitHub App code exchange requires `client_secret` | Rejected. |
| C. GitHub App user authorization with an ANNY-hosted callback | Yes: click, GitHub login/consent, automatic return | Client secret remains only in the ANNY backend secret vault | **Selected.** |

GitHub documents Device Flow for headless clients and explicitly requires a
user verification code. GitHub also documents that its GitHub App web code
exchange requires the client secret, while recommending the authorization-code
flow and PKCE over Device Flow when a redirect-capable experience is available.
The hosted confidential backend is therefore an architectural requirement, not
an environment variable that may be delegated to a customer.

Primary references:

- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
- https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app

## Required product journey

```text
fresh Runtime
  -> CONNECT GITHUB
  -> GitHub login and consent
  -> ANNY hosted callback validates authorization
  -> browser returns to the initiating Runtime
  -> Runtime redeems a bound one-time grant
  -> normal ADMIN session
  -> Control Center
```

The customer sees only the action and GitHub's own login/consent pages. No
authorization implementation term, token value, scope selector, or code is a
customer-facing control.

## Trust and protocol contract

### Runtime begins a transaction

`POST /v1/runtime-authorizations` at the ANNY authorization service accepts:

- a newly generated `transaction_id` and 128-bit-or-greater random nonce;
- Runtime ID, installation ID, and Ed25519 public key;
- an expiry of at most ten minutes;
- a signature by the Runtime private key over the canonical request;
- a hash of the ephemeral local onboarding-session ID and a hash of the local
  session CSRF token, never either raw value; and
- the fixed local return origin for the Runtime that initiated the request.

The service verifies the signature, records a one-time transaction, and returns
only an authorization URL. The Runtime redirects the browser to that URL. The
authorization URL carries an opaque service-generated state; it never carries a
GitHub access token, refresh token, client secret, Runtime private key, local
session ID, or CSRF token.

### Hosted callback

The ANNY service owns the registered HTTPS callback URL. It creates a fresh
GitHub `state` per transaction, stores it server-side, and requires an exact
match on callback. It exchanges the GitHub authorization code only at the
hosted backend using its vault-held GitHub App client secret, with PKCE (`S256`)
and the original verifier. It then validates the GitHub identity and the
minimum GitHub App permissions before marking the transaction authorized.

The service issues a short-lived, single-use **authorization grant** encrypted
to the initiating Runtime public key. The grant is bound to all of:

- transaction ID and nonce;
- Runtime ID and installation ID;
- Runtime public-key fingerprint;
- local onboarding-session binding hash; and
- expiry and one-use redemption state.

It is not a GitHub token and it cannot be redeemed by another Runtime or after
its first redemption. The browser may be redirected to the fixed loopback
return URL with an opaque transaction reference only; no credential or grant is
placed in a visible URL. The Runtime obtains and redeems the grant through its
authenticated service channel, verifies the service signature, and decrypts it
locally.

### Runtime completes onboarding

The Runtime accepts completion only when all transaction, signature, expiry,
installation, local-session binding, and one-use checks pass. It persists only
the resulting GitHub credential through `SecretBackend`, validates the GitHub
principal and required permissions, then revokes the `ONBOARDING_ONLY` session
and creates a new `ADMIN` session. Any error, mismatch, expiration, replay, or
authorization denial leaves the Runtime in `ONBOARDING_ONLY`.

Neither the hosted authorization service nor this protocol grants Runtime
activation, production status, or authority expansion. GitHub authorization is
readiness evidence only.

## Delivery boundary

The current repository contains no deployable ANNY authorization service,
registered GitHub App, service trust root, HTTPS callback hostname, or backend
secret vault. Those are mandatory external deliverables. It would be insecure
to simulate them by embedding a client ID, accepting an arbitrary endpoint, or
shipping a client secret in this repository.

Required implementation deliverables before this ADR can become operational:

1. An ANNY-owned hosted authorization service with its GitHub App registration,
   HTTPS callback, vault-held client secret, signing key, retention policy, and
   monitored audit trail.
2. A signed Runtime trust configuration that pins the service issuer and
   audience; it must not be customer-provided through an environment variable.
3. Runtime transaction, polling/redeem, signature verification, replay
   protection, and session-upgrade implementation.
4. Removal of Device Flow and token-entry controls from customer onboarding.
5. Integration tests against a non-production ANNY authorization service and a
   real GitHub App test tenant, followed by the browser E2E described below.

## Security acceptance tests

The implementation is not acceptable without tests for:

- rejected missing, mismatched, expired, or reused GitHub `state`;
- rejected transaction where the Runtime signature, runtime ID, installation
  ID, key fingerprint, or local-session binding differs;
- rejected replay of a completion or authorization grant;
- callback and redemption that never expose tokens or secrets in URLs, HTML,
  browser storage, logs, receipts, or telemetry;
- continued `ONBOARDING_ONLY` access when authorization is pending, denied, or
  invalid, including rejection of unrelated administrative routes;
- successful authorization that revokes the old session and creates a distinct
  `ADMIN` session; and
- a real fresh-install browser E2E: `CONNECT GITHUB` -> GitHub login/consent ->
  automatic return -> Control Center -> physical `SYNC NOW` click -> observed
  `POST /api/sync`, `GET /api/sync/status`, and automatic polling.

The Sync E2E remains unqualified until that final real-browser flow is observed
and its receipt is durable and remotely verifiable.
