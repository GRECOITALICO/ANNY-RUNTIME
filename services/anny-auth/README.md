# ANNY Hosted Authorization Service

## Boundary

This service is the only public authentication component between a customer-facing ANNY Runtime and GitHub.

Customer experience:

CONNECT GITHUB -> GitHub login/consent -> automatic return to ANNY -> authenticated Runtime -> Control Center.

The customer does **not** provision, configure, install, or operate:

- Railway
- Supabase
- a database
- a secret vault
- OAuth client identifiers
- client secrets
- PKCE
- device codes
- tokens
- callback URLs

Those are platform-internal implementation details.

## Infrastructure-neutral contract

The service must run on any ANNY-approved hosting stack that provides:

1. public HTTPS;
2. server-side secret storage;
3. durable transaction storage;
4. runtime execution for the authorization API and GitHub callback;
5. TLS/certificate management;
6. controlled logging and retention;
7. outbound HTTPS to GitHub.

Railway, Supabase, AWS, Azure, GCP, Cloudflare, or another provider are implementation choices. No provider is part of the customer contract.

## Repository Fabric boundary

Repository Fabric is the durable source of truth for:

- architecture and ADRs;
- non-secret configuration;
- service contract;
- trust metadata and fingerprints;
- deployment/version provenance;
- acceptance criteria;
- security evidence;
- audit receipts;
- operational state and certification.

Repository Fabric is **not** the live OAuth callback server and is **not** a secret vault.

## Secret boundary

The following must never be committed to GitHub or sent to the customer:

- GitHub App client secret;
- service private signing key;
- runtime private keys;
- GitHub access/refresh tokens;
- raw onboarding/session or CSRF values.

Secrets remain in the hosting platform's vault/secret manager or an equivalent dedicated service.

## Current status

This repository branch contains an implementation scaffold only. The live authorization service remains blocked until the ANNY-owned GitHub App, public HTTPS callback, secret vault/trust root, and durable transaction store exist.

Fail closed rather than simulating any of those dependencies.
