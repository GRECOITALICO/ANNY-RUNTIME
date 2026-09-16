import sys, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, ".")
from runtime.browser.broker_server import BrowserBroker

FORM_HTML = b"""<!DOCTYPE html>
<html><body>
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
base_url = f"http://127.0.0.1:{port}"

b = BrowserBroker()
b.start_browser(base_url)
b.navigate(base_url)
time.sleep(2.0)
print("ALL BUTTONS:", b.find({"tag": "button"}))
b.stop_browser()
srv.shutdown()
