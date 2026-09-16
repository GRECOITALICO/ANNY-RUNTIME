import pytest
from unittest.mock import patch, MagicMock

from runtime.browser.manager import BrowserSessionManager
from runtime.browser.broker_server import BrowserBroker

@pytest.fixture
def manager():
    mgr = BrowserSessionManager(profile="test")
    return mgr

@pytest.fixture
def running_broker(tmp_path):
    broker = BrowserBroker()
    broker.profile_dir = tmp_path
    broker.process = MagicMock()
    broker.process.poll.return_value = None
    broker.ws_url = "ws://localhost:19222/devtools/page/1"
    return broker

def test_manager_navigate_action(manager):
    with patch.object(manager, "_send_ipc", return_value={"status": "ok", "action": "back"}) as mock_ipc:
        res = manager.navigate_action("back")
        assert res["status"] == "ok"
        mock_ipc.assert_called_once_with("NAVIGATE_ACTION", action="back")

def test_manager_observe(manager, tmp_path):
    with patch.object(manager, "_send_ipc") as mock_ipc:
        mock_ipc.return_value = {
            "status": "ok", 
            "observation": {"url": "http://test", "title": "Test", "text": "Hello", "links": []}
        }
        res = manager.observe()
        assert res["status"] == "ok"
        assert "observation" in res

def test_broker_navigate_action(running_broker):
    with patch.object(running_broker, "_cdp_request") as mock_cdp:
        mock_cdp.side_effect = [
            {"currentIndex": 1, "entries": [{"id": 1, "url": "url1"}, {"id": 2, "url": "url2"}]},
            None
        ]
        res = running_broker.navigate_action("back")
        assert res["status"] == "ok"
        
        # Called getNavigationHistory, then navigateToHistoryEntry
        assert mock_cdp.call_count == 2
        mock_cdp.assert_any_call("Page.getNavigationHistory")
        mock_cdp.assert_any_call("Page.navigateToHistoryEntry", {"entryId": 1})

def test_broker_observe(running_broker):
    with patch.object(running_broker, "_cdp_request") as mock_cdp:
        mock_cdp.return_value = {
            "result": {
                "value": {
                    "url": "http://test",
                    "title": "Title",
                    "text": "Text",
                    "links": []
                }
            }
        }
        res = running_broker.observe()
        assert res["status"] == "ok"
        assert res["observation"]["title"] == "Title"
        mock_cdp.assert_called_once()
        assert mock_cdp.call_args[0][0] == "Runtime.evaluate"
