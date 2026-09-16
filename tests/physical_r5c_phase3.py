import time
import uuid
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import sys
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

from runtime.browser.broker_server import BrowserBroker
from runtime.mcp.tools import browser_interaction_submit

# --- HTTP Test Fixture ---

class TestHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <!DOCTYPE html>
                <html>
                <body>
                    <form method="POST" action="/submit-target" id="myform">
                        <input type="text" name="ANNY_R5C3_TEST" value="testdata">
                        <input type="password" name="password" value="TEST_MARKER_PASS">
                        <button type="submit" id="btn_submit">Submit</button>
                    </form>
                </body>
                </html>
            """)
        elif self.path == "/success":
            body = b"<!DOCTYPE html><html><body><h1>Success</h1></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        print(f"[TEST SERVER] POST received, path={self.path}, content_length={content_length}")
        
        body = b""
        if content_length > 0:
            self.connection.settimeout(2.0)
            try:
                body = self.rfile.read(content_length)
                print(f"[TEST SERVER] body_redacted=true")
            except Exception as e:
                print(f"[TEST SERVER] Error reading body: {e}")

        body_str = body.decode('utf-8', errors='ignore')
        if "ANNY_R5C3_TEST=" in body_str and "password=" in body_str:
            print("[TEST SERVER] expected_fields_present=true")

        self.server.post_requests.append({
            "path": self.path,
            "body": body_str
        })
        
        if self.path == "/submit-target":
            self.send_response(302)
            self.send_header("Location", "/success")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

def run_server(port):
    server = ThreadingHTTPServer(('127.0.0.1', port), TestHandler)
    server.post_requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

# --- Mock Context for MCP ---

class MockContext:
    def __init__(self):
        pass

# --- Physical Validation ---

def run_validation():
    print("=== Starting physical validation: 001D-R5-C-PHASE3 ===")
    
    # 1. Start Server
    server = run_server(0)
    port = server.server_port
    base_url = f"http://127.0.0.1:{port}"
    print(f"Test server: {base_url}")
    
    # 2. Start Broker
    broker = BrowserBroker()
    broker.start_browser(base_url)
    time.sleep(2)  # Wait for startup and navigation
    
    try:
        # 3. Find target
        find_res = broker.find({"text": "Submit"})
        if not find_res.get("targets"):
            print("❌ Failed to find submit button")
            sys.exit(1)
            
        target_id = find_res["targets"][0]["target_id"]
        print(f"Found target: {target_id}")
        
        # 4. Issue Auth (Trusted Path)
        auth_res = broker.issue_auth(target_id, broker._session_id, 300)
        auth_id = auth_res["auth_id"]
        print(f"[PASS] Issued auth_id: {auth_id}")
        
        # 5. Execute Authorized Submit via MCP Tool
        print("Executing browser.interaction.submit...")
        # Patch BrowserSessionManager to route to our local broker instance
        class DummyManager:
            def __init__(self):
                self.profile = "test-profile"
            def submit(self, tgt, auth):
                return broker.submit(tgt, auth)
                
        import runtime.mcp.tools
        original_manager = runtime.mcp.tools.BrowserSessionManager
        runtime.mcp.tools.BrowserSessionManager = DummyManager
        
        try:
            res = browser_interaction_submit({
                "target_id": target_id,
                "authorization_id": auth_id
            }, MockContext())
            
            # Give network/server time to record
            time.sleep(1)
            
            # 6. Verify Result Structure
            if res["status"] != "ok" or res["result"] != "REQUEST_ACCEPTED":
                print(f"❌ Submit failed unexpectedly: {res}")
                sys.exit(1)
            print("[PASS] Result structured correctly (REQUEST_ACCEPTED)")
            
            # 7. Verify Post-Action Observation (and Redaction)
            obs = res["observation"]
            if obs["url"] != f"{base_url}/success":
                print(f"❌ Post-action URL incorrect: {obs['url']}")
                sys.exit(1)
                
            print("[PASS] Post-action observation valid and URL matches success page")
            
            # 8. Verify Exactly One POST
            if len(server.post_requests) != 1:
                print(f"❌ Expected 1 POST request, got {len(server.post_requests)}")
                sys.exit(1)
                
            post_req = server.post_requests[0]
            if post_req["path"] != "/submit-target":
                print(f"❌ POST went to wrong path: {post_req['path']}")
                sys.exit(1)
                
            if "ANNY_R5C3_TEST=testdata" not in post_req["body"]:
                print(f"❌ Body missing test data (redacted)")
                sys.exit(1)
                
            if "TEST_MARKER_PASS" not in post_req["body"]:
                print(f"❌ Body missing password data (redacted)")
                sys.exit(1)
                
            print("[PASS] Exactly one POST received with correct body")
            
            # 9. Verify Evidence Generated (and Redacted)
            evidence = res["evidence"]
            if evidence["decision"] != "AUTHORIZED_AND_EXECUTED":
                print(f"❌ Evidence decision incorrect: {evidence['decision']}")
                sys.exit(1)
                
            evidence_str = json.dumps(evidence)
            if "TEST_MARKER_PASS" in evidence_str or "testdata" in evidence_str or auth_id in evidence_str:
                print(f"❌ Evidence leaked sensitive data: {evidence_str}")
                sys.exit(1)
                
            print("[PASS] Evidence generated safely (no sensitive data leaked)")
            
            # 10. Attempt Reuse (Single-Use check)
            res_reuse = browser_interaction_submit({
                "target_id": target_id,
                "authorization_id": auth_id
            }, MockContext())
            
            if res_reuse["status"] != "DENIED" or res_reuse["reason"] != "INVALID_AUTHORIZATION":
                print(f"❌ Reuse did not fail correctly: {res_reuse}")
                sys.exit(1)
                
            print("[PASS] Authorization reuse denied (single-use enforced)")
            
            print("\n=== FINAL R5-C PHASE 3 VALIDATION PASSED ===")
        finally:
            runtime.mcp.tools.BrowserSessionManager = original_manager

        
    finally:
        broker.stop_browser()

if __name__ == "__main__":
    run_validation()
