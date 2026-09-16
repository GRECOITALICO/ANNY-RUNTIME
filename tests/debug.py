import sys, time
sys.path.insert(0, ".")
from runtime.browser.broker_server import BrowserBroker
b = BrowserBroker()
b.start_browser("http://example.com")
b._cdp_request("Page.navigate", {"url": "data:text/html,<html><body><button>Submit Main</button></body></html>"})
time.sleep(1)
target_id = b.find({"tag": "button"})["targets"][0]["target_id"]
print(b.issue_auth(target_id, b._session_id))
b.stop_browser()
