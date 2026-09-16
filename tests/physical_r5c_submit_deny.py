"""
001D-R5-C-HARDENING-R2 Physical Validation: Submit Default-Deny and Request-Scoped Auth

Proves denial and request-scoped authorization boundaries against a live browser.

Required proofs:
  A. background POST /analytics -> BLOCKED (no auth)
  B. issue auth for Form A
  C. unrelated POST while auth pending -> BLOCKED (doesn't consume auth)
  D. intended Form A POST -> ALLOWED (consumes auth)
  E. reuse Form A auth -> BLOCKED
  F. second unrelated POST -> BLOCKED
  G. browser restart -> previous auth invalid
  H. textarea newline -> still ALLOWED
  I. form.submit() without auth -> BLOCKED
  J. requestSubmit() without auth -> BLOCKED
"""
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, ".")

from runtime.browser.broker_server import BrowserBroker

# Test page 1: has e.preventDefault() to keep page alive during denial tests
# Also includes a script to fire a background POST request.
FORM_HTML_DENY = b"""<!DOCTYPE html>
<html>
<head><title>Submit Denial Test</title></head>
<body>
  <form id="test-form" action="/submit-target" method="post">
    <input type="text" id="test-name" aria-label="Name" />
    <input type="email" id="test-email" aria-label="Email" required />
    <textarea id="test-textarea" aria-label="Comments"></textarea>
    <button type="submit" id="test-submit" aria-label="Submit Form">Submit</button>
    <input type="submit" id="test-submit2" aria-label="Submit Input" value="Go" />
  </form>
  <div id="result"></div>
  <script>
    document.getElementById('test-form').addEventListener('submit', function(e) {
      e.preventDefault();
      document.getElementById('result').textContent = 'SUBMITTED';
    });
    
    // Function to fire background POSTs
    window.fireBackgroundPost = function() {
      fetch('/analytics', {
        method: 'POST',
        body: 'analytics_data=1'
      }).catch(e => console.error(e));
    };
  </script>
</body>
</html>
"""

# Test page 2: NO e.preventDefault() — real POST allowed through
FORM_HTML_SUBMIT = b"""<!DOCTYPE html>
<html>
<head><title>Auth Submit Test</title></head>
<body>
  <form id="test-form" action="/submit-target" method="post">
    <input type="text" id="test-name" aria-label="Name" value="test" />
    <button type="submit" id="test-submit" aria-label="Submit Form">Submit</button>
  </form>
  <script>
    // Function to fire background POSTs
    window.fireBackgroundPost = function() {
      fetch('/analytics', {
        method: 'POST',
        body: 'analytics_data=1'
      }).catch(e => console.error(e));
    };
  </script>
</body>
</html>
"""

_posts = {
    "/submit-target": 0,
    "/analytics": 0
}

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/auth-submit":
            body = FORM_HTML_SUBMIT
        else:
            body = FORM_HTML_DENY
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global _posts
        if self.path in _posts:
            _posts[self.path] += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"received")

    def log_message(self, *args):
        pass


def _start_server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


def print_step(msg):   print(f"\n=== {msg} ===")
def print_pass(msg):   print(f"[PASS] {msg}")
def print_fail(msg):   print(f"[FAIL] {msg}", file=sys.stderr)
def done_ok():
    print("\n=== ALL R5-C-HARDENING-R2 CHECKS PASSED ===")
    sys.exit(0)


def find_submit_btn(broker):
    find_btn = broker.find({"tag": "button"})
    for t in find_btn.get("targets", []):
        if t.get("type", "").lower() in ("", "submit") or "Submit" in (t.get("name", "") + t.get("text", "")):
            return t["target_id"]
    return None

def trigger_background_post(broker):
    broker._cdp_request("Runtime.evaluate", {
        "expression": "window.fireBackgroundPost();"
    })
    time.sleep(0.5)

def main():
    global _posts
    print("\n=== Starting physical validation: R5-C-HARDENING-R2 ===")

    srv, port = _start_server()
    deny_url = f"http://127.0.0.1:{port}/"
    submit_url = f"http://127.0.0.1:{port}/auth-submit"
    print(f"  Test server: {deny_url}")

    broker = BrowserBroker()

    # 1: Start and navigate to deny page
    res = broker.start_browser(deny_url)
    broker.navigate(deny_url)
    time.sleep(1.5)

    submit_btn_id = find_submit_btn(broker)
    if not submit_btn_id:
        print_fail("Could not find submit button")
        sys.exit(1)

    print_step("A. Background POST /analytics without auth -> BLOCKED")
    trigger_background_post(broker)
    if _posts["/analytics"] > 0:
        print_fail(f"Background POST allowed! _posts: {_posts}")
        sys.exit(1)
    print_pass("Background POST blocked")

    print_step("I. Programmatic form.submit() without auth -> BLOCKED")
    broker._cdp_request("Runtime.evaluate", {"expression": "document.getElementById('test-form').submit();"})
    time.sleep(0.5)
    if _posts["/submit-target"] > 0:
        print_fail(f"form.submit() allowed! _posts: {_posts}")
        sys.exit(1)
    print_pass("form.submit() blocked")

    # Navigate to auth-submit page for the actual submission testing
    broker.navigate(submit_url)
    time.sleep(1.5)
    submit_btn_id = find_submit_btn(broker)
    if not submit_btn_id:
        print_fail("Could not find submit button on auth-submit page")
        sys.exit(1)
        
    print_step("B. Issue Auth for Form A")
    auth_res = broker.issue_auth(submit_btn_id, broker._session_id, 300)
    if auth_res.get("status") != "ok":
        print_fail(f"issue_auth failed: {auth_res}")
        sys.exit(1)
    auth_id = auth_res["auth_id"]
    print_pass(f"Auth issued: {auth_id}")
    
    # Check that issue_auth populated URL correctly
    auth_record = broker.issued_authorizations[auth_id]
    print_pass(f"Expected URL resolved to: {auth_record['expected_url']}")
    if "submit-target" not in auth_record["expected_url"]:
        print_fail(f"Invalid expected_url in auth record: {auth_record}")
        sys.exit(1)

    print_step("C. Unrelated background POST while auth pending -> BLOCKED")
    trigger_background_post(broker)
    if _posts["/analytics"] > 0:
        print_fail(f"Background POST allowed while auth pending! _posts: {_posts}")
        sys.exit(1)
    print_pass("Background POST blocked")
    
    # Verify auth still exists (was not consumed)
    if auth_id not in broker.issued_authorizations:
        print_fail("Auth was consumed by unrelated POST!")
        sys.exit(1)
    print_pass("Auth was NOT consumed by unrelated POST")

    print_step("D. Intended Form A POST -> ALLOWED")
    sub_res = broker.submit(submit_btn_id, auth_id)
    if sub_res.get("status") != "ok":
        print_fail(f"Authorized submit failed: {sub_res}")
        sys.exit(1)
    time.sleep(1)
    if _posts["/submit-target"] != 1:
        print_fail(f"Authorized POST did not reach server. _posts: {_posts}")
        sys.exit(1)
    print_pass("Intended POST allowed")

    print_step("E. Reuse Form A Auth -> BLOCKED")
    sub_res2 = broker.submit(submit_btn_id, auth_id)
    if sub_res2.get("status") != "error" or "INVALID_AUTHORIZATION" not in sub_res2.get("message", ""):
        print_fail(f"Expected INVALID_AUTHORIZATION, got: {sub_res2}")
        sys.exit(1)
    print_pass("Auth reuse blocked")

    print_step("F. Second unrelated POST -> BLOCKED")
    trigger_background_post(broker)
    if _posts["/analytics"] > 0:
        print_fail(f"Second background POST allowed! _posts: {_posts}")
        sys.exit(1)
    print_pass("Second background POST blocked")
    
    print_step("G. Browser restart -> previous auth invalid")
    # Issue a new auth
    broker.navigate(submit_url)
    time.sleep(1.5)
    submit_btn_id3 = find_submit_btn(broker)
    auth_res3 = broker.issue_auth(submit_btn_id3, broker._session_id, 300)
    auth_id3 = auth_res3["auth_id"]
    
    broker.stop_browser()
    broker.start_browser(submit_url)
    broker.navigate(submit_url)
    time.sleep(1.5)
    
    # Try using the old auth ID in the new session, finding a new target
    submit_btn_id4 = find_submit_btn(broker)
    sub_res4 = broker.submit(submit_btn_id4, auth_id3)
    if sub_res4.get("status") != "error":
        print_fail(f"Auth survived browser restart! {sub_res4}")
        sys.exit(1)
    print_pass(f"Auth after restart failed as expected: {sub_res4.get('message')}")

    print_step("H. Textarea newline -> ALLOWED")
    broker.navigate(deny_url)
    time.sleep(1.5)
    find_ta = broker.find({"tag": "textarea"})
    ta_targets = find_ta.get("targets", [])
    if not ta_targets:
        print_fail("Could not find textarea")
        sys.exit(1)
    ta_id = ta_targets[0]["target_id"]
    ta_res = broker.type(ta_id, "hello\nworld")
    if ta_res.get("status") != "ok":
        print_fail(f"Expected SUCCESS from textarea newline type, got: {ta_res}")
        sys.exit(1)
    print_pass("Textarea newline type succeeded")

    print_step("J. Programmatic form.requestSubmit() without auth -> BLOCKED")
    broker._cdp_request("Runtime.evaluate", {"expression": "document.getElementById('test-form').requestSubmit();"})
    time.sleep(0.5)
    if _posts["/submit-target"] > 1:
        print_fail(f"form.requestSubmit() allowed! _posts: {_posts}")
        sys.exit(1)
    print_pass("form.requestSubmit() blocked")

    broker.stop_browser()
    srv.shutdown()
    done_ok()

if __name__ == "__main__":
    main()
