import json, socket
import sys, time

sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.broker_server import BrowserBroker
import websocket

broker = BrowserBroker()
broker.start_browser('about:blank')

url = broker._get_cdp_ws_url()
ws = websocket.create_connection(url, timeout=5, suppress_origin=True)

def req(method, params=None):
    payload = {"id": 1, "method": method, "params": params or {}}
    ws.send(json.dumps(payload))
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == 1:
            return resp.get("result", resp)

res = req("Runtime.evaluate", {
    "expression": "({hello: 'world'})",
    "returnByValue": False
})
print("Result with persistent WS:", res)
ws.close()

ws2 = websocket.create_connection(url, timeout=5, suppress_origin=True)
def req2(method, params=None):
    payload = {"id": 2, "method": method, "params": params or {}}
    ws2.send(json.dumps(payload))
    while True:
        resp = json.loads(ws2.recv())
        if resp.get("id") == 2:
            if "error" in resp:
                return resp["error"]
            return resp.get("result", resp)

res2 = req2("Runtime.getProperties", {
    "objectId": res["result"]["objectId"]
})
print("Result with NEW WS:", res2)
ws2.close()

broker.stop_browser()
