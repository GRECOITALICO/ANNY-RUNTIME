from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .contracts import AuthorizationState
from .test_backend import get_test_store

app = FastAPI(title="ANNY Hosted Authorization Service", version="0.1.0")


def _test_mode() -> bool:
    return os.getenv("ANNY_AUTH_TEST_MODE") == "1"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "anny-auth"}


@app.post("/v1/runtime-authorizations")
def create_runtime_authorization(payload: dict[str, str]) -> dict[str, str]:
    if not _test_mode():
        required = (
            "GITHUB_APP_CLIENT_ID",
            "GITHUB_APP_CLIENT_SECRET",
            "ANNY_AUTH_SIGNING_KEY",
            "ANNY_AUTH_ISSUER",
            "ANNY_AUTH_AUDIENCE",
        )
        missing = [name for name in required if not os.getenv(name)]
        raise HTTPException(
            status_code=503,
            detail={
                "status": "BLOCKED",
                "error": "AUTH_SERVICE_NOT_CONFIGURED",
                "missing_configuration": missing,
            },
        )

    required_fields = (
        "transaction_id",
        "runtime_id",
        "installation_id",
        "runtime_public_key",
        "onboarding_session_hash",
    )
    missing = [name for name in required_fields if not payload.get(name)]
    if missing:
        raise HTTPException(status_code=422, detail={"missing_fields": missing})

    try:
        tx = get_test_store().create(
            transaction_id=payload["transaction_id"],
            runtime_id=payload["runtime_id"],
            installation_id=payload["installation_id"],
            runtime_public_key=payload["runtime_public_key"],
            onboarding_session_hash=payload["onboarding_session_hash"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Test-mode authorization stands in for the external GitHub callback.
    get_test_store().authorize(tx.transaction_id)
    return {
        "transaction_id": tx.transaction_id,
        "authorization_url": f"https://test.invalid/authorize/{tx.transaction_id}",
    }


@app.get("/v1/runtime-authorizations/{transaction_id}/status")
def runtime_authorization_status(transaction_id: str) -> dict[str, str]:
    if not _test_mode():
        raise HTTPException(status_code=503, detail="AUTH_SERVICE_NOT_CONFIGURED")
    tx = get_test_store().get(transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="TRANSACTION_NOT_FOUND")
    return {
        "transaction_id": tx.transaction_id,
        "state": tx.state.value,
    }


@app.post("/v1/runtime-authorizations/{transaction_id}/redeem")
def redeem_runtime_authorization(
    transaction_id: str, payload: dict[str, str]
) -> dict[str, str]:
    if not _test_mode():
        raise HTTPException(status_code=503, detail="AUTH_SERVICE_NOT_CONFIGURED")

    try:
        grant = get_test_store().redeem(
            transaction_id=transaction_id,
            runtime_id=payload.get("runtime_id", ""),
            installation_id=payload.get("installation_id", ""),
            runtime_public_key=payload.get("runtime_public_key", ""),
            onboarding_session_hash=payload.get("onboarding_session_hash", ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="TRANSACTION_NOT_FOUND") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "transaction_id": transaction_id,
        "grant": grant,
        "state": AuthorizationState.REDEEMED.value,
    }
