import sys

with open("runtime/browser/broker_server.py", "r") as f:
    content = f.read()

content = content.replace(
    'if method == "Fetch.requestPaused":',
    'if "error" in event:\n                print(f"[DEBUG CDP ERROR] {event}", file=sys.stderr)\n            if method == "Fetch.requestPaused":'
)

with open("runtime/browser/broker_server.py", "w") as f:
    f.write(content)
