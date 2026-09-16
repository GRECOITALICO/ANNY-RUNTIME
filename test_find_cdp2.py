import json, socket, uuid
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

b._cdp_request("DOM.enable")
b._cdp_request("Runtime.evaluate", {
    "expression": "document.body.innerHTML = '<a>Link 1</a><a>Link 2</a>';"
})

res = b._cdp_request("Runtime.evaluate", {
    "expression": "document.querySelector('a')",
    "returnByValue": False
})

obj_id = res['result']['objectId']
print("requestNode on:", obj_id)
node_res = b._cdp_request("DOM.requestNode", {"objectId": obj_id})
print("node_res:", node_res)

# Then get backendNodeId from the node description? No, DOM.describeNode
desc = b._cdp_request("DOM.describeNode", {"objectId": obj_id})
print("describeNode:", desc)

b.stop_browser()
