import sys, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, ".")
from runtime.browser.broker_server import BrowserBroker

_posts = {"frame_ids": [], "request_ids": []}

FORM_HTML = b"""<!DOCTYPE html>
<html><body>
  <form id="f" action="/sub" method="post" target="iframe1">
    <button type="submit" id="btn">Submit</button>
  </form>
  <iframe id="iframe1" src="about:blank" name="iframe1"></iframe>
</body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type","text/html")
        self.send_header("Content-Length", len(FORM_HTML))
        self.end_headers()
        self.wfile.write(FORM_HTML)
    def do_POST(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self,*a): pass

srv = HTTPServer(("127.0.0.1",0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

b = BrowserBroker()

# Patch handler to capture frameIds
orig = b._handle_cdp_event
captured = []
def patched(event):
    if event.get("method") == "Fetch.requestPaused":
        p = event.get("params", {})
        if p.get("request", {}).get("method","").upper() == "POST":
            captured.append({"frameId": p.get("frameId"), "url": p.get("request",{}).get("url")})
    orig(event)
b._handle_cdp_event = patched

b.start_browser(f"http://127.0.0.1:{port}")
b.navigate(f"http://127.0.0.1:{port}")
time.sleep(1.5)

target_id = b.find({"tag": "button"})["targets"][0]["target_id"]
auth_res = b.issue_auth(target_id, b._session_id)
print("AUTH RES:", auth_res)
if "auth_id" in auth_res:
    auth = b.issued_authorizations[auth_res["auth_id"]]
    print("EXPECTED_FRAME_ID:", auth["expected_frame_id"])
    
    # Don't submit via broker - trigger directly to see what frameId arrives
    b._cdp_request("Runtime.evaluate", {"expression": "document.getElementById('f').submit();"})
    time.sleep(1)
    print("CAPTURED REQUESTS:", captured)

b.stop_browser()
srv.shutdown()
