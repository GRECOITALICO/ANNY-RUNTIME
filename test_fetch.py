import asyncio
import json
import time
import websocket
from runtime.browser.broker_server import BrowserBroker

b = BrowserBroker()
b.start_browser("about:blank")
time.sleep(1)

# Connect to CDP directly for testing
res = urllib.request.urlopen("http://127.0.0.1:" + str(b.process.args[b.process.args.index("--remote-debugging-port=")+len("--remote-debugging-port="):]) + "/json").read()
# Wait, the port is assigned dynamically by Chrome when passed 0.
