import json, socket
import sys, time

sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.broker_server import BrowserBroker

broker = BrowserBroker()
broker.start_browser('https://example.com')
time.sleep(2)

frame_id = broker._cdp_request("Page.getFrameTree")["frameTree"]["frame"]["id"]
res = broker._cdp_request("Page.createIsolatedWorld", {
    "frameId": frame_id,
    "worldName": "anny_governed_world",
    "grantUniveralAccess": True
})
ctx_id = res['executionContextId']
print("Initial ctx_id:", ctx_id)

broker._cdp_request("Runtime.evaluate", {
    "contextId": ctx_id,
    "expression": "window.__annyTargets = { 'A': 123 };"
})

broker._cdp_request("Page.navigate", {"url": "about:blank"})
time.sleep(2)

try:
    res = broker._cdp_request("Runtime.evaluate", {
        "contextId": ctx_id,
        "expression": "window.__annyTargets"
    })
    print("Navigated Eval:", res)
except Exception as e:
    print("Eval Failed (as expected):", e)

broker.stop_browser()
