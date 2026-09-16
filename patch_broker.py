import re

with open("runtime/browser/broker_server.py", "r") as f:
    content = f.read()

# Add debug print to requestPaused
content = content.replace('if method == "Fetch.requestPaused":', 'if method == "Fetch.requestPaused":\n                print(f"[DEBUG Fetch] Paused: {params}", file=sys.stderr)')

with open("runtime/browser/broker_server.py", "w") as f:
    f.write(content)
