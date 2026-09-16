import pytest
from unittest.mock import patch, MagicMock

from runtime.browser.broker_server import BrowserBroker, _REQUIRED_FIELDS, _FORBIDDEN_FIELDS

@pytest.fixture
def running_broker():
    broker = BrowserBroker()
    broker.process = MagicMock()
    broker.process.poll.return_value = None
    broker._session_id = "test-session"
    return broker

def mock_cdp_click_success(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        return {"result": {"value": {"success": True}}}
    return {}

def mock_cdp_click_disabled(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        return {"result": {"value": {"error": "TARGET_DISABLED"}}}
    return {}

def mock_cdp_click_invisible(method, params=None):
    if method == "DOM.resolveNode":
        return {"object": {"objectId": "obj1"}}
    if method == "Runtime.callFunctionOn":
        return {"result": {"value": {"error": "TARGET_INVISIBLE"}}}
    return {}

class TestClickIPC:
    def test_click_success_returns_action_and_observation(self, running_broker):
        running_broker.targets["bt_valid"] = {"backendNodeId": 1, "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_click_success), \
             patch.object(running_broker, "observe") as mock_obs:
            mock_obs.return_value = {"status": "ok", "observation": {"url": "https://example.com/clicked", "title": "Clicked"}}
            res = running_broker.click("bt_valid")
    
        assert res["status"] == "ok"
        assert res["result"] == "success"
        assert res["action"] == {"type": "click", "target_id": "bt_valid"}
        assert res["observation"] == {"url": "https://example.com/clicked", "title": "Clicked"}

class TestDisabledTarget:
    def test_click_disabled_target_rejected(self, running_broker):
        running_broker.targets["bt_disabled"] = {"backendNodeId": 2, "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_click_disabled):
            res = running_broker.click("bt_disabled")
        assert res["status"] == "error"
        assert "TARGET_DISABLED" in res["message"]

class TestInvisibleTarget:
    def test_click_invisible_target_rejected(self, running_broker):
        running_broker.targets["bt_hidden"] = {"backendNodeId": 3, "session_id": "test-session"}
        with patch.object(running_broker, "_cdp_request", side_effect=mock_cdp_click_invisible):
            res = running_broker.click("bt_hidden")
        assert res["status"] == "error"
        assert "TARGET_INVISIBLE" in res["message"]

class TestTargetStale:
    def test_click_stale_target(self, running_broker):
        # Target not in registry
        res = running_broker.click("bt_invalid")
        assert res["status"] == "error"
        assert "TARGET_STALE" in res["message"]
        
    def test_click_wrong_session(self, running_broker):
        # Target from a previous session
        running_broker.targets["bt_old"] = {"backendNodeId": 4, "session_id": "old-session"}
        res = running_broker.click("bt_old")
        assert res["status"] == "error"
        assert "TARGET_STALE" in res["message"]
        
    def test_click_navigation_invalidated(self, running_broker):
        # Target is valid in registry, but DOM.resolveNode fails (navigated away or removed)
        running_broker.targets["bt_nav"] = {"backendNodeId": 5, "session_id": "test-session"}
        def mock_nav(method, params=None):
            if method == "DOM.resolveNode":
                return {} # No object returned because backendNodeId is invalid
        with patch.object(running_broker, "_cdp_request", side_effect=mock_nav):
            res = running_broker.click("bt_nav")
        assert res["status"] == "error"
        assert "TARGET_STALE" in res["message"]

class TestFindIPC:
    def test_find_with_text_query(self, running_broker):
        def mock_find(method, params=None):
            if method == "DOM.enable":
                return {}
            if method == "Runtime.evaluate":
                return {"result": {"objectId": "array_obj"}}
            if method == "Runtime.getProperties":
                if params["objectId"] == "array_obj":
                    return {"result": [{"name": "0", "value": {"objectId": "item_obj"}}]}
                if params["objectId"] == "item_obj":
                    return {"result": [
                        {"name": "node", "value": {"objectId": "node_obj"}},
                        {"name": "text", "value": {"value": "search term"}},
                        {"name": "tag", "value": {"value": "a"}}
                    ]}
            if method == "DOM.describeNode":
                return {"node": {"backendNodeId": 42}}
            return {}

        with patch.object(running_broker, "_cdp_request", side_effect=mock_find):
            res = running_broker.find({"text": "search term"})
        assert res["status"] == "ok"
        assert len(res["targets"]) == 1
        assert res["targets"][0]["text"] == "search term"
        assert res["targets"][0]["tag"] == "a"
        target_id = res["targets"][0]["target_id"]
        assert target_id in running_broker.targets
        assert running_broker.targets[target_id]["backendNodeId"] == 42
