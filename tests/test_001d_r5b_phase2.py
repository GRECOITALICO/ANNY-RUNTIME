import pytest
from unittest.mock import patch, MagicMock

from runtime.browser.broker_server import BrowserBroker, _REQUIRED_FIELDS, _FORBIDDEN_FIELDS
from runtime.mcp.tools import browser_interaction_type, browser_interaction_fill, browser_interaction_clear, ToolImplementationError

@pytest.fixture
def running_broker():
    broker = BrowserBroker()
    broker.process = MagicMock()
    broker.process.poll.return_value = None
    broker._session_id = "test-session"
    return broker

def mock_cdp_type_success(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        return {"result": {"value": {"success": True}}}
    return {}

def mock_cdp_target_protected(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        return {"result": {"value": {"error": "TARGET_PROTECTED"}}}
    return {}

class TestGovernedTextInputIPC:
    def test_type_success_returns_action_and_observation(self, running_broker):
        running_broker.targets["bt_valid"] = {"backendNodeId": 1, "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_type_success), \
             patch.object(running_broker, "observe") as mock_obs:
            mock_obs.return_value = {"status": "ok", "observation": {"url": "https://example.com", "title": "Test"}}
            res = running_broker.type("bt_valid", "hello")
    
        assert res["status"] == "ok"
        assert res["result"] == "success"
        assert res["action"] == {"type": "type", "target_id": "bt_valid"}
        # Ensure the text payload is NOT in the returned result dictionary
        assert "hello" not in str(res)
        assert res["observation"] == {"url": "https://example.com", "title": "Test"}

    def test_fill_success_returns_action_and_observation(self, running_broker):
        running_broker.targets["bt_valid"] = {"backendNodeId": 1, "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_type_success), \
             patch.object(running_broker, "observe") as mock_obs:
            mock_obs.return_value = {"status": "ok", "observation": {"url": "https://example.com", "title": "Test"}}
            res = running_broker.fill("bt_valid", "hello")
    
        assert res["status"] == "ok"
        assert res["result"] == "success"
        assert res["action"] == {"type": "fill", "target_id": "bt_valid"}
        # Ensure the text payload is NOT in the returned result dictionary
        assert "hello" not in str(res)
        assert res["observation"] == {"url": "https://example.com", "title": "Test"}

    def test_clear_success_returns_action_and_observation(self, running_broker):
        running_broker.targets["bt_valid"] = {"backendNodeId": 1, "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_type_success), \
             patch.object(running_broker, "observe") as mock_obs:
            mock_obs.return_value = {"status": "ok", "observation": {"url": "https://example.com", "title": "Test"}}
            res = running_broker.clear("bt_valid")
    
        assert res["status"] == "ok"
        assert res["result"] == "success"
        assert res["action"] == {"type": "clear", "target_id": "bt_valid"}
        assert res["observation"] == {"url": "https://example.com", "title": "Test"}

    def test_target_protected_rejected(self, running_broker):
        running_broker.targets["bt_pw"] = {"backendNodeId": 2, "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_target_protected):
            res = running_broker.fill("bt_pw", "secret")
        assert res["status"] == "error"
        assert "TARGET_PROTECTED" in res["message"]
        # Ensure the secret is NOT in the error message
        assert "secret" not in res["message"]

    def test_stale_target(self, running_broker):
        res = running_broker.type("bt_invalid", "test")
        assert res["status"] == "error"
        assert "TARGET_STALE" in res["message"]

class TestMCPTools:
    @patch("runtime.browser.manager.BrowserSessionManager.type")
    def test_browser_interaction_type_mcp(self, mock_manager_type):
        mock_manager_type.return_value = {
            "status": "ok", 
            "result": "success", 
            "action": {"type": "type", "target_id": "bt_123"},
            "observation": {}
        }
        
        # Test valid
        res = browser_interaction_type({"target_id": "bt_123", "text": "hello"}, {})
        assert res["result"] == "success"
        
        # Ensure payload is omitted
        assert "hello" not in str(res)
        
        # Test rejection of forbidden fields
        with pytest.raises(ToolImplementationError) as e:
            browser_interaction_type({"target_id": "bt_123", "text": "hello", "selector": "input"}, {})
        assert "Forbidden input fields" in str(e.value)

    @patch("runtime.browser.manager.BrowserSessionManager.fill")
    def test_browser_interaction_fill_mcp(self, mock_manager_fill):
        mock_manager_fill.return_value = {
            "status": "ok", 
            "result": "success", 
            "action": {"type": "fill", "target_id": "bt_123"},
            "observation": {}
        }
        
        # Test valid
        res = browser_interaction_fill({"target_id": "bt_123", "text": "hello"}, {})
        assert res["result"] == "success"
        
        # Ensure payload is omitted
        assert "hello" not in str(res)
        
        # Test rejection of forbidden fields
        with pytest.raises(ToolImplementationError) as e:
            browser_interaction_fill({"target_id": "bt_123", "text": "hello", "script": "alert(1)"}, {})
        assert "Forbidden input fields" in str(e.value)

    @patch("runtime.browser.manager.BrowserSessionManager.clear")
    def test_browser_interaction_clear_mcp(self, mock_manager_clear):
        mock_manager_clear.return_value = {
            "status": "ok", 
            "result": "success", 
            "action": {"type": "clear", "target_id": "bt_123"},
            "observation": {}
        }
        
        # Test valid
        res = browser_interaction_clear({"target_id": "bt_123"}, {})
        assert res["result"] == "success"
        
        # Test rejection of forbidden fields
        with pytest.raises(ToolImplementationError) as e:
            browser_interaction_clear({"target_id": "bt_123", "backendNodeId": 5}, {})
        assert "Forbidden input fields" in str(e.value)
