import sys, time
sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')

# Start the dev broker
import subprocess
proc = subprocess.Popen(["python3", "runtime/browser/broker_server.py"])
time.sleep(2)

from runtime.browser.manager import BrowserSessionManager
m = BrowserSessionManager()
m._send_ipc("START_BROWSER", url="about:blank")
time.sleep(2)
m.navigate("https://example.com")
time.sleep(2)

res = m.find({"tag": "a"})
print("FIND:", res)

if res.get("targets"):
    tid = res["targets"][0]["target_id"]
    print("CLICK:", m.click(tid))

m._send_ipc("STOP_BROWSER")
proc.terminate()
