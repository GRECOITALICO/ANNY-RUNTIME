from __future__ import annotations

import os
import unittest

import httpx

from anny_auth_service.app import app


class AuthContractFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        os.environ["ANNY_AUTH_TEST_MODE"] = "1"
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        os.environ.pop("ANNY_AUTH_TEST_MODE", None)

    async def test_authorize_status_redeem(self) -> None:
        payload = {
            "transaction_id": "test-flow-001",
            "runtime_id": "runtime-001",
            "installation_id": "install-001",
            "runtime_public_key": "public-key-001",
            "onboarding_session_hash": "session-hash-001",
        }
        created = await self.client.post(
            "/v1/runtime-authorizations", json=payload
        )
        self.assertEqual(created.status_code, 200)
        self.assertIn("authorization_url", created.json())

        status = await self.client.get(
            "/v1/runtime-authorizations/test-flow-001/status"
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "AUTHORIZED")

        redeem_payload = {
            key: payload[key] for key in payload if key != "transaction_id"
        }
        redeemed = await self.client.post(
            "/v1/runtime-authorizations/test-flow-001/redeem",
            json=redeem_payload,
        )
        self.assertEqual(redeemed.status_code, 200)
        self.assertEqual(redeemed.json()["state"], "REDEEMED")

        replay = await self.client.post(
            "/v1/runtime-authorizations/test-flow-001/redeem",
            json=redeem_payload,
        )
        self.assertEqual(replay.status_code, 409)

    async def test_production_mode_fails_closed(self) -> None:
        os.environ.pop("ANNY_AUTH_TEST_MODE", None)
        response = await self.client.post(
            "/v1/runtime-authorizations",
            json={"transaction_id": "blocked"},
        )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
