import asyncio
import json
from runtime.browser.broker_server import BrowserBroker

b = BrowserBroker()
b.start_browser("about:blank")
import time
time.sleep(1)

script = f'''function() {{
    const txt = {json.dumps("hello\n")};
    return txt.includes('\\n');
}}'''

print("Script being sent:", repr(script))

res = b._cdp_request("Runtime.evaluate", {
    "expression": "(" + script + ")()",
    "returnByValue": True
})

print("Result:", res)
