from __future__ import annotations

import argparse
import asyncio
import os
import time

import httpx

from anny_auth_service.app import app


SCENARIOS = {
    "500_10s": (500, 10.0),
    "2000_1m": (2000, 60.0),
    "10000_10m": (10000, 600.0),
    "10000_30m": (10000, 1800.0),
    "10000_60m": (10000, 3600.0),
}


async def one(client: httpx.AsyncClient, index: int) -> tuple[float, int]:
    started = time.perf_counter()
    tx = f"load-{index}-{time.time_ns()}"
    payload = {
        "transaction_id": tx,
        "runtime_id": "load-runtime",
        "installation_id": "load-install",
        "runtime_public_key": "load-public-key",
        "onboarding_session_hash": f"session-{index}",
    }
    created = await client.post("/v1/runtime-authorizations", json=payload)
    if created.status_code != 200:
        return time.perf_counter() - started, created.status_code

    status = await client.get(f"/v1/runtime-authorizations/{tx}/status")
    if status.status_code != 200:
        return time.perf_counter() - started, status.status_code

    redeemed = await client.post(
        f"/v1/runtime-authorizations/{tx}/redeem",
        json={k: payload[k] for k in payload if k != "transaction_id"},
    )
    return time.perf_counter() - started, redeemed.status_code


async def run(count: int, duration: float) -> dict[str, float | int]:
    os.environ["ANNY_AUTH_TEST_MODE"] = "1"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        interval = duration / count
        started = time.perf_counter()
        tasks = []
        for index in range(count):
            target = started + index * interval
            delay = target - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            tasks.append(asyncio.create_task(one(client, index)))
        samples = await asyncio.gather(*tasks)

    latencies = sorted(latency for latency, _ in samples)
    statuses = [status for _, status in samples]
    elapsed = time.perf_counter() - started

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        position = (len(latencies) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(latencies) - 1)
        fraction = position - lower
        return latencies[lower] + (latencies[upper] - latencies[lower]) * fraction

    return {
        "requests": count,
        "elapsed_seconds": elapsed,
        "effective_requests_per_second": count / elapsed if elapsed else 0.0,
        "p50_seconds": pct(0.50),
        "p95_seconds": pct(0.95),
        "p99_seconds": pct(0.99),
        "non_200": sum(1 for code in statuses if code != 200),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="500_10s")
    args = parser.parse_args()
    count, duration = SCENARIOS[args.scenario]
    result = asyncio.run(run(count, duration))
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
