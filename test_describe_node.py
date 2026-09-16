import sys, time
sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.broker_server import BrowserBroker

b = BrowserBroker()
b.start_browser('about:blank')
b._cdp_request("DOM.enable")
b._cdp_request("Runtime.evaluate", {"expression": "document.body.innerHTML = '<a>Link</a>';"})

res = b._cdp_request("Runtime.evaluate", {"expression": "document.querySelector('a')", "returnByValue": False})
obj_id = res['result']['objectId']

desc = b._cdp_request("DOM.describeNode", {"objectId": obj_id})
print("describeNode:", desc)

b.stop_browser()
