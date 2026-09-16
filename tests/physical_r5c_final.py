"""
001D-R5-C-HARDENING-R2 — Final Physical Validation

Tests the complete security matrix:
1.  Background POST blocked (no auth)
2.  Programmatic form.submit() blocked
3.  Programmatic form.requestSubmit() blocked
4.  issue_auth issues a valid auth_id
5.  Pending auth does NOT unblock unrelated POST
6.  Authorized submit succeeds (single allowed POST)
7.  Auth is single-use (reuse denied)
8.  302 redirect: original POST allowed, subsequent GET safe, no second POST
9.  307 redirect: original POST allowed, follow-on POST blocked
10. Cross-frame mismatch: forged frame_id blocked
11. Reload invalidates target
12. Navigation invalidates target
13. Session restart invalidates auth
14. Expired auth rejected
15. Textarea newline typing accepted
"""
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, ".")
from runtime.browser.broker_server import BrowserBroker
from runtime.browser.authorization import PendingSubmissionAuthorization

# ---------------------------------------------------------------------------
# Test server
# ---------------------------------------------------------------------------

FORM_HTML_MAIN = b"""<!DOCTYPE html>
<html>
<head><title>Main Frame</title></head>
<body>
  <!-- All forms navigate in the main frame (no target attr) -->
  <form id="test-form" action="/submit-target" method="post">
    <input type="text" id="test-name" />
    <textarea id="test-textarea"></textarea>
    <button type="submit" id="test-submit">Submit Main</button>
  </form>
  <form id="redirect-302-form" action="/redirect-302" method="post">
    <button type="submit" id="btn-302">Submit 302</button>
  </form>
  <form id="redirect-307-form" action="/redirect-307" method="post">
    <button type="submit" id="btn-307">Submit 307</button>
  </form>
  <script>
    window.fireBackgroundPost = function(url) {
      fetch(url, {method: 'POST', body: 'data=1'}).catch(e => console.error(e));
    };
  </script>
</body>
</html>
"""

_posts = {
    "/submit-target": 0,
    "/analytics": 0,
    "/redirect-302": 0,
    "/redirect-307": 0
}
_gets = {
    "/submit-target": 0
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _gets
        if self.path in _gets:
            _gets[self.path] += 1
        body = FORM_HTML_MAIN
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global _posts
        if self.path in _posts:
            _posts[self.path] += 1

        if self.path == "/redirect-302":
            self.send_response(302)
            self.send_header("Location", "/submit-target")
            self.end_headers()
            return

        if self.path == "/redirect-307":
            self.send_response(307)
            self.send_header("Location", "/submit-target")
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"POST OK")

    def log_message(self, *args):
        pass


def _start_server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_step(msg):
    print(f"\n=== {msg} ===")

def print_pass(msg):
    print(f"[PASS] {msg}")

def print_fail(msg):
    print(f"[FAIL] {msg}", file=sys.stderr)

def done_ok():
    print("\n=== FINAL R5-C VALIDATION PASSED ===")
    sys.exit(0)

def get_btn(broker, text):
    for t in broker.find({"tag": "button"}).get("targets", []):
        combined = (t.get("name", "") + t.get("text", "")).lower()
        if text.lower() in combined:
            return t["target_id"]
    return None

def trigger_background_post(broker, url):
    expression = f"window.fireBackgroundPost('{url}');"
    broker._cdp_request("Runtime.evaluate", {"expression": expression})
    time.sleep(0.5)

def navigate_and_wait(broker, url, wait=2.0):
    """Navigate and wait for page to fully load."""
    broker.navigate(url)
    time.sleep(wait)


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def main():
    global _posts, _gets
    print("\n=== Starting physical validation: 001D-R5-C-HARDENING-R2 FINAL ===")

    srv, port = _start_server()
    base_url = f"http://127.0.0.1:{port}"
    print(f"  Test server: {base_url}")

    broker = BrowserBroker()
    broker.start_browser(base_url)
    navigate_and_wait(broker, base_url)

    # ------------------------------------------------------------------
    # STEP 1: Unauthorized background POST → blocked
    # ------------------------------------------------------------------
    print_step("1. Unauthorized /analytics POST → 0")
    trigger_background_post(broker, f"{base_url}/analytics")
    assert _posts["/analytics"] == 0, f"Expected 0, got {_posts['/analytics']}"
    print_pass("Blocked")

    # ------------------------------------------------------------------
    # STEP 2: Unauthorized programmatic form.submit() → blocked
    # ------------------------------------------------------------------
    print_step("2. Unauthorized form.submit() → 0")
    broker._cdp_request("Runtime.evaluate", {
        "expression": "document.getElementById('test-form').submit();"
    })
    time.sleep(0.8)
    assert _posts["/submit-target"] == 0
    print_pass("Blocked")

    # Fetch failure may cause the browser to end up in an error state;
    # navigate back to get clean DOM for next steps.
    navigate_and_wait(broker, base_url)

    # ------------------------------------------------------------------
    # STEP 3: Unauthorized programmatic form.requestSubmit() → blocked
    # ------------------------------------------------------------------
    print_step("3. Unauthorized form.requestSubmit() → 0")
    broker._cdp_request("Runtime.evaluate", {
        "expression": "document.getElementById('test-form').requestSubmit();"
    })
    time.sleep(0.8)
    assert _posts["/submit-target"] == 0
    print_pass("Blocked")

    # Again recover clean DOM.
    navigate_and_wait(broker, base_url)

    # ------------------------------------------------------------------
    # STEP 4: issue_auth returns valid auth_id
    # ------------------------------------------------------------------
    print_step("4. issue_auth Form A → auth_id")
    main_btn = get_btn(broker, "Submit Main")
    assert main_btn, "Submit Main button not found"
    auth_res = broker.issue_auth(main_btn, broker._session_id, 300)
    assert auth_res.get("status") == "ok", f"Auth failed: {auth_res}"
    auth_id = auth_res["auth_id"]
    print_pass(f"Issued auth_id: {auth_id}")

    # ------------------------------------------------------------------
    # STEP 5: Unrelated POST while auth pending → blocked, auth preserved
    # ------------------------------------------------------------------
    print_step("5. Unrelated POST while auth pending → 0, auth preserved")
    trigger_background_post(broker, f"{base_url}/analytics")
    assert _posts["/analytics"] == 0
    assert auth_id in broker.issued_authorizations, "Auth was consumed by unrelated POST"
    print_pass("Blocked without consuming auth")

    # ------------------------------------------------------------------
    # STEP 6: Authorized submit → 1 POST reaches server
    # ------------------------------------------------------------------
    print_step("6. Authorized submit /submit-target → 1")
    sub_res = broker.submit(main_btn, auth_id)
    assert sub_res.get("status") == "ok", f"Submit failed: {sub_res}"
    time.sleep(1.0)
    # After a main-frame POST the page navigates (server returns 200 with HTML again)
    assert _posts["/submit-target"] == 1, f"Expected 1, got {_posts['/submit-target']}"
    print_pass("Allowed — server received POST")

    # ------------------------------------------------------------------
    # STEP 7: Auth reuse → INVALID_AUTHORIZATION
    # ------------------------------------------------------------------
    print_step("7. Auth reuse → INVALID_AUTHORIZATION")
    sub_res2 = broker.submit(main_btn, auth_id)
    assert sub_res2.get("status") == "error", f"Expected error, got: {sub_res2}"
    assert "INVALID_AUTHORIZATION" in sub_res2.get("message", ""), sub_res2
    print_pass("Reuse denied")

    # ------------------------------------------------------------------
    # STEP 8: 302 redirect — POST to /redirect-302, then safe GET
    # ------------------------------------------------------------------
    print_step("8. 302 redirect → POST to /redirect-302, follow-on GET safe")
    navigate_and_wait(broker, base_url)
    btn_302 = get_btn(broker, "Submit 302")
    assert btn_302, "btn-302 not found"
    auth_res_302 = broker.issue_auth(btn_302, broker._session_id, 300)
    assert auth_res_302.get("status") == "ok", f"Auth 302 failed: {auth_res_302}"
    sub_302 = broker.submit(btn_302, auth_res_302["auth_id"])
    assert sub_302.get("status") == "ok", f"Submit 302 failed: {sub_302}"
    time.sleep(1.0)
    assert _posts["/redirect-302"] == 1, f"Expected 1, got {_posts['/redirect-302']}"
    # The browser follows 302 with a GET — that's fine; /submit-target POST count unchanged
    assert _posts["/submit-target"] == 1, f"302 should not POST to /submit-target, got {_posts['/submit-target']}"
    print_pass("302 POST allowed, follow-on GET safe")

    # ------------------------------------------------------------------
    # STEP 9: 307 redirect — first POST allowed, follow-on POST blocked
    # ------------------------------------------------------------------
    print_step("9. 307 redirect → POST to /redirect-307, follow-on POST blocked")
    navigate_and_wait(broker, base_url)
    btn_307 = get_btn(broker, "Submit 307")
    assert btn_307, "btn-307 not found"
    auth_res_307 = broker.issue_auth(btn_307, broker._session_id, 300)
    assert auth_res_307.get("status") == "ok", f"Auth 307 failed: {auth_res_307}"
    sub_307 = broker.submit(btn_307, auth_res_307["auth_id"])
    assert sub_307.get("status") == "ok", f"Submit 307 failed: {sub_307}"
    time.sleep(1.0)
    assert _posts["/redirect-307"] == 1, f"Expected 1, got {_posts['/redirect-307']}"
    # The 307 tells the browser to re-POST to /submit-target — that must be blocked
    assert _posts["/submit-target"] == 1, f"307 follow-on POST must be blocked, got {_posts['/submit-target']}"
    print_pass("307 POST allowed, follow-on POST to /submit-target blocked")

    # ------------------------------------------------------------------
    # STEP 10: Cross-frame mismatch → blocked (via forged pending record)
    # ------------------------------------------------------------------
    print_step("10. Cross-frame mismatch → blocked")
    navigate_and_wait(broker, base_url)
    main_btn = get_btn(broker, "Submit Main")
    auth_res_m = broker.issue_auth(main_btn, broker._session_id, 300)
    assert auth_res_m.get("status") == "ok"
    
    auth = broker.issued_authorizations[auth_res_m["auth_id"]]
    # Forge: replace correct frame_id with a bogus one in the _pending_submission slot
    broker._pending_submission = PendingSubmissionAuthorization(
        auth_id=auth_res_m["auth_id"],
        session_id=auth["session_id"],
        target_id=auth["target_id"],
        expected_method=auth["expected_method"],
        expected_url=auth["expected_url"],
        expected_frame_id="BOGUS_FRAME_XYZ",  # wrong frame
        issued_at=auth["issued_at"],
        expires_at=auth["expires_at"]
    )
    # Fire a background POST that matches method+URL but wrong frame
    trigger_background_post(broker, f"{base_url}/submit-target")
    time.sleep(0.5)
    assert _posts["/submit-target"] == 1, f"Cross-frame POST must be blocked, got {_posts['/submit-target']}"
    # Clean up
    broker._pending_submission = None
    broker.issued_authorizations.pop(auth_res_m["auth_id"], None)
    print_pass("Cross-frame mismatch blocked")

    # ------------------------------------------------------------------
    # STEP 11: Reload invalidates target stale
    # ------------------------------------------------------------------
    print_step("11. Reload invalidates target → TARGET_STALE")
    navigate_and_wait(broker, base_url)
    main_btn = get_btn(broker, "Submit Main")
    auth_res = broker.issue_auth(main_btn, broker._session_id, 300)
    assert auth_res.get("status") == "ok"
    broker._cdp_request("Page.reload")
    time.sleep(1.5)
    # The old target_id is now stale (backendNodeId no longer valid)
    sub_stale = broker.submit(main_btn, auth_res["auth_id"])
    assert sub_stale.get("status") == "error", f"Expected error, got: {sub_stale}"
    assert "STALE" in sub_stale.get("message", "") or "INVALID" in sub_stale.get("message", ""), sub_stale
    print_pass(f"Reload invalidated target: {sub_stale['message']}")

    # ------------------------------------------------------------------
    # STEP 12: Navigation invalidates target
    # ------------------------------------------------------------------
    print_step("12. Navigation invalidates target → TARGET_STALE")
    navigate_and_wait(broker, base_url)
    main_btn = get_btn(broker, "Submit Main")
    auth_res = broker.issue_auth(main_btn, broker._session_id, 300)
    assert auth_res.get("status") == "ok"
    navigate_and_wait(broker, base_url)  # navigates away, old target stale
    sub_stale = broker.submit(main_btn, auth_res["auth_id"])
    assert sub_stale.get("status") == "error", f"Expected error, got: {sub_stale}"
    assert "STALE" in sub_stale.get("message", "") or "INVALID" in sub_stale.get("message", ""), sub_stale
    print_pass(f"Navigation invalidated target: {sub_stale['message']}")

    # ------------------------------------------------------------------
    # STEP 13: Session restart invalidates auth
    # ------------------------------------------------------------------
    print_step("13. Session restart invalidates auth → INVALID_AUTHORIZATION")
    navigate_and_wait(broker, base_url)
    main_btn = get_btn(broker, "Submit Main")
    auth_res = broker.issue_auth(main_btn, broker._session_id, 300)
    saved_auth_id = auth_res["auth_id"]
    assert auth_res.get("status") == "ok"

    broker.stop_browser()
    broker.start_browser(base_url)
    navigate_and_wait(broker, base_url)
    main_btn_new = get_btn(broker, "Submit Main")

    # Old auth_id belongs to old session — new broker.issued_authorizations is empty
    sub_restart = broker.submit(main_btn_new, saved_auth_id)
    assert sub_restart.get("status") == "error", f"Expected error, got: {sub_restart}"
    assert "INVALID_AUTHORIZATION" in sub_restart.get("message", ""), sub_restart
    print_pass("Session restart invalidated auth")

    # ------------------------------------------------------------------
    # STEP 14: Expired auth → AUTHORIZATION_EXPIRED
    # ------------------------------------------------------------------
    print_step("14. Expired auth → AUTHORIZATION_EXPIRED")
    navigate_and_wait(broker, base_url)
    main_btn = get_btn(broker, "Submit Main")
    auth_res = broker.issue_auth(main_btn, broker._session_id, 1)  # 1 second
    assert auth_res.get("status") == "ok"
    time.sleep(1.1)
    sub_exp = broker.submit(main_btn, auth_res["auth_id"])
    assert sub_exp.get("status") == "error", f"Expected error, got: {sub_exp}"
    assert "AUTHORIZATION_EXPIRED" in sub_exp.get("message", ""), sub_exp
    print_pass("Expired auth rejected")

    # ------------------------------------------------------------------
    # STEP 15: Textarea newline typing accepted
    # ------------------------------------------------------------------
    print_step("15. Textarea newline typing → ok")
    navigate_and_wait(broker, base_url)
    ta_list = broker.find({"tag": "textarea"}).get("targets", [])
    assert ta_list, "No textarea found"
    ta_id = ta_list[0]["target_id"]
    res = broker.type(ta_id, "line1\nline2")
    assert res.get("status") == "ok", f"Type failed: {res}"
    print_pass("Textarea type with newline accepted")

    broker.stop_browser()
    srv.shutdown()
    done_ok()


if __name__ == "__main__":
    main()
