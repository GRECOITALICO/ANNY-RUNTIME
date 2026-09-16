import sys, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, ".")
from runtime.browser.broker_server import BrowserBroker

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
b.start_browser(f"http://127.0.0.1:{port}")
b.navigate(f"http://127.0.0.1:{port}")
time.sleep(1.5)

import uuid
target_id = b.find({"tag": "button"})["targets"][0]["target_id"]
target_record = b.targets[target_id]
obj_id = b._cdp_request("DOM.resolveNode", {"backendNodeId": target_record["backendNodeId"]})["object"]["objectId"]

token = str(uuid.uuid4())
# Inject token into the target frame's document
b._cdp_request("Runtime.callFunctionOn", {
    "objectId": obj_id,
    "functionDeclaration": f'''function() {{
        let form = this.closest('form');
        let formTarget = form ? (form.target || "") : "";
        let targetWin = formTarget ? window.frames[formTarget] : window;
        if (!targetWin) targetWin = window;
        targetWin.document.documentElement.setAttribute('data-anny-auth-token', '{token}');
    }}''',
    "returnByValue": True
})

# Walk frames to find which one got the token
tree = b._cdp_request("Page.getFrameTree")
def get_frames(t):
    frames = [t["frame"]["id"]]
    for c in t.get("childFrames", []):
        frames.extend(get_frames(c))
    return frames

f_ids = get_frames(tree["frameTree"])
print("ALL FRAMES:", f_ids)

for f_id in f_ids:
    w = b._cdp_request("Page.createIsolatedWorld", {"frameId": f_id, "worldName": "anny_auth"})
    ctx_id = w["executionContextId"]
    res = b._cdp_request("Runtime.evaluate", {"contextId": ctx_id, "expression": "document.documentElement.getAttribute('data-anny-auth-token')"})
    val = res.get("result", {}).get("value")
    print(f"  Frame {f_id}: token={val}")

b.stop_browser()
srv.shutdown()
