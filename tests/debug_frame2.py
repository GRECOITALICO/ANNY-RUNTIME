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

target_id = b.find({"tag": "button"})["targets"][0]["target_id"]
target_record = b.targets[target_id]
obj_id = b._cdp_request("DOM.resolveNode", {"backendNodeId": target_record["backendNodeId"]})["object"]["objectId"]

# Try to resolve form target frame via JS
res = b._cdp_request("Runtime.callFunctionOn", {
    "objectId": obj_id,
    "functionDeclaration": '''function() {
        let form = this.closest('form');
        if (!form) return {error: "no_form"};
        let formTarget = form.target || "";
        let targetFrame = formTarget ? window.frames[formTarget] : window;
        if (!targetFrame) targetFrame = window;
        // Inject token into target frame's document
        return {
            formTarget: formTarget,
            hasTargetFrame: !!window.frames[formTarget]
        };
    }''',
    "returnByValue": True
})
print("FORM JS RESULT:", res["result"]["value"])

b.stop_browser()
srv.shutdown()
