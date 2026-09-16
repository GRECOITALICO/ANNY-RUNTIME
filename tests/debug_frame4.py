import sys, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, ".")
from runtime.browser.broker_server import BrowserBroker

FORM_HTML = b"""<!DOCTYPE html>
<html><body>
  <form id="test-form" action="/submit-target" method="post" target="iframe1">
    <input type="text" id="test-name" />
    <textarea id="test-textarea"></textarea>
    <button type="submit" id="test-submit">Submit Main</button>
  </form>
  <form id="redirect-302-form" action="/redirect-302" method="post" target="iframe1">
    <button type="submit" id="btn-302">Submit 302</button>
  </form>
  <iframe id="iframe1" src="/iframe-page" name="iframe1"></iframe>
</body></html>"""

IFRAME_HTML = b"""<!DOCTYPE html>
<html><body>
  <form id="iframe-form" action="/submit-target" method="post">
    <input type="text" id="iframe-name" />
    <button type="submit" id="iframe-submit">Submit Iframe</button>
  </form>
</body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = IFRAME_HTML if self.path == "/iframe-page" else FORM_HTML
        self.send_response(200)
        self.send_header("Content-Type","text/html")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self,*a): pass

srv = HTTPServer(("127.0.0.1",0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base_url = f"http://127.0.0.1:{port}"

b = BrowserBroker()

captured = []
orig = b._handle_cdp_event
def patched(event):
    if event.get("method") == "Fetch.requestPaused":
        p = event.get("params", {})
        captured.append({"method": p.get("request",{}).get("method"), "frameId": p.get("frameId"), "url": p.get("request",{}).get("url")})
    orig(event)
b._handle_cdp_event = patched

b.start_browser(base_url)
b.navigate(base_url)
time.sleep(2.0)  # Give iframe time to load

target_id = b.find({"tag": "button", "text": "Submit Main"})["targets"][0]["target_id"]
print("TARGET_ID:", target_id)
auth_res = b.issue_auth(target_id, b._session_id)
print("AUTH RES:", auth_res)
if "auth_id" in auth_res:
    auth = b.issued_authorizations[auth_res["auth_id"]]
    print("EXPECTED_FRAME_ID:", auth["expected_frame_id"])
    print("EXPECTED_METHOD:", auth["expected_method"])
    print("EXPECTED_URL:", auth["expected_url"])
    
    # Now submit via broker
    captured.clear()
    sub = b.submit(target_id, auth_res["auth_id"])
    time.sleep(1)
    print("SUBMIT RESULT:", sub)
    print("CAPTURED POST EVENTS:")
    for c in captured:
        if c["method"] in ("POST","PUT","PATCH","DELETE"):
            print(" ", c)
else:
    print("Auth failed!")

b.stop_browser()
srv.shutdown()
