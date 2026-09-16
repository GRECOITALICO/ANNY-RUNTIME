import sys, time
sys.path.insert(0, ".")
from runtime.browser.broker_server import BrowserBroker

b = BrowserBroker()
b.start_browser("http://example.com")
b._cdp_request("Page.navigate", {"url": "data:text/html,<html><body><button>Submit Main</button><button>Submit 302</button></body></html>"})
time.sleep(1)
print(b.find({"tag": "button"}))
b.stop_browser()
