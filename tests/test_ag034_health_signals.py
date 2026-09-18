import json
from unittest.mock import Mock, MagicMock
from http.server import BaseHTTPRequestHandler
import pytest
from runtime.admin.routes import AdminRouter

class MockResponse:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.body = b""
        
    def send_response(self, code):
        self.status = code
        
    def send_header(self, k, v):
        self.headers[k] = v
        
    def end_headers(self):
        pass
        
    def write(self, data):
        self.body += data

class MockHandler(BaseHTTPRequestHandler):
    def __init__(self):
        self.wfile = MockResponse()
        
    def send_response(self, code, message=None):
        self.wfile.send_response(code)
        
    def send_header(self, keyword, value):
        self.wfile.send_header(keyword, value)
        
    def end_headers(self):
        self.wfile.end_headers()

def test_health_live():
    router = AdminRouter({})
    handler = MockHandler()
    
    router.dispatch_get("/health/live", handler)
    
    assert handler.wfile.status == 200
    resp = json.loads(handler.wfile.body.decode('utf-8'))
    assert resp["status"] == "alive"

def test_health_ready_when_ready():
    mock_engine = MagicMock()
    mock_engine.state.name = "READY"
    mock_engine.bootstrap_report.anny_ready = True
    
    router = AdminRouter({'runtime_engine': mock_engine})
    handler = MockHandler()
    
    router.dispatch_get("/health/ready", handler)
    
    assert handler.wfile.status == 200
    resp = json.loads(handler.wfile.body.decode('utf-8'))
    assert resp["status"] == "ready"

def test_health_ready_when_not_ready():
    mock_engine = MagicMock()
    mock_engine.state.name = "ADMIN_MODE"
    mock_engine.bootstrap_report.anny_ready = False
    
    router = AdminRouter({'runtime_engine': mock_engine})
    handler = MockHandler()
    
    router.dispatch_get("/health/ready", handler)
    
    assert handler.wfile.status == 503
    resp = json.loads(handler.wfile.body.decode('utf-8'))
    assert resp["status"] == "not_ready"
    assert "ADMIN_MODE" in resp["reason"]

def test_api_status_derives_health():
    mock_engine = MagicMock()
    mock_engine.state.name = "ERROR"
    mock_engine.bootstrap_report.anny_ready = False
    mock_engine.bootstrap_report.timestamp = None
    mock_engine.bootstrap_report.fabric_node = "UNKNOWN"
    mock_engine.config = None
    
    router = AdminRouter({'runtime_engine': mock_engine})
    handler = MockHandler()
    
    class MockParsed:
        path = '/api/status'
        query = ''
        
    router.dispatch_get("/api/status", handler)
    
    resp = json.loads(handler.wfile.body.decode('utf-8'))
    assert resp["runtime_health"] == "NOT_HEALTHY"
    
    mock_engine.state.name = "READY"
    mock_engine.bootstrap_report.anny_ready = True
    mock_engine.bootstrap_report.timestamp = None
    mock_engine.bootstrap_report.fabric_node = "UNKNOWN"
    handler = MockHandler() # reset handler
    router.dispatch_get("/api/status", handler)
    resp = json.loads(handler.wfile.body.decode('utf-8'))
    assert resp["runtime_health"] == "HEALTHY"

def test_health_no_secret_disclosure():
    mock_engine = MagicMock()
    mock_engine.state.name = "READY"
    mock_engine.bootstrap_report.anny_ready = True
    mock_engine.bootstrap_report.timestamp = None
    mock_engine.bootstrap_report.fabric_node = "UNKNOWN"
    
    router = AdminRouter({'runtime_engine': mock_engine})
    handler = MockHandler()
    
    router.dispatch_get("/health/ready", handler)
    body_str = handler.wfile.body.decode('utf-8')
    assert "token" not in body_str.lower()
    assert "secret" not in body_str.lower()
    assert "key" not in body_str.lower()
