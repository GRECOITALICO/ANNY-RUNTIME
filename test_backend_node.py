import json, socket
import sys, time

sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.broker_server import BrowserBroker

broker = BrowserBroker()
broker.start_browser('about:blank')

# Inject element
broker._cdp_request("Runtime.evaluate", {
    "expression": "document.body.innerHTML = '<button id=\"btn\">Click me</button>';"
})

broker._cdp_request("DOM.enable")

res = broker._cdp_request("Runtime.evaluate", {
    "expression": "document.querySelector('button')",
    "returnByValue": False
})
obj_id = res['result']['objectId']

node_res = broker._cdp_request("DOM.requestNode", {"objectId": obj_id})
backend_id = node_res.get('nodeId')
print("Backend node ID:", backend_id)

resolve_res = broker._cdp_request("DOM.resolveNode", {"backendNodeId": backend_id})
print("Resolve node:", resolve_res)

broker.stop_browser()
