import json, socket
import sys, time

sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.broker_server import BrowserBroker
import websocket

class PersistentBroker(BrowserBroker):
    def __init__(self):
        super().__init__()
        self._ws = None
        self._msg_id = 0

    def _get_ws(self):
        if self._ws:
            return self._ws
        url = self._get_cdp_ws_url()
        if not url: return None
        self._ws = websocket.create_connection(url, timeout=5, suppress_origin=True)
        return self._ws

    def _cdp_request(self, method: str, params: dict | None = None) -> dict:
        ws = self._get_ws()
        self._msg_id += 1
        msg_id = self._msg_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        ws.send(json.dumps(payload))
        
        while True:
            resp = json.loads(ws.recv())
            if resp.get("id") == msg_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP Error: {resp['error']}")
                return resp.get("result", {})

b = PersistentBroker()
b.start_browser('about:blank')
time.sleep(1)

# Test 1: Evaluate
res1 = b._cdp_request("Runtime.evaluate", {"expression": "({foo: 'bar'})", "returnByValue": False})
obj_id = res1["result"]["objectId"]
print("Eval 1:", obj_id)

# Test 2: Get properties
res2 = b._cdp_request("Runtime.getProperties", {"objectId": obj_id})
print("Props 2:", res2)

b.stop_browser()
