"""Deterministic browser E2E for the local Control Center contract.

This validates the rendered browser surface against an isolated in-process
AdminServer fixture. It is CI E2E, not founder-host/live-CONRRAD evidence.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).parent))

from playwright.sync_api import expect, sync_playwright

from test_control_center_http_surface import _start_server


def test_control_center_browser_e2e():
    with TemporaryDirectory() as raw:
        server, sync, port = _start_server(Path(raw))
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(
                        f"http://127.0.0.1:{port}/",
                        wait_until="domcontentloaded",
                    )

                    expect(page.locator("#anny-sync-panel")).to_be_visible()
                    expect(
                        page.locator('.panel[data-projection-id="control.truth_freshness"]')
                    ).to_be_visible()
                    expect(
                        page.locator(
                            '[data-truth-source="truth_sources.conrrad"]'
                        )
                    ).to_be_visible()

                    expect(page.locator("#anny-sync-state")).to_have_text("IDLE")
                    expect(page.locator("#anny-sync-stage-btn")).to_be_disabled()
                    expect(page.locator("#anny-sync-activate-btn")).to_be_disabled()
                    expect(page.locator("#anny-sync-rollback-btn")).to_be_disabled()

                    registry_meta = page.locator("#projection-registry-meta")
                    expect(registry_meta).to_contain_text("REGISTERED=357")

                    sync_row = page.locator(
                        "#projection-registry-tbody tr"
                    ).filter(
                        has=page.get_by_text("distribution.sync", exact=True)
                    )
                    expect(sync_row).to_have_count(1)
                    sync_row.get_by_role("button", name="VIEW").click()

                    detail = page.locator("#projection-detail-panel")
                    expect(detail).to_be_visible()
                    expect(detail).to_contain_text("distribution.sync")
                    expect(detail).to_contain_text("SYNC")
                finally:
                    browser.close()
        finally:
            sync.wait(timeout=1)
            server.stop()
