import pytest
from unittest.mock import patch, MagicMock

from runtime.browser.broker_server import BrowserBroker, _REQUIRED_FIELDS, _FORBIDDEN_FIELDS
from runtime.mcp.tools import browser_interaction_select, browser_interaction_check, browser_interaction_uncheck, ToolImplementationError

@pytest.fixture
def running_broker():
    broker = BrowserBroker()
    broker.process = MagicMock()
    broker.process.poll.return_value = None
    broker._session_id = "test-session"
    return broker

def mock_cdp_control_success(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        if "getBoundingClientRect" in params.get("functionDeclaration", ""):
            return {"result": {"value": {"tag": "input", "type": "checkbox"}}}
        return {"result": {"value": {"success": True}}}
    return {}

def mock_cdp_control_radio_uncheck(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        if "getBoundingClientRect" in params.get("functionDeclaration", ""):
            return {"result": {"value": {"tag": "input", "type": "radio"}}}
        return {"result": {"value": {"success": True}}}
    return {}

def mock_cdp_control_select_success(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        if "getBoundingClientRect" in params.get("functionDeclaration", ""):
            return {"result": {"value": {"tag": "select", "type": "select-one"}}}
        return {"result": {"value": {"success": True}}}
    return {}

class TestGovernedControlIPC:
    def test_select_success(self, running_broker):
        running_broker.targets["bt_valid"] = {"node_obj_id": "obj1", "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_control_select_success), \
             patch.object(running_broker, "observe") as mock_obs:
            mock_obs.return_value = {"status": "ok", "observation": {"url": "https://example.com", "title": "Test"}}
            res = running_broker.select("bt_valid", "Option 1")
    
        assert res["status"] == "ok"
        assert res["result"] == "success"
        assert res["action"] == {"type": "select", "target_id": "bt_valid", "option": "Option 1"}

    def test_check_success(self, running_broker):
        running_broker.targets["bt_valid"] = {"node_obj_id": "obj1", "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_control_success), \
             patch.object(running_broker, "observe") as mock_obs:
            mock_obs.return_value = {"status": "ok", "observation": {"url": "https://example.com", "title": "Test"}}
            res = running_broker.check("bt_valid")
    
        assert res["status"] == "ok"
        assert res["result"] == "success"
        assert res["action"] == {"type": "check", "target_id": "bt_valid"}

    def test_uncheck_success(self, running_broker):
        running_broker.targets["bt_valid"] = {"node_obj_id": "obj1", "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_control_success), \
             patch.object(running_broker, "observe") as mock_obs:
            mock_obs.return_value = {"status": "ok", "observation": {"url": "https://example.com", "title": "Test"}}
            res = running_broker.uncheck("bt_valid")
    
        assert res["status"] == "ok"
        assert res["result"] == "success"
        assert res["action"] == {"type": "uncheck", "target_id": "bt_valid"}

    def test_radio_uncheck_fails(self, running_broker):
        running_broker.targets["bt_radio"] = {"node_obj_id": "obj1", "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_control_radio_uncheck):
            res = running_broker.uncheck("bt_radio")
        assert res["status"] == "error"
        assert "TARGET_UNSUPPORTED_ACTION" in res["message"]

class TestMCPToolsPhase3:
    @patch("runtime.browser.manager.BrowserSessionManager.check")
    def test_browser_interaction_check_mcp(self, mock_manager_check):
        mock_manager_check.return_value = {
            "status": "ok", 
            "result": "success", 
            "action": {"type": "check", "target_id": "bt_123"},
            "observation": {}
        }
        
        # Test valid
        res = browser_interaction_check({"target_id": "bt_123"}, {})
        assert res["result"] == "success"
        
        # Test forbidden
        with pytest.raises(ToolImplementationError):
            browser_interaction_check({"target_id": "bt_123", "script": "alert(1)"}, {})
