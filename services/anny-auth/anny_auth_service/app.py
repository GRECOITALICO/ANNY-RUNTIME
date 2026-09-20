from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .contracts import AuthorizationState

app = FastAPI(title="ANNY Hosted Authorization Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "anny-auth"}


@app.post("/v1/runtime-authorizations")
def create_runtime_authorization() -> dict[str, str]:
    # Intentionally fail closed until the hosted GitHub App, trust root,
    # transaction store, and runtime signature verification are configured.
    required = (
        "GITHUB_APP_CLIENT_ID",
        "GITHUB_APP_CLIENT_SECRET",
        "ANNY_AUTH_SIGNING_KEY",
        "ANNY_AUTH_ISSUER",
        "ANNY_AUTH_AUDIENCE",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "BLOCKED",
                "error": "AUTH_SERVICE_NOT_CONFIGURED",
                "missing_configuration": missing,
            },
        )
    raise HTTPException(
        status_code=501,
        detail={
            "status": AuthorizationState.FAILED.value,
            "error": "IMPLEMENTATION_PENDING",
        },
    )
