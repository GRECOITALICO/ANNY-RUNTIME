"""Regression tests — SYNC control DOM identity.

Prevents re-introduction of the anny-sync-btn ID collision (GUI-P0-SYNC-ID-COLLISION-001).

Each test exercises a specific requirement from the fix specification:
  1. No duplicate IDs for SYNC controls.
  2. Header control exists.
  3. Panel control exists.
  4. Both controls call annySyncNow().
  5. Both controls are disabled during busy state (render path).
  6. Both controls recover enabled state after polling.
  7. STAGE remains disabled.
  8. ACTIVATE remains disabled.
  9. ROLLBACK remains disabled.
  10. CSRF field is present in JS.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from runtime.admin.sync_ui import inject_sync_controls


_MINIMAL_PAGE = """\
<!doctype html>
<html>
<head><title>CC</title></head>
<body>
<header><div>Nav</div>
</header>
<main>
<p>body</p>
</main>
</body>
</html>
"""


def _rendered(csrf: str = "test-csrf") -> str:
    return inject_sync_controls(_MINIMAL_PAGE, csrf)


# ── 1. No duplicate IDs ──────────────────────────────────────────────────────

def test_no_duplicate_sync_button_ids():
    html = _rendered()
    ids = re.findall(r'id="([^"]*sync[^"]*)"', html)
    duplicates = [i for i in set(ids) if ids.count(i) > 1]
    assert duplicates == [], f"Duplicate SYNC-related IDs found: {duplicates}"


def test_legacy_shared_id_absent():
    """The old colliding id anny-sync-btn must not appear at all."""
    html = _rendered()
    assert 'id="anny-sync-btn"' not in html, (
        "Legacy colliding ID 'anny-sync-btn' was re-introduced"
    )


# ── 2. Header control exists ─────────────────────────────────────────────────

def test_header_sync_button_present():
    html = _rendered()
    assert 'id="anny-sync-header-btn"' in html


# ── 3. Panel control exists ──────────────────────────────────────────────────

def test_panel_sync_button_present():
    html = _rendered()
    assert 'id="anny-sync-panel-btn"' in html


# ── 4. Both controls call annySyncNow() ──────────────────────────────────────

def test_header_button_calls_annysynocnow():
    html = _rendered()
    # Locate the header-btn element and check its onclick attribute
    match = re.search(r'id="anny-sync-header-btn"[^>]*>', html)
    assert match, "anny-sync-header-btn element not found"
    assert "annySyncNow()" in match.group(), (
        "anny-sync-header-btn does not call annySyncNow()"
    )


def test_panel_button_calls_annySyncNow():
    html = _rendered()
    match = re.search(r'id="anny-sync-panel-btn"[^>]*>', html)
    assert match, "anny-sync-panel-btn element not found"
    assert "annySyncNow()" in match.group(), (
        "anny-sync-panel-btn does not call annySyncNow()"
    )


# ── 5. Both controls are disabled in busy state (render path in JS) ──────────

def test_render_disables_both_buttons_on_busy_state():
    html = _rendered()
    # JS render() must reference both IDs when setting disabled
    assert "'anny-sync-header-btn'" in html
    assert "'anny-sync-panel-btn'" in html
    # Verify they're inside the forEach / array pattern (not isolated getElementById)
    # The pattern must NOT rely on a single getElementById('anny-sync-btn')
    assert "getElementById('anny-sync-btn')" not in html, (
        "JS still references legacy colliding ID 'anny-sync-btn'"
    )
    # Both IDs must appear together in the same forEach call
    header_pos = html.find("'anny-sync-header-btn'")
    panel_pos = html.find("'anny-sync-panel-btn'")
    assert abs(header_pos - panel_pos) < 300, (
        "Header and panel IDs are not co-located in the same forEach/array expression"
    )


# ── 6. Both controls recover after polling (annySyncNow path) ────────────────

def test_annySyncNow_disables_both_then_polls():
    html = _rendered()
    # annySyncNow must also iterate both IDs when initially disabling
    # and must call annySyncPoll() to re-enable via render()
    assert "annySyncPoll" in html
    # Verify the .finally(()=>setTimeout(annySyncPoll,...)) recovery path
    assert "setTimeout(annySyncPoll" in html


# ── 7. STAGE remains disabled ────────────────────────────────────────────────

def test_stage_button_is_disabled_in_html():
    html = _rendered()
    match = re.search(r'id="anny-sync-stage-btn"[^>]*>', html)
    assert match, "anny-sync-stage-btn not found"
    assert "disabled" in match.group(), "STAGE button is not disabled in HTML"


def test_stage_button_stays_disabled_in_js():
    html = _rendered()
    # JS must force stageBtn.disabled = true unconditionally
    assert "stageBtn.disabled = true" in html or "stageBtn) stageBtn.disabled = true" in html


# ── 8. ACTIVATE remains disabled ─────────────────────────────────────────────

def test_activate_button_is_disabled_in_html():
    html = _rendered()
    match = re.search(r'id="anny-sync-activate-btn"[^>]*>', html)
    assert match, "anny-sync-activate-btn not found"
    assert "disabled" in match.group(), "ACTIVATE button is not disabled in HTML"


def test_activate_button_stays_disabled_in_js():
    html = _rendered()
    assert "activateBtn.disabled = true" in html or "activateBtn) activateBtn.disabled = true" in html


# ── 9. ROLLBACK remains disabled ─────────────────────────────────────────────

def test_rollback_button_is_disabled_in_html():
    html = _rendered()
    match = re.search(r'id="anny-sync-rollback-btn"[^>]*>', html)
    assert match, "anny-sync-rollback-btn not found"
    assert "disabled" in match.group(), "ROLLBACK button is not disabled in HTML"


def test_rollback_button_stays_disabled_in_js():
    html = _rendered()
    assert "rollbackBtn.disabled = true" in html or "rollbackBtn) rollbackBtn.disabled = true" in html


# ── 10. CSRF token is embedded ───────────────────────────────────────────────

def test_csrf_token_is_embedded_in_js():
    csrf = "my-secret-csrf-token"
    html = inject_sync_controls(_MINIMAL_PAGE, csrf)
    assert csrf in html, "CSRF token not embedded in rendered page"


def test_csrf_token_is_used_in_sync_post():
    html = _rendered()
    assert "ANNY_SYNC_CSRF" in html
    assert "body.set('csrf_token',ANNY_SYNC_CSRF)" in html


# ── Additional: injection idempotence ────────────────────────────────────────

def test_inject_is_idempotent_for_panel():
    """Re-injecting must not add a second panel."""
    once = inject_sync_controls(_MINIMAL_PAGE, "tok")
    twice = inject_sync_controls(once, "tok")
    assert twice.count('id="anny-sync-panel"') == 1


def test_inject_is_idempotent_for_header_button():
    """Re-injecting must not add a second header button."""
    once = inject_sync_controls(_MINIMAL_PAGE, "tok")
    twice = inject_sync_controls(once, "tok")
    assert twice.count('id="anny-sync-header-btn"') == 1


def test_inject_is_idempotent_for_css():
    once = inject_sync_controls(_MINIMAL_PAGE, "tok")
    twice = inject_sync_controls(once, "tok")
    assert twice.count('id="anny-sync-ui-css"') == 1


def test_inject_is_idempotent_for_js():
    once = inject_sync_controls(_MINIMAL_PAGE, "tok")
    twice = inject_sync_controls(once, "tok")
    assert twice.count('id="anny-sync-ui-js"') == 1
