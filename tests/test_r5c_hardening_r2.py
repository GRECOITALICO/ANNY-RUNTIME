import pytest
import time
import json
import threading
from runtime.browser.broker_server import BrowserBroker
from runtime.browser.authorization import PendingSubmissionAuthorization

class MockWebSocket:
    def __init__(self):
        self.sent = []
        self.cond = threading.Condition()
        self.responses = []
        
    def send(self, msg):
        self.sent.append(json.loads(msg))
        
    def recv(self):
        with self.cond:
            while not self.responses:
                self.cond.wait()
            return self.responses.pop(0)
            
    def close(self):
        pass

class MockProcess:
    def poll(self):
        return None
    def terminate(self):
        pass
    def wait(self, timeout=None):
        pass

@pytest.fixture
def broker(monkeypatch):
    b = BrowserBroker()
    b._session_id = "test-session"
    b.process = MockProcess()
    b._cdp_ws = MockWebSocket()
    b._cdp_listener_thread = threading.Thread(target=b._cdp_listener_loop, args=(b._cdp_ws,), daemon=True)
    b._cdp_listener_thread.start()
    return b

def test_issue_auth_resolves_form_metadata(broker):
    broker.targets["target_1"] = {"session_id": "test-session", "backendNodeId": 123}
    
    injected_token = {}

    def mock_request(method, params=None, timeout=5.0):
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "obj1"}}
        elif method == "DOM.describeNode":
            return {"node": {"frameId": "frame1"}}
        elif method == "Runtime.callFunctionOn":
            decl = (params or {}).get("functionDeclaration", "")
            if "data-anny-auth-token" in decl and "setAttribute" in decl:
                # Extract token from the injected JS and cache it
                import re
                m = re.search(r"data-anny-auth-token',\s*'([^']+)'", decl)
                if m:
                    injected_token["value"] = m.group(1)
                return {}
            return {"result": {"value": {"action": "http://test/submit", "method": "POST"}}}
        elif method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "frame1"}, "childFrames": []}}
        elif method == "Page.createIsolatedWorld":
            return {"executionContextId": 999}
        elif method == "Runtime.evaluate":
            expr = (params or {}).get("expression", "")
            if "getAttribute" in expr:
                return {"result": {"value": injected_token.get("value")}}
            return {"result": {"value": None}}
        return {}
    
    broker._cdp_request = mock_request
    
    res = broker.issue_auth("target_1", "test-session", 300)
    assert res["status"] == "ok"
    auth_id = res["auth_id"]
    
    auth = broker.issued_authorizations[auth_id]
    assert auth["expected_method"] == "POST"
    assert auth["expected_url"] == "http://test/submit"
    assert auth["expected_frame_id"] == "frame1"

def test_unrelated_post_does_not_consume_auth(broker):
    pending = PendingSubmissionAuthorization(
        auth_id="auth1", session_id="test-session", target_id="t1",
        expected_method="POST", expected_url="http://test/submit",
        expected_frame_id="frame1", issued_at=time.time(), expires_at=time.time()+300
    )
    broker._pending_submission = pending
    
    event = {
        "method": "Fetch.requestPaused",
        "params": {
            "requestId": "req1",
            "frameId": "frame1",
            "request": {"url": "http://test/analytics", "method": "POST"}
        }
    }
    broker._handle_cdp_event(event)
    
    assert broker._pending_submission is pending
    assert broker._cdp_ws.sent[-1]["method"] == "Fetch.failRequest"

def test_intended_post_consumed(broker):
    pending = PendingSubmissionAuthorization(
        auth_id="auth1", session_id="test-session", target_id="t1",
        expected_method="POST", expected_url="http://test/submit",
        expected_frame_id="frame1", issued_at=time.time(), expires_at=time.time()+300
    )
    broker._pending_submission = pending
    
    event = {
        "method": "Fetch.requestPaused",
        "params": {
            "requestId": "req2",
            "frameId": "frame1",
            "request": {"url": "http://test/submit", "method": "POST"}
        }
    }
    broker._handle_cdp_event(event)
    
    assert broker._pending_submission is None
    assert broker._cdp_ws.sent[-1]["method"] == "Fetch.continueRequest"

def test_cross_session_blocked(broker):
    broker.issued_authorizations["auth1"] = {
        "target_id": "t1", "session_id": "wrong-session", "expires_at": time.time()+300
    }
    res = broker.submit("t1", "auth1")
    assert res["status"] == "error"
    assert "AUTHORIZATION_SESSION_MISMATCH" in res["message"]

def test_stop_clears_pending_submission(broker):
    broker._pending_submission = "mock-pending"
    broker.issued_authorizations = {"mock": "mock"}
    broker.stop_browser()
    assert broker._pending_submission is None
    assert broker.issued_authorizations == {}

def test_issue_auth_not_in_mcp_registry():
    with open("runtime/mcp/registry.py", "r") as f:
        content = f.read()
    assert "issue_auth" not in content
    assert "ISSUE_AUTH" not in content
    assert "issue_authorization" not in content
