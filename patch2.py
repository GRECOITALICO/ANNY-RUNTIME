import sys

with open("runtime/browser/broker_server.py", "r") as f:
    content = f.read()

content = content.replace(
    'if method == "Fetch.requestPaused":',
    'if method == "Fetch.requestPaused":\n                import sys\n                print(f"[DEBUG Fetch] Paused: {params}", file=sys.stderr)'
)

content = content.replace(
    'self._send_cdp_async("Fetch.continueRequest", {"requestId": request_id})',
    'print(f"[DEBUG Fetch] Continuing request {request_id}", file=sys.stderr)\n                            self._send_cdp_async("Fetch.continueRequest", {"requestId": request_id})'
)

content = content.replace(
    'self._send_cdp_async("Fetch.failRequest", {"requestId": request_id, "errorReason": "AccessDenied"})',
    'print(f"[DEBUG Fetch] Failing request {request_id}", file=sys.stderr)\n            self._send_cdp_async("Fetch.failRequest", {"requestId": request_id, "errorReason": "AccessDenied"})'
)

with open("runtime/browser/broker_server.py", "w") as f:
    f.write(content)
