# ANNY Hosted Authorization Service

This package is the implementation boundary for ADR-022.

Customer journey:

CONNECT GITHUB -> GitHub login/consent -> ANNY HTTPS callback -> one-time Runtime-bound grant -> Runtime redemption -> ADMIN session.

This service must never require the ANNY customer to configure OAuth/client identifiers, paste tokens, or enter device codes.

This source tree contains no secrets. Production deployment requires external hosting, a registered GitHub App, a vault-backed client secret/signing key, HTTPS callback, and durable transaction storage.
