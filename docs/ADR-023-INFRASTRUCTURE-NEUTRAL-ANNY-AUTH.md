# ADR-023 — Infrastructure-Neutral ANNY Hosted Authorization

## Status

Accepted for implementation.

## Context

ANNY requires a customer-zero GitHub connection flow in which the customer performs only:

CONNECT GITHUB -> GitHub login/consent -> automatic return to ANNY.

The customer must not be exposed to hosting, database, vault, OAuth, Device Flow, PKCE, client IDs, client secrets, tokens, or callback configuration.

## Decision

The customer-facing contract is provider-neutral.

ANNY will operate one hosted authorization service that:

1. creates Runtime-bound authorization transactions;
2. starts GitHub authorization;
3. receives the registered HTTPS GitHub callback;
4. validates state and PKCE;
5. creates a short-lived one-time Runtime-bound authorization grant;
6. allows the initiating Runtime to redeem that grant;
7. upgrades the local onboarding session to the normal authenticated Runtime session.

The hosting provider is an internal implementation choice. Railway, Supabase, AWS, Azure, GCP, Cloudflare, or another provider may satisfy the contract if it provides the required capabilities.

## Repository Fabric

Repository Fabric remains the durable system of record for:

- architecture;
- contracts;
- non-secret configuration;
- trust metadata;
- deployment provenance;
- acceptance evidence;
- receipts;
- certification state.

Repository Fabric is not the live callback server and is not a secret vault.

## Local development

A local Runtime may use loopback or test callbacks for development and controlled E2E testing. Local execution does not replace the hosted authorization service for customer-zero production use.

## Security boundary

GitHub App secrets, service signing keys, GitHub tokens, runtime private keys, and other credentials must never be committed to GitHub or exposed to customers.

The service must fail closed whenever required external infrastructure is unavailable or trust configuration is missing.

## Consequence

No customer action depends on the choice of ANNY infrastructure provider.

The remaining P0 dependency is ANNY-owned hosted authorization infrastructure and registered GitHub App configuration, not customer configuration.
