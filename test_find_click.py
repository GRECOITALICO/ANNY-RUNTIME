import sys, time
sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.broker_server import BrowserBroker

b = BrowserBroker()
b.start_browser('about:blank')
b._cdp_request("Runtime.evaluate", {"expression": "document.body.innerHTML = '<a>Link</a>';"})

res = b.find({"tag": "a"})
print("FIND res:", res)

target = b.targets[res["targets"][0]["target_id"]]
print("Stored Target:", target)

try:
    c_res = b.click(res["targets"][0]["target_id"])
    print("CLICK res:", c_res)
except Exception as e:
    print("CLICK error:", e)

b.stop_browser()
