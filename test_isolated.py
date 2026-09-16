import json, socket
import sys, time

sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.broker_server import BrowserBroker

broker = BrowserBroker()
broker.start_browser('https://example.com')
time.sleep(2)

# Create isolated world
res = broker._cdp_request("Page.createIsolatedWorld", {
    "frameId": broker._cdp_request("Page.getFrameTree")["frameTree"]["frame"]["id"],
    "worldName": "anny_governed_world",
    "grantUniveralAccess": True
})
print("Isolated World:", res)
ctx_id = res['executionContextId']

# Evaluate in isolated world
eval_res = broker._cdp_request("Runtime.evaluate", {
    "contextId": ctx_id,
    "expression": "window.__annyTargets = { 'A': document.querySelector('h1') }; Object.keys(window.__annyTargets);"
})
print("Isolated Eval:", eval_res)

# Evaluate in main world
main_eval = broker._cdp_request("Runtime.evaluate", {
    "expression": "window.__annyTargets"
})
print("Main Eval:", main_eval)

broker.stop_browser()
