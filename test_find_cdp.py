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

b._cdp_request("Runtime.evaluate", {
    "expression": "document.body.innerHTML = '<a>Link 1</a><a>Link 2</a>';"
})
b._cdp_request("DOM.enable")

# Find logic
script = '''(function() {
    return Array.from(document.querySelectorAll('a')).map(a => ({
        node: a,
        text: a.innerText
    }));
})()'''

res = b._cdp_request("Runtime.evaluate", {
    "expression": script,
    "returnByValue": False
})

array_obj_id = res['result']['objectId']

# Get elements
props = b._cdp_request("Runtime.getProperties", {
    "objectId": array_obj_id,
    "ownProperties": True
})

targets = []
for prop in props.get("result", []):
    if prop.get("name").isdigit(): # array index
        item_obj_id = prop["value"]["objectId"]
        
        # Now we need the 'node' and 'text' from this item
        item_props = b._cdp_request("Runtime.getProperties", {
            "objectId": item_obj_id,
            "ownProperties": True
        })
        
        node_obj_id = None
        text = ""
        for ip in item_props.get("result", []):
            if ip["name"] == "node":
                node_obj_id = ip["value"]["objectId"]
            elif ip["name"] == "text":
                text = ip["value"]["value"]
                
        # Get backendNodeId
        node_res = b._cdp_request("DOM.requestNode", {"objectId": node_obj_id})
        backend_id = node_res["nodeIds"][0] if "nodeIds" in node_res else node_res.get("nodeId")
        
        targets.append({
            "target_id": "bt_" + str(uuid.uuid4()),
            "backendNodeId": backend_id,
            "text": text
        })

print("Found targets:")
print(json.dumps(targets, indent=2))

b.stop_browser()
