import subprocess
import time
import urllib.request
import json
import urllib.error
import websocket # we might not have this, let's see

proc = subprocess.Popen([
    "/usr/bin/google-chrome",
    "--remote-debugging-port=9222",
    "--user-data-dir=/tmp/test-profile",
    "about:blank"
], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)

time.sleep(2)

try:
    req = urllib.request.Request("http://127.0.0.1:9222/json/version")
    with urllib.request.urlopen(req) as response:
        version_data = json.loads(response.read().decode())
        ws_url = version_data["webSocketDebuggerUrl"]
        print("WS URL:", ws_url)
except Exception as e:
    print("Error getting CDP info:", e)

proc.terminate()
